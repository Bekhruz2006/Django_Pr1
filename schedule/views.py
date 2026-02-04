from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.db import transaction
from datetime import datetime, timedelta
import json
import uuid
from io import BytesIO 
from django.db.models import Q
try:
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False




from .models import Subject, ScheduleSlot, Semester, Classroom, AcademicWeek, TimeSlot, AcademicPlan, PlanDiscipline, SubjectTemplate  
from .forms import SubjectForm, SemesterForm, ClassroomForm, BulkClassroomForm, AcademicWeekForm, ScheduleImportForm, AcademicPlanForm, PlanDisciplineForm, SubjectTemplateForm
from .services import ScheduleImporter
from accounts.models import Group, Student, Teacher, Director, ProRector, Department


def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'

def is_teacher(user):
    return user.is_authenticated and user.role == 'TEACHER'

def is_student(user):
    return user.is_authenticated and user.role == 'STUDENT'

def get_time_slots_for_shift(shift):
    if shift == 'MORNING':
        return TimeSlot.objects.filter(start_time__gte='08:00:00', start_time__lt='14:00:00').order_by('start_time')
    else:
        return TimeSlot.objects.filter(start_time__gte='13:00:00', start_time__lt='19:00:00').order_by('start_time')

def get_active_semester_for_group(group):
    semester = Semester.objects.filter(groups=group, is_active=True).first()
    if not semester:
        semester = Semester.objects.filter(course=group.course, is_active=True).first()
    return semester

@login_required
def schedule_constructor(request):
    if request.user.role not in ['DEAN', 'VICE_DEAN', 'superuser']:
         messages.error(request, "Доступ запрещен")
         return redirect('core:dashboard')

    active_semester = Semester.objects.filter(is_active=True).first()
    if not active_semester:
        messages.error(request, 'Нет активного семестра. Создайте его в разделе "Семестры".')
        return redirect('schedule:manage_semesters')

    groups = Group.objects.all().order_by('name')
    if request.user.role == 'DEAN':
        faculty = request.user.dean_profile.faculty
        groups = groups.filter(specialty__department__faculty=faculty)

    selected_group_id = request.GET.get('group')
    selected_group = None
    
    if selected_group_id:
        selected_group = get_object_or_404(Group, id=selected_group_id)
        if request.user.role == 'DEAN' and selected_group not in groups:
             return redirect('schedule:constructor')

    time_slots = get_time_slots_for_shift(active_semester.shift)
    days = [(0, 'ДУШАНБЕ'), (1, 'СЕШАНБЕ'), (2, 'ЧОРШАНБЕ'), (3, 'ПАНҶШАНБЕ'), (4, 'ҶУМЪА'), (5, 'ШАНБЕ')]
    
    schedule_data = {}
    subjects_to_schedule = []

    if selected_group:
        slots = ScheduleSlot.objects.filter(
            group=selected_group,
            semester=active_semester,
            is_active=True
        ).select_related('subject', 'teacher__user', 'time_slot', 'classroom')

        schedule_data[selected_group.id] = {}
        for slot in slots:
            if slot.day_of_week not in schedule_data[selected_group.id]:
                schedule_data[selected_group.id][slot.day_of_week] = {}
            schedule_data[selected_group.id][slot.day_of_week][slot.time_slot.id] = slot

        assigned_subjects = selected_group.assigned_subjects.select_related('teacher__user').all()

        for subject in assigned_subjects:
            needed = subject.get_weekly_slots_needed()
            
            if needed['LECTURE'] > 0:
                scheduled = slots.filter(subject=subject, lesson_type='LECTURE').count()
                remaining = max(0, needed['LECTURE'] - scheduled)
                if remaining > 0:
                    subjects_to_schedule.append({
                        'obj': subject,
                        'type': 'LECTURE',
                        'label': 'Лекция',
                        'remaining': remaining,
                        'color': 'primary'
                    })

            if needed['PRACTICE'] > 0:
                scheduled = slots.filter(subject=subject, lesson_type='PRACTICE').count()
                remaining = max(0, needed['PRACTICE'] - scheduled)
                if remaining > 0:
                    subjects_to_schedule.append({
                        'obj': subject,
                        'type': 'PRACTICE',
                        'label': 'Практика',
                        'remaining': remaining,
                        'color': 'success'
                    })
            
            if needed['SRSP'] > 0:
                scheduled = slots.filter(subject=subject, lesson_type='SRSP').count()
                remaining = max(0, needed['SRSP'] - scheduled)
                if remaining > 0:
                    subjects_to_schedule.append({
                        'obj': subject,
                        'type': 'SRSP',
                        'label': 'СРСП',
                        'remaining': remaining,
                        'color': 'warning'
                    })

    return render(request, 'schedule/constructor_with_limits.html', {
        'groups': groups,
        'group': selected_group,
        'semester': active_semester,
        'time_slots': time_slots,
        'days': days,
        'schedule_data': schedule_data,
        'subjects_to_schedule': subjects_to_schedule, 
    })


@login_required
@user_passes_test(is_dean)
@require_POST
def create_schedule_slot(request):
    try:
        data = json.loads(request.body)
        
        if data.get('is_military_day'):
            group_id = data.get('group')
            day_of_week = int(data.get('day_of_week'))
            semester_id = data.get('semester_id')
            
            group = get_object_or_404(Group, id=group_id)
            
            semester = get_object_or_404(Semester, id=semester_id)

            ScheduleSlot.objects.filter(
                group=group, semester=semester, day_of_week=day_of_week
            ).delete()
            
            time_slots = get_time_slots_for_shift(semester.shift)
            
            military_dept = group.specialty.department if group.specialty else Department.objects.first()
            military_subject, _ = Subject.objects.get_or_create(
                code="MILITARY",
                defaults={
                    'name': "Кафедраи ҳарбӣ (Военная кафедра)", 
                    'department': military_dept, 
                    'type': 'PRACTICE'
                }
            )
            
            created_count = 0
            with transaction.atomic():
                for ts in time_slots:
                    ScheduleSlot.objects.create(
                        group=group,
                        subject=military_subject,
                        semester=semester,
                        day_of_week=day_of_week,
                        time_slot=ts,
                        start_time=ts.start_time,
                        end_time=ts.end_time,
                        is_military=True,
                        lesson_type='PRACTICE',
                        classroom=None, # Важно! Нет кабинета - нет конфликта
                        room="Воен. каф" # Просто текст для отображения
                    )
                    created_count += 1
            
            return JsonResponse({'success': True, 'message': f'Назначено {created_count} часов военной кафедры'})

        force = data.get('force', False)
        group_id = data.get('group')
        subject_id = data.get('subject')
        day_of_week = data.get('day_of_week')
        time_slot_id = data.get('time_slot')
        lesson_type = data.get('lesson_type', 'LECTURE')
        semester_id = data.get('semester_id')

        main_group = get_object_or_404(Group, id=group_id)
        subject = get_object_or_404(Subject, id=subject_id)
        time_slot = get_object_or_404(TimeSlot, id=time_slot_id)

        if semester_id:
            active_semester = get_object_or_404(Semester, id=semester_id)
        else:
            active_semester = get_active_semester_for_group(main_group)
        
        if not active_semester:
            return JsonResponse({'success': False, 'error': 'Нет активного семестра'}, status=400)

        start_h = time_slot.start_time.hour
        if active_semester.shift == 'MORNING' and start_h >= 13:
            return JsonResponse({'success': False, 'error': 'Ошибка смены: Слот ДНЕВНОЙ, а семестр УТРЕННИЙ.'}, status=400)
        if active_semester.shift == 'DAY' and start_h < 13:
            return JsonResponse({'success': False, 'error': 'Ошибка смены: Слот УТРЕННИЙ, а семестр ДНЕВНОЙ.'}, status=400)
    
        groups_to_schedule = [main_group]
        is_stream = False
        stream_id = None

        if lesson_type == 'LECTURE' and subject.groups.count() > 1:
            all_subject_groups = list(subject.groups.all())
            if len(all_subject_groups) > 3:
                return JsonResponse({'success': False, 'error': 'Слишком большой поток! Максимум 3 группы.'}, status=400)
            groups_to_schedule = all_subject_groups
            is_stream = True
            stream_id = uuid.uuid4()

        conflicts = []
        if not force:
            for target_group in groups_to_schedule:
                busy_slot = ScheduleSlot.objects.filter(
                    group=target_group,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    semester=active_semester,
                    is_active=True
                ).first()
                if busy_slot:
                    conflicts.append(f"Группа {target_group.name} занята: {busy_slot.subject.name}")
            
            if subject.teacher:
                teacher_slots = ScheduleSlot.objects.filter(
                    teacher=subject.teacher,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    semester=active_semester,
                    is_active=True
                )
                if teacher_slots.exists():
                    conflicts.append(f"Преподаватель {subject.teacher.user.get_full_name()} занят.")

        if conflicts:
            return JsonResponse({'success': False, 'is_conflict': True, 'error': "<br>".join(conflicts)}, status=400)

        with transaction.atomic():
            created_slots = []
            for target_group in groups_to_schedule:
                if force:
                    ScheduleSlot.objects.filter(
                        group=target_group,
                        day_of_week=day_of_week,
                        time_slot=time_slot,
                        semester=active_semester
                    ).delete()

                new_slot = ScheduleSlot.objects.create(
                    group=target_group, 
                    subject=subject, 
                    teacher=subject.teacher,
                    semester=active_semester, 
                    day_of_week=day_of_week,
                    time_slot=time_slot, 
                    lesson_type=lesson_type,
                    start_time=time_slot.start_time, 
                    end_time=time_slot.end_time,
                    stream_id=stream_id if is_stream else None
                )
                created_slots.append(new_slot)

        return JsonResponse({'success': True, 'count': len(created_slots), 'is_stream': is_stream})

    except Exception as e:
        return JsonResponse({'success': False, 'error': f"Ошибка сервера: {str(e)}"}, status=500)


@login_required
@require_POST
def update_schedule_room(request, slot_id):
    try:
        data = json.loads(request.body)
        room_number = data.get('room', '').strip()
        force = data.get('force', False) # НОВЫЙ ПАРАМЕТР
        
        slot = get_object_or_404(ScheduleSlot, id=slot_id)

        classroom = None
        if room_number:
            classroom = Classroom.objects.filter(number=room_number, is_active=True).first()
            if not classroom:
                return JsonResponse({'success': False, 'error': f'Кабинет {room_number} не найден'}, status=400)
            
            occupants = ScheduleSlot.objects.filter(
                classroom=classroom,
                day_of_week=slot.day_of_week,
                time_slot=slot.time_slot,
                semester__is_active=True,
                is_active=True
            )

            if slot.stream_id:
                occupants = occupants.exclude(stream_id=slot.stream_id)
            else:
                occupants = occupants.exclude(id=slot.id)

            if occupants.exists() and not force:
                other = occupants.first()
                return JsonResponse({
                    'success': False,
                    'is_conflict': True, 
                    'error': f'Кабинет занят: {other.group.name}, {other.subject.name}'
                }, status=400)

            if not force:
                total_students = 0
                if slot.stream_id:
                    stream_slots = ScheduleSlot.objects.filter(stream_id=slot.stream_id)
                    for s in stream_slots:
                        total_students += s.group.students.count()
                else:
                    total_students = slot.group.students.count()

                if total_students > classroom.capacity:
                    return JsonResponse({
                        'success': False,
                        'is_capacity_warning': True, 
                        'error': f'Вместимость кабинета ({classroom.capacity}) меньше количества студентов ({total_students}). Продолжить?'
                    }, status=400)

        with transaction.atomic():
            if slot.stream_id:
                ScheduleSlot.objects.filter(stream_id=slot.stream_id).update(
                    room=room_number if room_number else None,
                    classroom=classroom
                )
            else:
                slot.room = room_number if room_number else None
                slot.classroom = classroom
                slot.save()

        return JsonResponse({'success': True, 'room': room_number or '?'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def delete_schedule_slot(request, slot_id):
    try:
        schedule_slot = get_object_or_404(ScheduleSlot, id=slot_id)

        if not (request.user.is_staff or hasattr(request.user, 'dean_profile')):
            return JsonResponse({'success': False, 'error': 'Нет прав'}, status=403)

        with transaction.atomic():
            if schedule_slot.stream_id:
                count = ScheduleSlot.objects.filter(stream_id=schedule_slot.stream_id).delete()[0]
                msg = f'Удален поток ({count} групп)'
            else:
                schedule_slot.delete()
                msg = 'Занятие удалено'

        return JsonResponse({'success': True, 'message': msg})

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка: {str(e)}'}, status=500)

@login_required
def schedule_view(request):
    user = request.user
    group = None

    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                active_semester = get_active_semester_for_group(group)
            else:
                active_semester = None
        except Student.DoesNotExist:
            active_semester = None
    else:
        active_semester = Semester.objects.filter(is_active=True).first()

    if not active_semester:
        messages.warning(request, 'Активный семестр не найден.')
        return render(request, 'schedule/no_semester.html')

    if user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            group_ids = ScheduleSlot.objects.filter(
                teacher=teacher, semester=active_semester, is_active=True
            ).values_list('group_id', flat=True).distinct()

            groups = Group.objects.filter(id__in=group_ids)
            group_id = request.GET.get('group')

            if group_id:
                group = get_object_or_404(Group, id=group_id, id__in=group_ids)

            context = {'groups': groups, 'group': group, 'active_semester': active_semester}
            if not group:
                return render(request, 'schedule/schedule_view_unified.html', context)

        except Teacher.DoesNotExist:
            pass

    elif user.role == 'DEAN':
        group_id = request.GET.get('group')
        groups = Group.objects.all()

        if group_id:
            group = get_object_or_404(Group, id=group_id)
            active_semester = get_active_semester_for_group(group)
            if not active_semester:
                messages.warning(request, f'Нет активного семестра для {group.course} курса')

        context = {'groups': groups, 'group': group, 'active_semester': active_semester}
        if not group:
            return render(request, 'schedule/schedule_view_unified.html', context)

    if group and active_semester:
        time_slots = get_time_slots_for_shift(active_semester.shift)
        days = [(0, 'ДУШАНБЕ'), (1, 'СЕШАНБЕ'), (2, 'ЧОРШАНБЕ'), (3, 'ПАНҶШАНБЕ'), (4, 'ҶУМЪА'), (5, 'ШАНБЕ')]
        valid_slot_ids = list(time_slots.values_list('id', flat=True))

        slots = ScheduleSlot.objects.filter(
            group=group,
            semester=active_semester,
            time_slot_id__in=valid_slot_ids,
            is_active=True
        ).select_related('subject', 'teacher__user', 'time_slot')

        schedule_data = {group.id: {}}
        for slot in slots:
            if slot.day_of_week not in schedule_data[group.id]:
                schedule_data[group.id][slot.day_of_week] = {}
            schedule_data[group.id][slot.day_of_week][slot.time_slot.id] = slot

        return render(request, 'schedule/schedule_view_unified.html', {
            'group': group, 'groups': Group.objects.all() if user.role == 'DEAN' else None,
            'days': days, 'time_slots': time_slots, 'schedule_data': schedule_data,
            'active_semester': active_semester, 'is_view_mode': True,
        })

    return render(request, 'schedule/schedule_view_unified.html', {
        'groups': Group.objects.all() if user.role == 'DEAN' else None,
        'active_semester': active_semester,
    })

@login_required
def today_classes(request):
    user = request.user
    today = datetime.now()
    day_of_week = today.weekday()
    current_time = today.time()

    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            if student.group:
                active_semester = get_active_semester_for_group(student.group)
            else:
                active_semester = None
        except:
            active_semester = None
    else:
        active_semester = Semester.objects.filter(is_active=True).first()

    classes = []
    if not active_semester:
        return render(request, 'schedule/today_widget.html', {'classes': classes, 'current_time': current_time, 'today': today})

    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            if student.group:
                classes = ScheduleSlot.objects.filter(
                    group=student.group, semester=active_semester,
                    day_of_week=day_of_week, is_active=True
                ).select_related('subject', 'teacher__user').order_by('start_time')
        except Student.DoesNotExist:
            pass

    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            classes = ScheduleSlot.objects.filter(
                teacher=teacher, semester=active_semester,
                day_of_week=day_of_week, is_active=True
            ).select_related('subject', 'group').order_by('start_time')
        except Teacher.DoesNotExist:
            pass

    return render(request, 'schedule/today_widget.html', {
        'classes': classes, 'current_time': current_time, 'today': today
    })

@user_passes_test(is_dean)
def manage_subjects(request):
    subjects = Subject.objects.all().select_related('teacher__user')
    search = request.GET.get('search', '')
    if search:
        subjects = subjects.filter(Q(name__icontains=search) | Q(code__icontains=search))
    return render(request, 'schedule/manage_subjects.html', {'subjects': subjects, 'search': search})

@user_passes_test(is_dean)
def add_subject(request):
    initial_data = {}
    dept_id = request.GET.get('department')

    target_department = None
    if dept_id:
        target_department = get_object_or_404(Department, id=dept_id)
        if request.user.role == 'DEAN':
            if target_department.faculty != request.user.dean_profile.faculty:
                messages.error(request, "Нет доступа к этой кафедре")
                return redirect('schedule:manage_subjects')

        initial_data['department'] = target_department
        initial_data['assign_to_all_groups'] = True

    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)

            if target_department and not subject.department_id:
                subject.department = target_department

            subject.save()
            form.save_m2m()  
            if form.cleaned_data.get('assign_to_all_groups') and subject.department:
                dept_groups = Group.objects.filter(specialty__department=subject.department)
                subject.groups.add(*dept_groups)

            messages.success(request, f'Предмет "{subject.name}" создан')
            if dept_id:
                return redirect('accounts:manage_structure')
            return redirect('schedule:manage_subjects')
        else:
            print("Ошибки формы предмета:", form.errors)
    else:
        form = SubjectForm(initial=initial_data)

        if target_department:
            form.fields['teacher'].queryset = Teacher.objects.filter(
                Q(department=target_department) | Q(additional_departments=target_department)
            ).distinct()
            form.fields['department'].queryset = Department.objects.filter(id=target_department.id)
        elif request.user.role == 'DEAN':
            faculty = request.user.dean_profile.faculty
            form.fields['department'].queryset = Department.objects.filter(faculty=faculty)
            form.fields['teacher'].queryset = Teacher.objects.filter(
                Q(department__faculty=faculty) | Q(additional_departments__faculty=faculty)
            ).distinct()

    return render(request, 'schedule/subject_form.html', {'form': form, 'title': 'Добавить предмет'})



@user_passes_test(is_dean)
def edit_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, 'Предмет обновлен')
            return redirect('schedule:manage_subjects')
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'schedule/subject_form.html', {'form': form, 'subject': subject, 'title': 'Редактировать предмет'})

@user_passes_test(is_dean)
def delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    subject.delete()
    messages.success(request, 'Предмет удален')
    return redirect('schedule:manage_subjects')

@user_passes_test(is_dean)
def manage_semesters(request):
    semesters = Semester.objects.all().order_by('-academic_year', 'course', 'number')

    active_by_course = Semester.objects.filter(is_active=True).values_list('course', flat=True)
    missing_courses = [c for c, _ in Semester.COURSE_CHOICES if c not in active_by_course]

    return render(request, 'schedule/manage_semesters.html', {
        'semesters': semesters,
        'missing_courses': missing_courses
    })

@user_passes_test(is_dean)
def add_semester(request):
    if request.method == 'POST':
        form = SemesterForm(request.POST, user=request.user)
        if form.is_valid():
            semester = form.save(commit=False)
            semester.save() 
            
            dept = form.cleaned_data.get('department_filter')
            course = form.cleaned_data.get('course')
            
            if dept and course:
                dept_groups = Group.objects.filter(specialty__department=dept, course=course)
                semester.groups.add(*dept_groups)
            
            form.save_m2m()
            
            messages.success(request, f'Семестр "{semester.name}" создан')
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm(user=request.user)
        
    return render(request, 'schedule/semester_form.html', {'form': form, 'title': 'Добавить семестр'})

@user_passes_test(is_dean)
def edit_semester(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if request.method == 'POST':
        form = SemesterForm(request.POST, instance=semester, user=request.user)
        if form.is_valid():
            semester = form.save(commit=False)
            semester.save()
            
            dept = form.cleaned_data.get('department_filter')
            course = form.cleaned_data.get('course')
            
            if dept and course:
                dept_groups = Group.objects.filter(specialty__department=dept, course=course)
                semester.groups.add(*dept_groups)
                
            form.save_m2m()
            messages.success(request, 'Семестр обновлен')
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm(instance=semester, user=request.user)
        
    return render(request, 'schedule/semester_form.html', {'form': form, 'semester': semester, 'title': 'Редактировать семестр'})

@user_passes_test(is_dean)
def toggle_semester_active(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    semester.is_active = not semester.is_active
    semester.save()
    status = "активирован" if semester.is_active else "деактивирован"
    messages.success(request, f'Семестр {status}')
    return redirect('schedule:manage_semesters')

@user_passes_test(is_dean)
def manage_classrooms(request):
    classrooms = Classroom.objects.all().order_by('floor', 'number')
    return render(request, 'schedule/manage_classrooms.html', {'classrooms': classrooms})

@user_passes_test(is_dean)
def add_classroom(request):
    if request.method == 'POST':
        form = ClassroomForm(request.POST)
        if form.is_valid():
            classroom = form.save()
            messages.success(request, f'Кабинет {classroom.number} добавлен')
            return redirect('schedule:manage_classrooms')
    else:
        form = ClassroomForm()
    return render(request, 'schedule/classroom_form.html', {'form': form, 'title': 'Добавить кабинет'})

@user_passes_test(is_dean)
def bulk_add_classrooms(request):
    if request.method == 'POST':
        form = BulkClassroomForm(request.POST)
        if form.is_valid():
            floor = form.cleaned_data['floor']
            start = form.cleaned_data['start_number']
            end = form.cleaned_data['end_number']
            capacity = form.cleaned_data['capacity']

            created = 0
            for num in range(start, end + 1):
                number = f"{num}"
                if not Classroom.objects.filter(number=number).exists():
                    Classroom.objects.create(number=number, floor=floor, capacity=capacity)
                    created += 1

            messages.success(request, f'Создано {created} кабинетов')
            return redirect('schedule:manage_classrooms')
    else:
        form = BulkClassroomForm()
    return render(request, 'schedule/bulk_classroom_form.html', {'form': form})

@user_passes_test(is_dean)
def delete_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)
    classroom.delete()
    messages.success(request, f'Кабинет {classroom.number} удален')
    return redirect('schedule:manage_classrooms')

@user_passes_test(is_dean)
def manage_academic_week(request):
    active_semester = Semester.objects.filter(is_active=True).first()
    current_week = AcademicWeek.get_current()

    if request.method == 'POST':
        form = AcademicWeekForm(request.POST, instance=current_week)
        if form.is_valid():
            week = form.save(commit=False)
            if active_semester:
                week.semester = active_semester
                AcademicWeek.objects.filter(is_current=True).update(is_current=False)
                week.is_current = True

                semester_start = form.cleaned_data['semester_start_date']
                week_num = form.cleaned_data['current_week']

                week.start_date = semester_start + timedelta(weeks=week_num - 1)
                week.end_date = week.start_date + timedelta(days=6)
                week.week_number = week_num

                week.save()
                messages.success(request, f'Учебная неделя {week_num} установлена')
            else:
                messages.error(request, 'Сначала создайте семестр')
            return redirect('schedule:manage_academic_week')
    else:
        initial = {}
        if current_week:
            initial = {
                'semester_start_date': current_week.semester.start_date if current_week.semester else None,
                'current_week': current_week.week_number
            }
        form = AcademicWeekForm(initial=initial)

    return render(request, 'schedule/manage_academic_week.html', {
        'form': form, 'current_week': current_week, 'active_semester': active_semester
    })

@login_required
def group_list(request):
    user = request.user

    if user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            active_semester = Semester.objects.filter(is_active=True).first()
            if active_semester:
                group_ids = ScheduleSlot.objects.filter(
                    teacher=teacher, semester=active_semester, is_active=True
                ).values_list('group_id', flat=True).distinct()
                groups = Group.objects.filter(id__in=group_ids)
            else:
                groups = Group.objects.none()
        except Teacher.DoesNotExist:
            groups = Group.objects.none()
    elif user.role == 'DEAN':
        groups = Group.objects.all()
    else:
        messages.error(request, 'Доступ запрещен')
        return redirect('core:dashboard')

    groups_with_students = []
    for group in groups:
        students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
        groups_with_students.append({'group': group, 'students': students})

    return render(request, 'schedule/group_list.html', {'groups_with_students': groups_with_students})

@login_required
def export_schedule(request):
    if not DOCX_AVAILABLE:
        return HttpResponse("Library python-docx not installed", status=500)

    group_id = request.GET.get('group')
    group = get_object_or_404(Group, id=group_id)
    active_semester = get_active_semester_for_group(group)
    
    if not active_semester:
        return HttpResponse("Нет активного семестра", status=400)

    try:
        specialty = group.specialty
        department = specialty.department
        faculty = department.faculty
        institute = faculty.institute
    except AttributeError:
        return HttpResponse("Ошибка структуры: Группа не привязана корректно.", status=400)

    director_user = None
    director_obj = Director.objects.filter(institute=institute).first()
    if director_obj:
        director_user = director_obj.user
    
    vice_user = None
    vice_obj = ProRector.objects.filter(institute=institute, title__icontains='таълим').first()
    if not vice_obj:
        vice_obj = ProRector.objects.filter(institute=institute).first()
    
    if vice_obj:
        vice_user = vice_obj.user

    director_name = director_user.get_full_name() if director_user else "Мирзозода А. Н." 
    vice_name = vice_user.get_full_name() if vice_user else "Ҷовиди Ҷамшед" 
    
    head_edu_name = "Ҷалилов Р.Р." 

    doc = Document()
    
    section = doc.sections[0]
    section.left_margin = Cm(1.0)
    section.right_margin = Cm(1.0)
    section.top_margin = Cm(1.0)
    section.bottom_margin = Cm(1.0)

    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = True
    header_table.width = section.page_width - section.left_margin - section.right_margin
    
    c1 = header_table.cell(0, 0)
    p1 = c1.paragraphs[0]
    p1.add_run("Мувофиқа карда шуд:\n").bold = True
    p1.add_run("Сардори раёсати таълим\n")
    p1.add_run(f"________ дотсент {head_edu_name}\n")
    p1.add_run("«___» _________ 2025с")
    
    c2 = header_table.cell(0, 1)
    p2 = c2.paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p2.add_run("Тасдиқ мекунам:\n").bold = True
    p2.add_run("Муовини директор\nоид ба корҳои таълимӣ\n").bold = False
    p2.add_run(f"________ дотсент {vice_name}\n")
    p2.add_run("«___»_________ 2025c")

    doc.add_paragraph() 

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_p.add_run("ҶАДВАЛИ ДАРСӢ")
    run.bold = True
    run.font.size = Pt(16)
    run.font.name = 'Times New Roman'

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sem_text = "якуми" if active_semester.number == 1 else "дуюми"
    year_text = active_semester.academic_year
    
    text = f"дар нимсолаи {sem_text} соли таҳсили {year_text} барои донишҷӯёни курси {group.course}-юми " \
           f"{institute.name}-и Донишгоҳи байналмилаии сайёҳӣ ва соҳибкории Тоҷикистон"
    
    run_sub = subtitle.add_run(text)
    run_sub.font.name = 'Times New Roman'
    run_sub.font.size = Pt(12)
    run_sub.bold = True
    
    shift_num = "1" if active_semester.shift == "MORNING" else "2"
    shift_p = doc.add_paragraph(f"(БАСТИ {shift_num})")
    shift_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    shift_p.runs[0].bold = True
    shift_p.runs[0].font.size = Pt(14)

    table = doc.add_table(rows=1, cols=4)
    table.style = 'Table Grid'
    
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "ҲАФТА"
    hdr_cells[1].text = "СОАТ"
    
    hdr_cells[2].text = f"{specialty.code} – “{specialty.name}” ({group.students.count()} нафар)"
    hdr_cells[3].text = "АУД"
    
    for cell in hdr_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:val'), 'clear')
        shading_elm.set(qn('w:color'), 'auto')
        shading_elm.set(qn('w:fill'), 'D9D9D9') # Серый цвет
        cell._tc.get_or_add_tcPr().append(shading_elm)
        
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(10)

    time_slots = get_time_slots_for_shift(active_semester.shift)
    days = [(0, 'ДУШАНБЕ'), (1, 'СЕШАНБЕ'), (2, 'ЧОРШАНБЕ'), (3, 'ПАНҶШАНБЕ'), (4, 'ҶУМЪА'), (5, 'ШАНБЕ')]

    for day_num, day_name in days:
        is_military_day = ScheduleSlot.objects.filter(
            group=group, semester=active_semester, day_of_week=day_num, is_military=True
        ).exists()

        first_row_idx = len(table.rows) 

        for ts in time_slots:
            row = table.add_row()
            row.cells[1].text = f'{ts.start_time.strftime("%H:%M")}-{ts.end_time.strftime("%H:%M")}'
            row.cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            row.cells[1].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            row.cells[1].paragraphs[0].runs[0].font.bold = True
            
            if not is_military_day:
                slot = ScheduleSlot.objects.filter(
                    group=group, semester=active_semester, day_of_week=day_num, time_slot=ts, is_active=True
                ).first()
                
                if slot:
                    cell = row.cells[2]
                    p = cell.paragraphs[0]
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.add_run(f"{slot.subject.name} ({slot.get_lesson_type_display()})\n")
                    if slot.teacher:
                        p.add_run(f"{slot.teacher.user.get_full_name()}")
                    
                    cell_aud = row.cells[3]
                    cell_aud.text = slot.room if slot.room else ""
                    cell_aud.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cell_aud.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        day_cell = table.rows[first_row_idx].cells[0]
        day_cell.text = day_name
        day_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        tcPr = day_cell._tc.get_or_add_tcPr()
        textDirection = OxmlElement('w:textDirection')
        textDirection.set(qn('w:val'), 'btLr') # Bottom to Top
        tcPr.append(textDirection)
        
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:val'), 'clear')
        shading_elm.set(qn('w:color'), 'auto')
        shading_elm.set(qn('w:fill'), 'D9D9D9')
        tcPr.append(shading_elm)

        last_row_idx = len(table.rows) - 1
        if last_row_idx > first_row_idx:
            day_cell.merge(table.rows[last_row_idx].cells[0])

        if is_military_day:
            mil_cell = table.rows[first_row_idx].cells[2]
            
            mil_cell.merge(table.rows[first_row_idx].cells[3])
            
            if last_row_idx > first_row_idx:
                mil_cell.merge(table.rows[last_row_idx].cells[3]) 
            
            mil_cell.text = "Кафедраи ҳарбӣ"
            
            for paragraph in mil_cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(48) 
                    run.font.name = 'Times New Roman'
            mil_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    doc.add_paragraph().add_run('\n')
    
    footer_table = doc.add_table(rows=1, cols=2)
    footer_table.autofit = True
    footer_table.width = section.page_width
    
    f_c1 = footer_table.cell(0, 0)
    fp1 = f_c1.paragraphs[0]
    fp1.add_run("Директор").bold = True
    
    f_c2 = footer_table.cell(0, 1)
    fp2 = f_c2.paragraphs[0]
    fp2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fp2.add_run(f"{director_name}").bold = True

    f = BytesIO()
    doc.save(f)
    f.seek(0)
    
    filename = f"Jadval_{group.name}.docx"
    response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response



@user_passes_test(is_dean)
def manage_plans(request):
    plans = AcademicPlan.objects.all().select_related('specialty')
    
    if request.user.role == 'DEAN':
        faculty = request.user.dean_profile.faculty
        plans = plans.filter(specialty__department__faculty=faculty)
        
    return render(request, 'schedule/plans/manage_plans.html', {'plans': plans})


@user_passes_test(is_dean)
def create_plan(request):
    from .forms import AcademicPlanForm
    if request.method == 'POST':
        form = AcademicPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            return redirect('schedule:plan_detail', plan_id=plan.id)
    else:
        form = AcademicPlanForm()
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Создать РУП'})


@user_passes_test(is_dean)
def plan_detail(request, plan_id):
    plan = get_object_or_404(AcademicPlan, id=plan_id)
    
    if request.user.role == 'DEAN':
        if plan.specialty.department.faculty != request.user.dean_profile.faculty:
            messages.error(request, "Нет доступа к этому плану")
            return redirect('schedule:manage_plans')

    disciplines = PlanDiscipline.objects.filter(plan=plan).order_by('semester_number', 'discipline_type')
    
    if request.method == 'POST':
        form = PlanDisciplineForm(request.POST)
        if form.is_valid():
            disc = form.save(commit=False)
            disc.plan = plan
            disc.save()
            messages.success(request, "Дисциплина добавлена")
            return redirect('schedule:plan_detail', plan_id=plan.id)
    else:
        form = PlanDisciplineForm()
    
    return render(request, 'schedule/plans/plan_detail.html', {
        'plan': plan, 
        'disciplines': disciplines, 
        'form': form,
        'semesters_range': range(1, 9) 
    })



@user_passes_test(is_dean)
def generate_subjects_from_rup(request):
    active_semester = Semester.objects.filter(is_active=True).first()
    if not active_semester:
        messages.error(request, "Нет активного семестра! Сначала активируйте семестр.")
        return redirect('schedule:manage_semesters')

    groups = Group.objects.all()
    if request.user.role == 'DEAN':
        groups = groups.filter(specialty__department__faculty=request.user.dean_profile.faculty)

    suggestions = {}

    for group in groups:
        current_semester_num = (group.course - 1) * 2 + active_semester.number

        plan = AcademicPlan.objects.filter(specialty=group.specialty, is_active=True).order_by('-admission_year').first()

        if not plan:
            continue

        disciplines = PlanDiscipline.objects.filter(plan=plan, semester_number=current_semester_num)

        for disc in disciplines:
            exists = Subject.objects.filter(
                plan_discipline=disc,
                groups=group
            ).exists()

            if exists:
                continue

            key = f"{disc.subject_template.id}_{disc.id}"

            if key not in suggestions:
                suggestions[key] = {
                    'template': disc.subject_template,
                    'discipline': disc,
                    'groups': [],
                    'hours': f"{disc.lecture_hours}/{disc.practice_hours}/{disc.control_hours}"
                }

            suggestions[key]['groups'].append(group)

    if request.method == 'POST':
        created_count = 0
        with transaction.atomic():
            selected_keys = request.POST.getlist('selected_items')

            for key in selected_keys:
                if key in suggestions:
                    item = suggestions[key]
                    disc = item['discipline']
                    group_list = item['groups']

                    is_stream = len(group_list) > 1 and request.POST.get(f'make_stream_{key}') == 'on'

                    if is_stream:
                        subject = Subject.objects.create(
                            name=disc.subject_template.name,
                            code=f"{disc.subject_template.id}-{active_semester.academic_year}-STREAM",
                            department=group_list[0].specialty.department,
                            type='LECTURE',
                            lecture_hours=disc.lecture_hours,
                            practice_hours=disc.practice_hours,
                            control_hours=disc.control_hours,
                            independent_work_hours=disc.independent_hours,
                            credits=disc.credits,
                            plan_discipline=disc,
                            is_stream_subject=True
                        )
                        subject.groups.set(group_list)
                        created_count += 1
                    else:
                        for grp in group_list:
                            subject = Subject.objects.create(
                                name=disc.subject_template.name,
                                code=f"{disc.subject_template.id}-{grp.name}-{active_semester.academic_year}",
                                department=grp.specialty.department,
                                type='LECTURE',
                                lecture_hours=disc.lecture_hours,
                                practice_hours=disc.practice_hours,
                                control_hours=disc.control_hours,
                                independent_work_hours=disc.independent_hours,
                                credits=disc.credits,
                                plan_discipline=disc,
                                is_stream_subject=False
                            )
                            subject.groups.add(grp)
                            created_count += 1

        messages.success(request, f"Создано предметов: {created_count}")
        return redirect('schedule:manage_subjects')

    return render(request, 'schedule/plans/generate_preview.html', {
        'suggestions': suggestions.values(),
        'semester': active_semester
    })



@user_passes_test(is_dean)
def edit_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)
    if request.method == 'POST':
        form = ClassroomForm(request.POST, instance=classroom)
        if form.is_valid():
            form.save()
            messages.success(request, f'Кабинет {classroom.number} обновлен')
            return redirect('schedule:manage_classrooms')
    else:
        form = ClassroomForm(instance=classroom)
    return render(request, 'schedule/classroom_form.html', {
        'form': form, 
        'title': f'Редактировать кабинет {classroom.number}'
    })

@user_passes_test(is_dean)
def classroom_occupancy(request):
    day = int(request.GET.get('day', 0)) 
    active_semester = Semester.objects.filter(is_active=True).first()
    
    if not active_semester:
        messages.error(request, "Нет активного семестра")
        return redirect('schedule:manage_classrooms')

    classrooms = Classroom.objects.filter(is_active=True).order_by('floor', 'number')
    time_slots = TimeSlot.objects.all().order_by('start_time')
    
    days = [
        (0, 'Понедельник'), (1, 'Вторник'), (2, 'Среда'),
        (3, 'Четверг'), (4, 'Пятница'), (5, 'Суббота')
    ]

    slots = ScheduleSlot.objects.filter(
        semester=active_semester,
        day_of_week=day,
        is_active=True,
        classroom__isnull=False
    ).select_related('classroom', 'group', 'subject', 'time_slot')

    occupancy = {}
    for slot in slots:
        c_id = slot.classroom.id
        t_id = slot.time_slot.id
        if c_id not in occupancy:
            occupancy[c_id] = {}
        occupancy[c_id][t_id] = slot

    return render(request, 'schedule/classroom_occupancy.html', {
        'classrooms': classrooms,
        'time_slots': time_slots,
        'occupancy': occupancy,
        'selected_day': day,
        'days': days
    })


@login_required
def import_schedule_view(request):
    if not (request.user.role in ['DEAN', 'VICE_DEAN'] or request.user.is_superuser):
        messages.error(request, "Доступ запрещен")
        return redirect('schedule:view')

    if request.method == 'POST' and 'confirm_import' in request.POST:
        semester_id = request.POST.get('semester_id')
        semester = Semester.objects.get(id=semester_id)

        all_keys = [k for k in request.POST.keys() if k.startswith('item_') and k.endswith('_group_id')]
        if not all_keys:
            messages.error(request, "Нет данных для сохранения")
            return redirect('schedule:view')

        import_data = []

        for key in all_keys:
            index = key.split('_')[1]
            prefix = f'item_{index}_'

            group_id = request.POST.get(f'{prefix}group_id')
            if not group_id: continue  
            import_data.append({
                'group_id': group_id,
                'day': request.POST.get(f'{prefix}day'),
                'start_time': request.POST.get(f'{prefix}start_time'),
                'end_time': request.POST.get(f'{prefix}end_time'),
                'subject': request.POST.get(f'{prefix}subject'),
                'teacher': request.POST.get(f'{prefix}teacher'),
                'room': request.POST.get(f'{prefix}room'),
                'type': request.POST.get(f'{prefix}type'),
                'is_military': request.POST.get(f'{prefix}is_military'),
            })

        importer = ScheduleImporter()
        stats = importer.save_data_from_preview(import_data, semester)
        messages.success(request, f"✅ Импорт завершен! Слотов: {stats['slots']}, Новых предметов: {stats['subjects']}, Новых учителей: {stats['teachers']}")
        return redirect('schedule:view')

    elif request.method == 'POST':
        form = ScheduleImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                importer = ScheduleImporter(file=request.FILES['file'])
                preview_data = importer.parse_for_preview(default_group=form.cleaned_data['default_group'])

                if not preview_data:
                    messages.warning(request, "Данные не найдены в файле или формат некорректен.")
                    return redirect('schedule:import_schedule')

                context = {
                    'preview_data': preview_data,
                    'semester': form.cleaned_data['semester'],
                    'days_map_rev': {0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 3: 'Четверг', 4: 'Пятница', 5: 'Суббота'}
                }
                return render(request, 'schedule/import_preview_edit.html', context)

            except Exception as e:
                messages.error(request, f"Ошибка обработки файла: {str(e)}")

    else:
        form = ScheduleImportForm()

    return render(request, 'schedule/import_schedule.html', {'form': form})

@login_required
@require_POST
def api_create_subject_template(request):
    
    import json
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        
        if not name:
            return JsonResponse({'success': False, 'error': 'Название не может быть пустым'})
            
        if SubjectTemplate.objects.filter(name__iexact=name).exists():
            return JsonResponse({'success': False, 'error': 'Такая дисциплина уже существует'})
            
        template = SubjectTemplate.objects.create(name=name)
        
        return JsonResponse({
            'success': True,
            'id': template.id,
            'name': template.name
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(is_dean)
def copy_plan(request, plan_id):
    original_plan = get_object_or_404(AcademicPlan, id=plan_id)
    
    if request.method == 'POST':
        new_year = request.POST.get('new_year')
        if not new_year:
            messages.error(request, "Укажите новый год")
            return redirect('schedule:manage_plans')
            
        if AcademicPlan.objects.filter(specialty=original_plan.specialty, admission_year=new_year).exists():
            messages.error(request, f"План для {original_plan.specialty.code} на {new_year} год уже существует!")
            return redirect('schedule:manage_plans')

        with transaction.atomic():
            new_plan = AcademicPlan.objects.create(
                specialty=original_plan.specialty,
                admission_year=new_year,
                is_active=True
            )
            
            disciplines = original_plan.disciplines.all()
            new_disciplines = []
            for disc in disciplines:
                disc.pk = None 
                disc.plan = new_plan
                new_disciplines.append(disc)
            
            PlanDiscipline.objects.bulk_create(new_disciplines)
            
        messages.success(request, f"План успешно скопирован на {new_year} год!")
        return redirect('schedule:plan_detail', plan_id=new_plan.id)
        
    return redirect('schedule:manage_plans')



@user_passes_test(is_dean)
def delete_plan_discipline(request, discipline_id):
    discipline = get_object_or_404(PlanDiscipline, id=discipline_id)
    plan_id = discipline.plan.id
    
    if request.user.role == 'DEAN':
        if discipline.plan.specialty.department.faculty != request.user.dean_profile.faculty:
            messages.error(request, "Нет прав на удаление")
            return redirect('schedule:plan_detail', plan_id=plan_id)

    discipline.delete()
    messages.success(request, "Дисциплина удалена из плана")
    return redirect('schedule:plan_detail', plan_id=plan_id)



