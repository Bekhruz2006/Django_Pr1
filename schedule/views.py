from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.db import transaction
from datetime import datetime, timedelta, date
import json
import uuid
from io import BytesIO 
from django.db.models import Q, Sum
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
from django import forms
from .models import Subject, ScheduleSlot, Semester, Classroom, TimeSlot, AcademicPlan, PlanDiscipline, SubjectTemplate, SubjectMaterial, Building, Institute
from .forms import SubjectForm, RupImportForm, SemesterForm, ClassroomForm, BulkClassroomForm, TimeSlotGeneratorForm, MaterialUploadForm, ScheduleImportForm, AcademicPlanForm, PlanDisciplineForm, SubjectTemplateForm, BuildingForm
from .services import ScheduleImporter, RupImporter
from accounts.models import Group, Student, Teacher, Director, ProRector, Department
import math
from django.utils.translation import gettext as _

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
def is_dean_or_admin(user):
    return user.is_authenticated and (
        user.is_superuser or 
        user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR', 'DEAN', 'VICE_DEAN']
    )

def get_active_semester_for_group(group):
    if group and group.specialty and group.specialty.department.faculty:
        faculty = group.specialty.department.faculty
        semester = Semester.objects.filter(faculty=faculty, is_active=True, course=group.course).first()
        if semester:
            return semester
    semester = Semester.objects.filter(course=group.course, is_active=True).first()
    if not semester:
        semester = Semester.objects.filter(is_active=True).first()
        
    return semester

@login_required
def schedule_constructor(request):
    if not is_dean_or_admin(request.user):
        messages.error(request, _("Доступ запрещен"))
        return redirect('core:dashboard')

    semester_id = request.GET.get('semester')
    active_semester = None

    if semester_id:
        active_semester = get_object_or_404(Semester, id=semester_id)
    else:
        if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
            faculty = request.user.dean_profile.faculty
            active_semester = Semester.objects.filter(faculty=faculty, is_active=True).first()

        if not active_semester:
            active_semester = Semester.objects.filter(is_active=True).first()

    if not active_semester:
        active_semester = Semester.objects.order_by('-start_date').first()
        if not active_semester:
            messages.warning(request, _('Сначала создайте семестр в настройках.'))
            return redirect('schedule:manage_semesters')

    groups = Group.objects.all().select_related('specialty').order_by('course', 'name')

    if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        groups = groups.filter(specialty__department__faculty=faculty)

    selected_group_id = request.GET.get('group')
    selected_group = None
    schedule_data = {}
    subjects_to_schedule = []

    if selected_group_id:
        selected_group = get_object_or_404(Group, id=selected_group_id)

        slots = ScheduleSlot.objects.filter(
            group=selected_group,
            semester=active_semester,
            is_active=True
        ).select_related('subject', 'teacher__user', 'time_slot', 'classroom')

        schedule_data = {}
        for slot in slots:
            if slot.day_of_week not in schedule_data:
                schedule_data[slot.day_of_week] = {}
            schedule_data[slot.day_of_week][slot.time_slot.id] = slot

        assigned_subjects = Subject.objects.filter(groups=selected_group).select_related('teacher__user').distinct()

        for subject in assigned_subjects:
            needed = subject.get_weekly_slots_needed()

            for l_type, label, color in [('LECTURE', _('Лекция'), 'primary'), ('PRACTICE', _('Практика'), 'success'), ('SRSP', _('СРСП'), 'warning')]:
                if needed[l_type] > 0:
                    scheduled_count = slots.filter(subject=subject, lesson_type=l_type).count()
                    remaining = max(0, needed[l_type] - scheduled_count)

                    if remaining > 0:
                        subjects_to_schedule.append({
                            'obj': subject,
                            'type': l_type,
                            'label': label,
                            'remaining': remaining,
                            'color': color
                        })

    time_slots = []
    if selected_group:
        try:
            if selected_group.specialty:
                institute = selected_group.specialty.department.faculty.institute
            elif hasattr(request.user, 'dean_profile'):
                institute = request.user.dean_profile.faculty.institute
            else:
                institute = Institute.objects.first()
                
            shift = active_semester.shift
            time_slots = TimeSlot.objects.filter(
                institute=institute,
                shift=shift
            ).order_by('start_time')
        except AttributeError:
            time_slots = TimeSlot.objects.none()
    else:
        time_slots = TimeSlot.objects.none()

    days = [(0, _('Понедельник')), (1, _('Вторник')), (2, _('Среда')), (3, _('Четверг')), (4, _('Пятница')), (5, _('Суббота'))]
    all_semesters = Semester.objects.all().order_by('-is_active', '-start_date')
    if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        all_semesters = all_semesters.filter(faculty=request.user.dean_profile.faculty)

    return render(request, 'schedule/constructor_with_limits.html', {
        'groups': groups,
        'group': selected_group,
        'semester': active_semester,
        'all_semesters': all_semesters,
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
                    'name': _("Кафедраи ҳарбӣ (Военная кафедра)"),
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
                        classroom=None,
                        room=_("Воен. каф")
                    )
                    created_count += 1

            return JsonResponse({'success': True, 'message': _('Назначено %(created_count)s часов военной кафедры') % {'created_count': created_count}})

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
            return JsonResponse({'success': False, 'error': _('Нет активного семестра')}, status=400)

        start_h = time_slot.start_time.hour
        if active_semester.shift == 'MORNING' and start_h >= 13:
            return JsonResponse({'success': False, 'error': _('Ошибка смены: Слот ДНЕВНОЙ, а семестр УТРЕННИЙ.')}, status=400)
        if active_semester.shift == 'DAY' and start_h < 13:
            return JsonResponse({'success': False, 'error': _('Ошибка смены: Слот УТРЕННИЙ, а семестр ДНЕВНОЙ.')}, status=400)

        groups_to_schedule = [main_group]
        is_stream = False
        stream_id = None

        if lesson_type == 'LECTURE' and subject.groups.count() > 1:
            all_subject_groups = list(subject.groups.all())
            if len(all_subject_groups) > 3:
                return JsonResponse({'success': False, 'error': _('Слишком большой поток! Максимум 3 группы.')}, status=400)
            groups_to_schedule = all_subject_groups
            is_stream = True
            stream_id = uuid.uuid4()

        conflicts = []
        if not force:
            for target_group in groups_to_schedule:
                busy_group = ScheduleSlot.objects.filter(
                    group=target_group,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    semester=active_semester,
                    is_active=True
                ).first()
                if busy_group:
                    conflicts.append(f"❌ Группа <b>{busy_group.group.name}</b> уже занята: {busy_group.subject.name} ({busy_group.room or 'каб?'})")

            if subject.teacher:
                busy_teacher = ScheduleSlot.objects.filter(
                    teacher=subject.teacher,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    semester=active_semester,
                    is_active=True
                ).first()
                if busy_teacher:
                    conflicts.append(f"❌ Преподаватель <b>{subject.teacher.user.get_full_name()}</b> занят в группе {busy_teacher.group.name} ({busy_teacher.room or 'каб?'})")

        if conflicts:
            return JsonResponse({
                'success': False,
                'is_conflict': True,
                'error': "<br>".join(conflicts)
            }, status=400)

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
        return JsonResponse({'success': False, 'error': _("Ошибка сервера: %(error)s") % {'error': str(e)}}, status=500)


@login_required
@require_POST
def update_schedule_room(request, slot_id):
    try:
        data = json.loads(request.body)
        room_number = data.get('room', '').strip()
        force = data.get('force', False)

        slot = get_object_or_404(ScheduleSlot, id=slot_id)

        classroom = None
        if room_number:
            candidates = Classroom.objects.filter(number=room_number, is_active=True)

            if candidates.count() == 0:
                return JsonResponse({'success': False, 'error': _('Кабинет %(num)s не найден в базе') % {'num': room_number}}, status=400)
            elif candidates.count() == 1:
                classroom = candidates.first()
            else:
                try:
                    group_institute = slot.group.specialty.department.faculty.institute
                    classroom = candidates.filter(building__institute=group_institute).first()
                except:
                    pass

                if not classroom:
                    classroom = candidates.first()

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
                    'error': _('Конфликт в %(building)s, каб. %(num)s! Там уже сидит: %(group)s (%(subject)s)') % {
                        'building': classroom.building.name if classroom.building else "Корпус?",
                        'num': classroom.number,
                        'group': other.group.name,
                        'subject': other.subject.name
                    }
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
                        'error': _('Вместимость кабинета (%(capacity)s) меньше количества студентов (%(students)s). Продолжить?') % {'capacity': classroom.capacity, 'students': total_students}
                    }, status=400)

        with transaction.atomic():
            if slot.stream_id:
                ScheduleSlot.objects.filter(stream_id=slot.stream_id).update(
                    room=classroom.number if classroom else room_number,
                    classroom=classroom
                )
            else:
                slot.room = classroom.number if classroom else room_number
                slot.classroom = classroom
                slot.save()

        display_name = str(classroom) if classroom else room_number
        return JsonResponse({'success': True, 'room': display_name})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def delete_schedule_slot(request, slot_id):
    try:
        schedule_slot = get_object_or_404(ScheduleSlot, id=slot_id)

        if not (request.user.is_staff or hasattr(request.user, 'dean_profile')):
            return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

        with transaction.atomic():
            if schedule_slot.stream_id:
                count = ScheduleSlot.objects.filter(stream_id=schedule_slot.stream_id).delete()[0]
                msg = _('Удален поток (%(count)s групп)') % {'count': count}
            else:
                schedule_slot.delete()
                msg = _('Занятие удалено')

        return JsonResponse({'success': True, 'message': msg})

    except Exception as e:
        return JsonResponse({'success': False, 'error': _('Ошибка: %(error)s') % {'error': str(e)}}, status=500)

@login_required
def schedule_view(request):
    user = request.user
    group = None
    active_semester = None
    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                active_semester = get_active_semester_for_group(group)
        except Student.DoesNotExist:
            pass

    if not active_semester:
        active_semester = Semester.objects.filter(is_active=True).first()

    if not active_semester:
        active_semester = Semester.objects.order_by('-start_date').first()
        if not active_semester:
             messages.warning(request, _('В системе не создано ни одного семестра.'))
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

        except Teacher.DoesNotExist:
            pass

    elif user.role == 'DEAN':
        group_id = request.GET.get('group')
        groups = Group.objects.all()

        if group_id:
            group = get_object_or_404(Group, id=group_id)
            active_semester = get_active_semester_for_group(group)
            if not active_semester:
                messages.warning(request, _('Нет активного семестра для %(course)s курса') % {'course': group.course})

    if group and active_semester:
        time_slots = get_time_slots_for_shift(active_semester.shift)
        days = [(0, _('ДУШАНБЕ')), (1, _('СЕШАНБЕ')), (2, _('ЧОРШАНБЕ')), (3, _('ПАНҶШАНБЕ')), (4, _('ҶУМЪА')), (5, _('ШАНБЕ'))]
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

        context = {
            'group': group,
            'groups': Group.objects.all() if user.role == 'DEAN' else groups if user.role == 'TEACHER' else None,
            'days': days,
            'time_slots': time_slots,
            'schedule_data': schedule_data,
            'active_semester': active_semester,
            'is_view_mode': True,
        }
        return render(request, 'schedule/schedule_view_unified.html', context)

    context = {
        'group': group,
        'groups': Group.objects.all() if user.role == 'DEAN' else None,
        'active_semester': active_semester,
    }
    return render(request, 'schedule/schedule_view_unified.html', context)

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

@user_passes_test(is_dean_or_admin)
def manage_subjects(request):
    subjects = Subject.objects.all().select_related('teacher__user')
    search = request.GET.get('search', '')
    if search:
        subjects = subjects.filter(Q(name__icontains=search) | Q(code__icontains=search))
    return render(request, 'schedule/manage_subjects.html', {'subjects': subjects, 'search': search})

@user_passes_test(is_dean_or_admin)
def add_subject(request):
    initial_data = {}
    dept_id = request.GET.get('department')

    target_department = None
    if dept_id:
        target_department = get_object_or_404(Department, id=dept_id)
        if request.user.role == 'DEAN':
            if target_department.faculty != request.user.dean_profile.faculty:
                messages.error(request, _("Нет доступа к этой кафедре"))
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

            messages.success(request, _('Предмет "%(subject_name)s" создан') % {'subject_name': subject.name})
            if dept_id:
                return redirect('accounts:manage_structure')
            return redirect('schedule:manage_subjects')
        else:
            print(_("Ошибки формы предмета:"), form.errors)
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

    return render(request, 'schedule/subject_form.html', {'form': form, 'title': _('Добавить предмет')})



@user_passes_test(is_dean_or_admin)
def edit_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, _('Предмет обновлен'))
            return redirect('schedule:manage_subjects')
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'schedule/subject_form.html', {'form': form, 'subject': subject, 'title': _('Редактировать предмет')})

@user_passes_test(is_dean_or_admin)
def delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    subject.delete()
    messages.success(request, _('Предмет удален'))
    return redirect('schedule:manage_subjects')

@user_passes_test(is_dean_or_admin)
def manage_semesters(request):
    semesters = Semester.objects.all().order_by('-academic_year', 'course')
    
    if request.user.role == 'DEAN':
        faculty = request.user.dean_profile.faculty
        semesters = semesters.filter(faculty=faculty)

    return render(request, 'schedule/manage_semesters.html', {
        'semesters': semesters
    })

@user_passes_test(is_dean_or_admin)
def add_semester(request):
    if request.method == 'POST':
        form = SemesterForm(request.POST, user=request.user)
        if form.is_valid():
            semester = form.save()
            messages.success(request, _('Семестр "%(semester_name)s" создан для факультета %(faculty_name)s') % {'semester_name': semester.name, 'faculty_name': semester.faculty.name})
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm(user=request.user)
    return render(request, 'schedule/semester_form.html', {'form': form, 'title': _('Добавить семестр')})

@user_passes_test(is_dean_or_admin)
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
            messages.success(request, _('Семестр обновлен'))
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm(instance=semester, user=request.user)
        
    return render(request, 'schedule/semester_form.html', {'form': form, 'semester': semester, 'title': _('Редактировать семестр')})

@user_passes_test(is_dean_or_admin)
def toggle_semester_active(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    with transaction.atomic():
        if not semester.is_active:
            Semester.objects.filter(
                course=semester.course, 
                is_active=True
            ).update(is_active=False)
            
            semester.is_active = True
            semester.save()
            messages.success(request, _('Семестр "%(semester_name)s" (%(course)s курс) теперь АКТИВЕН!') % {'semester_name': semester.name, 'course': semester.course})
        else:
            semester.is_active = False
            semester.save()
            messages.warning(request, _('Семестр "%(semester_name)s" деактивирован.') % {'semester_name': semester.name})

    return redirect('schedule:manage_semesters')

@login_required
def manage_classrooms(request):
    classrooms = Classroom.objects.select_related('building').all().order_by('building', 'floor', 'number')
    
    institutes = Institute.objects.all()
    selected_institute_id = request.GET.get('institute')
    
    if request.user.is_superuser or request.user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        if selected_institute_id:
            classrooms = classrooms.filter(building__institute_id=selected_institute_id)
    
    elif request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if faculty and faculty.institute:
            classrooms = classrooms.filter(building__institute=faculty.institute)
            institutes = [] 

    return render(request, 'schedule/manage_classrooms.html', {
        'classrooms': classrooms,
        'institutes': institutes,
        'selected_institute_id': int(selected_institute_id) if selected_institute_id else None,
        'is_admin': request.user.is_superuser or request.user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']
    })

@user_passes_test(is_dean_or_admin)
def add_classroom(request):
    if request.method == 'POST':
        form = ClassroomForm(request.POST, user=request.user)
        if form.is_valid():
            classroom = form.save()
            messages.success(request, _('Кабинет %(classroom_number)s добавлен') % {'classroom_number': classroom.number})
            return redirect('schedule:manage_classrooms')
    else:
        form = ClassroomForm(user=request.user)
    return render(request, 'schedule/classroom_form.html', {'form': form, 'title': _('Добавить кабинет')})

@user_passes_test(is_dean_or_admin)
def bulk_add_classrooms(request):
    if request.method == 'POST':
        form = BulkClassroomForm(request.POST, user=request.user)
        if form.is_valid():
            building = form.cleaned_data['building']
            floor = form.cleaned_data['floor']
            start = form.cleaned_data['start_number']
            end = form.cleaned_data['end_number']
            capacity = form.cleaned_data['capacity']

            created = 0
            for num in range(start, end + 1):
                number = f"{num}"
                if not Classroom.objects.filter(building=building, number=number).exists():
                    Classroom.objects.create(building=building, number=number, floor=floor, capacity=capacity)
                    created += 1

            messages.success(request, _('Создано %(created_count)s кабинетов в корпусе %(building)s') % {
                'created_count': created,
                'building': building.name
            })
            return redirect('schedule:manage_classrooms')
    else:
        form = BulkClassroomForm(user=request.user)
    return render(request, 'schedule/bulk_classroom_form.html', {'form': form})

@user_passes_test(is_dean_or_admin)
def delete_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)
    classroom.delete()
    messages.success(request, _('Кабинет %(classroom_number)s удален') % {'classroom_number': classroom.number})
    return redirect('schedule:manage_classrooms')

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
        messages.error(request, _('Доступ запрещен'))
        return redirect('core:dashboard')

    groups_with_students = []
    for group in groups:
        students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
        groups_with_students.append({'group': group, 'students': students})

    return render(request, 'schedule/group_list.html', {'groups_with_students': groups_with_students})

@login_required
def export_schedule(request):
    if not DOCX_AVAILABLE:
        return HttpResponse(_("Library python-docx not installed"), status=500)

    group_id = request.GET.get('group')
    group = get_object_or_404(Group, id=group_id)
    active_semester = get_active_semester_for_group(group)
    
    if not active_semester:
        return HttpResponse(_("Нет активного семестра"), status=400)

    try:
        if group.specialty:
            specialty_code = group.specialty.code
            specialty_name = group.specialty.name
            department = group.specialty.department
            faculty = department.faculty
            institute = faculty.institute
        else:
            specialty_code = "—"
            specialty_name = "Умумитаълимӣ (Общая)"
            faculty = active_semester.faculty
            institute = faculty.institute if faculty else Institute.objects.first()
    except AttributeError:
        return HttpResponse(_("Ошибка структуры: Невозможно определить институт."), status=400)

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

    director_name = director_user.get_full_name() if director_user else _("Мирзозода А. Н.") 
    vice_name = vice_user.get_full_name() if vice_user else _("Ҷовиди Ҷамшед") 
    
    head_edu_name = _("Ҷалилов Р.Р.")

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
    p1.add_run(_("Мувофиқа карда шуд:\n")).bold = True
    p1.add_run(_("Сардори раёсати таълим\n"))
    p1.add_run(_("________ дотсент %(head_edu_name)s\n") % {'head_edu_name': head_edu_name})
    p1.add_run(_("«___» _________ 2025с"))
    
    c2 = header_table.cell(0, 1)
    p2 = c2.paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p2.add_run(_("Тасдиқ мекунам:\n")).bold = True
    p2.add_run(_("Муовини директор\nоид ба корҳои таълимӣ\n")).bold = False
    p2.add_run(_("________ дотсент %(vice_name)s\n") % {'vice_name': vice_name})
    p2.add_run(_("«___»_________ 2025c"))

    doc.add_paragraph() 

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_p.add_run(_("ҶАДВАЛИ ДАРСӢ"))
    run.bold = True
    run.font.size = Pt(16)
    run.font.name = 'Times New Roman'

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sem_text = _("якуми") if active_semester.number == 1 else _("дуюми")
    year_text = active_semester.academic_year
    
    text = _("дар нимсолаи %(sem_text)s соли таҳсили %(year_text)s барои донишҷӯёни курси %(course)s-юми %(institute_name)s-и Донишгоҳи байналмилаии сайёҳӣ ва соҳибкории Тоҷикистон") % {
        'sem_text': sem_text,
        'year_text': year_text,
        'course': group.course,
        'institute_name': institute.name
    }
    
    run_sub = subtitle.add_run(text)
    run_sub.font.name = 'Times New Roman'
    run_sub.font.size = Pt(12)
    run_sub.bold = True
    
    shift_num = "1" if active_semester.shift == "MORNING" else "2"
    shift_p = doc.add_paragraph(_("(БАСТИ %(shift_num)s)") % {'shift_num': shift_num})
    shift_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    shift_p.runs[0].bold = True
    shift_p.runs[0].font.size = Pt(14)

    table = doc.add_table(rows=1, cols=4)
    table.style = 'Table Grid'
    
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = _("ҲАФТА")
    hdr_cells[1].text = _("СОАТ")
    
    hdr_cells[2].text = _("%(specialty_code)s – «%(specialty_name)s» (%(student_count)s нафар)") % {
        'specialty_code': specialty.code,
        'specialty_name': specialty.name,
        'student_count': group.students.count()
    }

    hdr_cells[3].text = _("АУД")
    
    for cell in hdr_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:val'), 'clear')
        shading_elm.set(qn('w:color'), 'auto')
        shading_elm.set(qn('w:fill'), 'D9D9D9')
        cell._tc.get_or_add_tcPr().append(shading_elm)
        
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(10)

    time_slots = get_time_slots_for_shift(active_semester.shift)
    days = [(0, _('ДУШАНБЕ')), (1, _('СЕШАНБЕ')), (2, _('ЧОРШАНБЕ')), (3, _('ПАНҶШАНБЕ')), (4, _('ҶУМЪА')), (5, _('ШАНБЕ'))]

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
                    p.add_run(_("%(subject_name)s (%(lesson_type)s)\n") % {
                        'subject_name': slot.subject.name,
                        'lesson_type': slot.get_lesson_type_display()
                    })
                    if slot.teacher:
                        p.add_run(_("%(teacher_name)s") % {'teacher_name': slot.teacher.user.get_full_name()})
                    
                    cell_aud = row.cells[3]
                    cell_aud.text = slot.room if slot.room else ""
                    cell_aud.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cell_aud.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        day_cell = table.rows[first_row_idx].cells[0]
        day_cell.text = day_name
        day_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        tcPr = day_cell._tc.get_or_add_tcPr()
        textDirection = OxmlElement('w:textDirection')
        textDirection.set(qn('w:val'), 'btLr')
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
            
            mil_cell.text = _("Кафедраи ҳарбӣ")
            
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
    fp1.add_run(_("Директор")).bold = True
    
    f_c2 = footer_table.cell(0, 1)
    fp2 = f_c2.paragraphs[0]
    fp2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fp2.add_run(_("%(director_name)s") % {'director_name': director_name}).bold = True

    f = BytesIO()
    doc.save(f)
    f.seek(0)
    
    filename = f"Jadval_{group.name}.docx"
    response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response



@user_passes_test(is_dean_or_admin)
def manage_plans(request):
    plans = AcademicPlan.objects.all().select_related('specialty', 'specialty__department__faculty')
    
    if request.user.role == 'DEAN':
        if hasattr(request.user, 'dean_profile'):
            faculty = request.user.dean_profile.faculty
            plans = plans.filter(specialty__department__faculty=faculty)
        
    return render(request, 'schedule/plans/manage_plans.html', {'plans': plans})


@user_passes_test(is_dean_or_admin)
def create_plan(request):
    initial_data = {}
    specialty_id = request.GET.get('specialty')
    if specialty_id:
        initial_data['specialty'] = specialty_id

    if request.method == 'POST':
        form = AcademicPlanForm(request.POST, user=request.user)
        if form.is_valid():
            plan = form.save()
            return redirect('schedule:plan_detail', plan_id=plan.id)
    else:
        form = AcademicPlanForm(user=request.user, initial=initial_data)
    
    all_groups = Group.objects.all()
    if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        all_groups = all_groups.filter(specialty__department__faculty=request.user.dean_profile.faculty)

    return render(request, 'schedule/plans/create_plan.html', {
        'form': form, 
        'all_groups': all_groups
    })


@user_passes_test(is_dean_or_admin)
def plan_detail(request, plan_id):
    plan = get_object_or_404(AcademicPlan, id=plan_id)
    if request.user.role == 'DEAN':
        user_faculty = request.user.dean_profile.faculty
        if plan.specialty.department.faculty != user_faculty:
            messages.error(request, _("Это план чужого факультета!"))
            return redirect('schedule:manage_plans')
    else:
        user_faculty = plan.specialty.department.faculty 

    try:
        current_sem_num = int(request.GET.get('semester', 1))
    except ValueError:
        current_sem_num = 1

    target_course = (current_sem_num + 1) // 2

    available_semesters = Semester.objects.filter(
        faculty=user_faculty,
        course=target_course
    ).order_by('-academic_year', 'number')

    active_semester = available_semesters.filter(is_active=True).first()

    if request.method == 'POST' and 'add_discipline' in request.POST:
        form = PlanDisciplineForm(request.POST)
        if form.is_valid():
            disc = form.save(commit=False)
            disc.plan = plan
            disc.semester_number = current_sem_num
            disc.save()
            messages.success(request, _("Дисциплина добавлена"))
            return redirect(f"{request.path}?semester={current_sem_num}")
    else:
        form = PlanDisciplineForm(initial={'semester_number': current_sem_num})

    disciplines = PlanDiscipline.objects.filter(plan=plan, semester_number=current_sem_num)
    
    return render(request, 'schedule/plans/plan_detail.html', {
        'plan': plan,
        'disciplines': disciplines,
        'form': form,
        'current_sem_num': current_sem_num,
        'semesters_range': range(1, 9),
        'target_course': target_course,
        'available_semesters': available_semesters, 
        'active_semester': active_semester          
    })


@user_passes_test(is_dean_or_admin)
def generate_subjects_from_rup(request):
    active_semester = Semester.objects.filter(is_active=True).first()
    if not active_semester:
        messages.error(request, _("Нет активного семестра! Сначала активируйте семестр."))
        return redirect('schedule:manage_semesters')

    groups = Group.objects.all()
    
    if request.user.role == 'DEAN':
        if hasattr(request.user, 'dean_profile'):
            groups = groups.filter(specialty__department__faculty=request.user.dean_profile.faculty)

    suggestions = {}

    for group in groups:
        current_semester_num = (group.course - 1) * 2 + active_semester.number

        plan = AcademicPlan.objects.filter(group=group, is_active=True).order_by('-admission_year').first()
        
        if not plan and group.specialty:
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
                            department=group_list[0].specialty.department if group_list[0].specialty else Department.objects.first(),                            type='LECTURE',
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
                                department=grp.specialty.department if grp.specialty else Department.objects.first(),
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

        messages.success(request, _("Создано предметов: %(created_count)s") % {'created_count': created_count})
        return redirect('schedule:manage_subjects')

    return render(request, 'schedule/plans/generate_preview.html', {
        'suggestions': suggestions.values(),
        'semester': active_semester
    })



@user_passes_test(is_dean_or_admin)
def edit_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)
    if request.method == 'POST':
        form = ClassroomForm(request.POST, instance=classroom)
        if form.is_valid():
            form.save()
            messages.success(request, _('Кабинет %(classroom_number)s обновлен') % {'classroom_number': classroom.number})
            return redirect('schedule:manage_classrooms')
    else:
        form = ClassroomForm(instance=classroom)
    return render(request, 'schedule/classroom_form.html', {
        'form': form, 
        'title': _('Редактировать кабинет %(classroom_number)s') % {'classroom_number': classroom.number}
    })

@login_required
def classroom_occupancy(request):
    day = int(request.GET.get('day', 0)) 
    
    active_semester = Semester.objects.filter(is_active=True).first()
    if not active_semester:
        active_semester = Semester.objects.order_by('-start_date').first()
        if not active_semester:
            messages.error(request, _("Нет активного семестра"))
            return redirect('schedule:manage_classrooms')

    classrooms = Classroom.objects.filter(is_active=True).select_related('building')
    
    institutes = []
    selected_institute_id = request.GET.get('institute')
    
    if request.user.is_superuser or request.user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        institutes = Institute.objects.all() 
        if selected_institute_id:
            classrooms = classrooms.filter(building__institute_id=selected_institute_id)
            
    elif request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if faculty and faculty.institute:
            classrooms = classrooms.filter(building__institute=faculty.institute)

    classrooms = classrooms.order_by('building', 'floor', 'number')
    
    time_slots = get_time_slots_for_shift(active_semester.shift)
    
    days = [
        (0, _('Понедельник')), (1, _('Вторник')), (2, _('Среда')),
        (3, _('Четверг')), (4, _('Пятница')), (5, _('Суббота'))
    ]

    slots = ScheduleSlot.objects.filter(
        semester=active_semester,
        day_of_week=day,
        is_active=True,
        classroom__in=classrooms
    ).select_related('classroom', 'group', 'subject', 'time_slot', 'teacher__user')

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
        'days': days,
        'institutes': institutes, 
        'selected_institute_id': int(selected_institute_id) if selected_institute_id else None
    })


@login_required
def import_schedule_view(request):
    if not (request.user.role in ['DEAN', 'VICE_DEAN'] or request.user.is_superuser):
        messages.error(request, _("Доступ запрещен"))
        return redirect('schedule:view')

    if request.method == 'POST' and 'confirm_import' in request.POST:
        semester_id = request.POST.get('semester_id')
        semester = Semester.objects.get(id=semester_id)

        all_keys = [k for k in request.POST.keys() if k.startswith('item_') and k.endswith('_group_id')]
        if not all_keys:
            messages.error(request, _("Нет данных для сохранения"))
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
        messages.success(request, _("✅ Импорт завершен! Слотов: %(slots)s, Новых предметов: %(subjects)s, Новых учителей: %(teachers)s") % {
            'slots': stats['slots'],
            'subjects': stats['subjects'],
            'teachers': stats['teachers']
        })
        return redirect('schedule:view')

    elif request.method == 'POST':
        form = ScheduleImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                importer = ScheduleImporter(file=request.FILES['file'])
                preview_data = importer.parse_for_preview(default_group=form.cleaned_data['default_group'])

                if not preview_data:
                    messages.warning(request, _("Данные не найдены в файле или формат некорректен."))
                    return redirect('schedule:import_schedule')

                context = {
                    'preview_data': preview_data,
                    'semester': form.cleaned_data['semester'],
                    'days_map_rev': {0: _('Понедельник'), 1: _('Вторник'), 2: _('Среда'), 3: _('Четверг'), 4: _('Пятница'), 5: _('Суббота')}
                }
                return render(request, 'schedule/import_preview_edit.html', context)

            except Exception as e:
                messages.error(request, _("Ошибка обработки файла: %(error)s") % {'error': str(e)})

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
            return JsonResponse({'success': False, 'error': _('Название не может быть пустым')})
            
        if SubjectTemplate.objects.filter(name__iexact=name).exists():
            return JsonResponse({'success': False, 'error': _('Такая дисциплина уже существует')})
            
        template = SubjectTemplate.objects.create(name=name)
        
        return JsonResponse({
            'success': True,
            'id': template.id,
            'name': template.name
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(is_dean_or_admin)
def copy_plan(request, plan_id):
    original_plan = get_object_or_404(AcademicPlan, id=plan_id)
    
    if request.method == 'POST':
        new_year = request.POST.get('new_year')
        if not new_year:
            messages.error(request, _("Укажите новый год"))
            return redirect('schedule:manage_plans')
            
        if AcademicPlan.objects.filter(specialty=original_plan.specialty, admission_year=new_year).exists():
            messages.error(request, _("План для %(specialty_code)s на %(new_year)s год уже существует!") % {
                'specialty_code': original_plan.specialty.code,
                'new_year': new_year
            })
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
            
        messages.success(request, _("План успешно скопирован на %(new_year)s год!") % {'new_year': new_year})
        return redirect('schedule:plan_detail', plan_id=new_plan.id)
        
    return redirect('schedule:manage_plans')



@user_passes_test(is_dean)
def delete_plan_discipline(request, discipline_id):
    discipline = get_object_or_404(PlanDiscipline, id=discipline_id)
    plan_id = discipline.plan.id
    
    if request.user.role == 'DEAN':
        if discipline.plan.specialty.department.faculty != request.user.dean_profile.faculty:
            messages.error(request, _("Нет прав на удаление"))
            return redirect('schedule:plan_detail', plan_id=plan_id)

    discipline.delete()
    messages.success(request, _("Дисциплина удалена из плана"))
    return redirect('schedule:plan_detail', plan_id=plan_id)

@user_passes_test(is_dean_or_admin)
def teacher_load_report(request):
    teachers = Teacher.objects.select_related('user', 'department', 'department__faculty').all()
    
    if request.user.role == 'DEAN':
        if hasattr(request.user, 'dean_profile'):
            faculty = request.user.dean_profile.faculty
            teachers = teachers.filter(department__faculty=faculty)
    
    report_data = []
    
    for teacher in teachers:
        subjects = Subject.objects.filter(teacher=teacher)
        
        total_hours = 0
        total_credits = 0
        subjects_list = []
        
        for subj in subjects:
            hours = subj.total_auditory_hours
            total_hours += hours
            total_credits += subj.credits
            subjects_list.append(f"{subj.name} ({hours}ч)")
            
        report_data.append({
            'teacher': teacher,
            'total_hours': total_hours,
            'total_credits': total_credits,
            'subjects_count': subjects.count(),
            'subjects_names': ", ".join(subjects_list[:3]) + ("..." if len(subjects_list) > 3 else "")
        })
    
    report_data.sort(key=lambda x: x['total_hours'], reverse=True)
    
    return render(request, 'schedule/teacher_load_report.html', {
        'report_data': report_data
    })

@login_required
def subject_materials(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    materials = subject.materials.order_by('-uploaded_at')
    
    can_upload = False
    if request.user.is_superuser or request.user.role in ['DEAN', 'VICE_DEAN']:
        can_upload = True
    elif request.user.role == 'TEACHER' and subject.teacher and subject.teacher.user == request.user:
        can_upload = True

    if request.method == 'POST' and can_upload:
        form = MaterialUploadForm(request.POST, request.FILES)
        if form.is_valid():
            mat = form.save(commit=False)
            mat.subject = subject
            mat.save()
            messages.success(request, _('Материал добавлен'))
            return redirect('schedule:subject_materials', subject_id=subject.id)
    else:
        form = MaterialUploadForm()

    return render(request, 'schedule/subject_materials.html', {
        'subject': subject,
        'materials': materials,
        'form': form,
        'can_upload': can_upload
    })

@login_required
def delete_material(request, material_id):
    material = get_object_or_404(SubjectMaterial, id=material_id)
    if request.user.is_superuser or (request.user.role == 'TEACHER' and material.subject.teacher.user == request.user):
        material.delete()
        messages.success(request, _('Материал удален'))
    return redirect('schedule:subject_materials', subject_id=material.subject.id)



@user_passes_test(is_dean_or_admin)
def activate_plan(request, plan_id):
    plan = get_object_or_404(AcademicPlan, id=plan_id)
    
    with transaction.atomic():
        AcademicPlan.objects.filter(specialty=plan.specialty).update(is_active=False)
        
        plan.is_active = True
        plan.save()
        
    messages.success(request, _("Учебный план для %(specialty_code)s (%(admission_year)s) теперь АКТИВЕН!") % {
        'specialty_code': plan.specialty.code,
        'admission_year': plan.admission_year
    })
    return redirect('schedule:plan_detail', plan_id=plan.id)

@user_passes_test(is_dean_or_admin)
def delete_plan(request, plan_id):
    plan = get_object_or_404(AcademicPlan, id=plan_id)
    if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        if plan.specialty.department.faculty != request.user.dean_profile.faculty:
            messages.error(request, _("Нет прав на удаление этого плана"))
            return redirect('schedule:manage_plans')
            
    plan.delete()
    messages.success(request, _("Учебный план для %(specialty_code)s удален") % {'specialty_code': plan.specialty.code})
    return redirect('schedule:manage_plans')

@user_passes_test(is_dean_or_admin)
def activate_semester_from_plan(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    with transaction.atomic():
        Semester.objects.filter(course=semester.course, is_active=True).update(is_active=False)
        
        semester.is_active = True
        semester.save()
        
    messages.success(request, _("Семестр '%(semester_name)s' (%(course)s курс) успешно активирован!") % {
        'semester_name': semester.name,
        'course': semester.course
    })
    return redirect(request.META.get('HTTP_REFERER', 'schedule:manage_plans'))

@user_passes_test(is_dean_or_admin)
@require_POST
def set_active_semester_manual(request):
    semester_id = request.POST.get('semester_id')
    
    if not semester_id:
        messages.error(request, _("Выберите семестр из списка"))
        return redirect(request.META.get('HTTP_REFERER'))

    semester = get_object_or_404(Semester, id=semester_id)
    
    if request.user.role == 'DEAN' and semester.faculty != request.user.dean_profile.faculty:
        messages.error(request, _("Ошибка доступа"))
        return redirect(request.META.get('HTTP_REFERER'))

    with transaction.atomic():
        Semester.objects.filter(
            faculty=semester.faculty, 
            course=semester.course, 
            is_active=True
        ).update(is_active=False)
        
        semester.is_active = True
        semester.save()

    messages.success(request, _("Семестр %(semester)s теперь АКТИВЕН для %(course)s курса!") % {
        'semester': semester,
        'course': semester.course
    })
    return redirect(request.META.get('HTTP_REFERER'))


@user_passes_test(lambda u: u.is_superuser or u.role in ['RECTOR', 'PRO_RECTOR'])
def manage_time_slots(request):
    if request.method == 'POST':
        form = TimeSlotGeneratorForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            inst = data['institute'] 
            shift = data['shift']
            
            if data['delete_existing']:
                TimeSlot.objects.filter(institute=inst, shift=shift).delete()
            
            current_time = datetime.combine(date.today(), data['start_time'])
            created_count = 0
            
            big_break_after = data.get('big_break_after') or 0
            big_break_dur = data.get('big_break_duration') or data['break_duration']
            
            for i in range(1, data['pairs_count'] + 1):
                start = current_time.time()
                end_dt = current_time + timedelta(minutes=data['lesson_duration'])
                end = end_dt.time()
                
                TimeSlot.objects.create(
                    institute=inst,
                    number=i,
                    start_time=start,
                    end_time=end,
                    shift=shift,
                    duration=data['lesson_duration']
                )
                created_count += 1
                
                is_big_break = (i == big_break_after)
                break_min = big_break_dur if is_big_break else data['break_duration']
                
                current_time = end_dt + timedelta(minutes=break_min)
            
            target = inst.name if inst else "Всего Университета (Глобально)"
            messages.success(request, _(f"Сетка звонков создана для: {target}. Сгенерировано {created_count} пар."))
            return redirect('schedule:manage_time_slots')
    else:
        form = TimeSlotGeneratorForm()

    global_slots = TimeSlot.objects.filter(institute__isnull=True).order_by('shift', 'start_time')
    institute_slots = TimeSlot.objects.filter(institute__isnull=False).select_related('institute').order_by('institute', 'shift', 'start_time')
    
    return render(request, 'schedule/manage_time_slots.html', {
        'form': form,
        'global_slots': global_slots,
        'institute_slots': institute_slots
    })




@user_passes_test(is_dean_or_admin)
def manage_buildings(request):
    buildings = Building.objects.select_related('institute').all()
    
    if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if faculty and faculty.institute:
            buildings = buildings.filter(institute=faculty.institute)

    return render(request, 'schedule/manage_buildings.html', {'buildings': buildings})

@user_passes_test(is_dean_or_admin)
def add_building(request):
    if request.method == 'POST':
        form = BuildingForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Учебный корпус добавлен"))
            return redirect('schedule:manage_buildings')
    else:
        form = BuildingForm(user=request.user)
    
    return render(request, 'schedule/building_form.html', {
        'form': form, 
        'title': _('Добавить учебный корпус')
    })

@user_passes_test(is_dean_or_admin)
def edit_building(request, building_id):
    building = get_object_or_404(Building, id=building_id)
    
    if request.user.role == 'DEAN':
        faculty = request.user.dean_profile.faculty
        if building.institute != faculty.institute:
            messages.error(request, _("Вы не можете редактировать корпуса чужого института"))
            return redirect('schedule:manage_buildings')

    if request.method == 'POST':
        form = BuildingForm(request.POST, instance=building, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Корпус обновлен"))
            return redirect('schedule:manage_buildings')
    else:
        form = BuildingForm(instance=building, user=request.user)
    
    return render(request, 'schedule/building_form.html', {
        'form': form, 
        'title': _('Редактировать корпус')
    })

@user_passes_test(is_dean_or_admin)
def delete_building(request, building_id):
    building = get_object_or_404(Building, id=building_id)
    
    if request.user.role == 'DEAN':
        faculty = request.user.dean_profile.faculty
        if building.institute != faculty.institute:
            messages.error(request, _("Нет доступа"))
            return redirect('schedule:manage_buildings')
            
    if building.classrooms.exists():
        messages.error(request, _("Нельзя удалить корпус, в котором есть кабинеты. Сначала удалите кабинеты."))
    else:
        building.delete()
        messages.success(request, _("Корпус удален"))
        
    return redirect('schedule:manage_buildings')



@login_required
@require_POST
def check_schedule_conflicts(request):
    import json
    data = json.loads(request.body)
    
    semester_id = data.get('semester_id')
    day = data.get('day')
    time_slot_id = data.get('time_slot_id')
    group_id = data.get('group_id')
    teacher_id = data.get('teacher_id') 
    room_number = data.get('room') 
    subject_id = data.get('subject_id')
    
    conflicts = []
    
    base_qs = ScheduleSlot.objects.filter(
        semester_id=semester_id,
        day_of_week=day,
        time_slot_id=time_slot_id,
        is_active=True
    )

    if group_id:
        group_conflict = base_qs.filter(group_id=group_id).first()
        if group_conflict:
            conflicts.append({
                'type': 'group',
                'message': _(f"Группа {group_conflict.group.name} уже занята: {group_conflict.subject.name}")
            })

    if teacher_id:
        teacher_conflict = base_qs.filter(teacher_id=teacher_id).first()
        if teacher_conflict:
            conflicts.append({
                'type': 'teacher',
                'message': _(f"Преподаватель {teacher_conflict.teacher.user.get_full_name()} уже ведет пару в группе {teacher_conflict.group.name}")
            })

    if room_number:
        
        classroom_qs = Classroom.objects.filter(number=room_number, is_active=True)
        
        if group_id:
            try:
                grp = Group.objects.get(id=group_id)
                inst = grp.specialty.department.faculty.institute
                classroom_qs = classroom_qs.filter(building__institute=inst)
            except:
                pass
        
        target_classroom = classroom_qs.first()
        
        if target_classroom:
            room_conflict = base_qs.filter(classroom=target_classroom).first()
            if room_conflict:
                conflicts.append({
                    'type': 'room',
                    'message': _(f"Кабинет {room_number} ({target_classroom.building.name}) занят: {room_conflict.group.name}, {room_conflict.teacher.user.get_last_name() if room_conflict.teacher else ''}")
                })
        else:
            text_conflict = base_qs.filter(room=room_number).first()
            if text_conflict:
                 conflicts.append({
                    'type': 'room',
                    'message': _(f"Кабинет {room_number} (текст) занят: {text_conflict.group.name}")
                })

    if conflicts:
        return JsonResponse({'success': False, 'conflicts': conflicts})
    
    return JsonResponse({'success': True})

@user_passes_test(is_dean_or_admin)
def import_rup_excel(request, plan_id, semester_num):
    plan = get_object_or_404(AcademicPlan, id=plan_id)
    
    if request.method == 'POST':
        form = RupImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                stats = RupImporter.import_from_excel(
                    file=request.FILES['file'], 
                    plan_id=plan.id, 
                    semester_number=semester_num
                )
                messages.success(request, f"Успешно! Добавлено: {stats['created']}, Обновлено: {stats['updated']}")
                if stats['errors']:
                    messages.warning(request, f"Ошибки ({len(stats['errors'])}): {'; '.join(stats['errors'][:3])}...")
            except Exception as e:
                messages.error(request, f"Ошибка обработки файла: {str(e)}")
                
            return redirect(f"/schedule/plans/{plan.id}/?semester={semester_num}")
    
    messages.error(request, "Неверный запрос")
    return redirect(f"/schedule/plans/{plan.id}/?semester={semester_num}")



