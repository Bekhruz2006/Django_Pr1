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

try:
    from docx import Document
    from docx.shared import Inches, Pt
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from .models import Subject, ScheduleSlot, Semester, Classroom, AcademicWeek, TimeSlot
from .forms import SubjectForm, SemesterForm, ClassroomForm, BulkClassroomForm, AcademicWeekForm
from accounts.models import Group, Student, Teacher

def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'

def is_teacher(user):
    return user.is_authenticated and user.role == 'TEACHER'

def is_student(user):
    return user.is_authenticated and user.role == 'STUDENT'

def get_time_slots_for_shift(shift):
    if shift == 'MORNING':
        return TimeSlot.objects.filter(
            start_time__gte='08:00:00',
            start_time__lt='14:00:00'
        ).order_by('start_time')
    else:
        return TimeSlot.objects.filter(
            start_time__gte='13:00:00',
            start_time__lt='19:00:00'
        ).order_by('start_time')

def get_active_semester_for_group(group):
    semester = Semester.objects.filter(groups=group, is_active=True).first()
    if not semester:
        semester = Semester.objects.filter(course=group.course, is_active=True).first()
    return semester

@login_required
def schedule_constructor(request):
    # ПРОВЕРКА ПРАВ: Декан меняет только свои группы
    group_id = request.GET.get('group')

    if group_id and request.user.role in ['DEAN', 'VICE_DEAN']:
        group = get_object_or_404(Group, id=group_id)

        # Получаем факультет пользователя
        user_faculty = None
        if hasattr(request.user, 'dean_profile') and request.user.dean_profile.faculty:
            user_faculty = request.user.dean_profile.faculty
        elif hasattr(request.user, 'vicedean_profile') and request.user.vicedean_profile.faculty:
            user_faculty = request.user.vicedean_profile.faculty

        # Проверяем, принадлежит ли группа факультету
        # Group -> Specialty -> Department -> Faculty
        group_faculty = group.specialty.department.faculty

        if user_faculty != group_faculty:
            messages.error(request, "Вы не можете редактировать расписание другого факультета!")
            return redirect('schedule:constructor')

    selected_group_id = request.GET.get('group')
    selected_semester_id = request.GET.get('semester')

    groups = Group.objects.all().order_by('name')
    if selected_group_id:
        try:
            group = Group.objects.get(id=selected_group_id)
            semesters = Semester.objects.filter(course=group.course).order_by('-start_date')
        except Group.DoesNotExist:
            semesters = Semester.objects.all().order_by('-start_date')
    else:
        semesters = Semester.objects.all().order_by('-start_date')

    schedule_data = {}
    selected_group = None
    selected_semester = None
    time_slots = []
    days = []

    lecture_subjects = []
    practice_subjects = []
    control_subjects = []

    if not selected_semester_id:
        if selected_group_id:
            group = Group.objects.get(id=selected_group_id)
            selected_semester = get_active_semester_for_group(group)
        else:
            selected_semester = Semester.objects.filter(is_active=True).first()
    else:
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            if selected_group_id:
                group = Group.objects.get(id=selected_group_id)
                if selected_semester.course != group.course:
                    messages.error(request, f'Семестр для {selected_semester.course} курса, а группа {group.name} на {group.course} курсе!')
                    selected_semester = get_active_semester_for_group(group)
        except Semester.DoesNotExist:
            selected_semester = Semester.objects.filter(is_active=True).first()

    if not selected_semester:
        messages.error(request, 'Сначала создайте и активируйте семестр для этого курса')
        return redirect('schedule:manage_semesters')

    if selected_group_id:
        try:
            selected_group = Group.objects.get(id=selected_group_id)
            time_slots = get_time_slots_for_shift(selected_semester.shift)

            days = [
                (0, 'ДУШАНБЕ'), (1, 'СЕШАНБЕ'), (2, 'ЧОРШАНБЕ'),
                (3, 'ПАНҶШАНБЕ'), (4, 'ҶУМЪА'), (5, 'ШАНБЕ'),
            ]

            assigned_subjects = Subject.objects.filter(
                groups=selected_group
            ).select_related('teacher__user')

            for subject in assigned_subjects:
                slots_needed = subject.get_weekly_slots_needed()

                is_stream = subject.groups.count() > 1
                stream_groups_count = subject.groups.count()

                if slots_needed['LECTURE'] > 0:
                    existing_lectures = ScheduleSlot.objects.filter(
                        subject=subject,
                        group=selected_group,
                        semester=selected_semester,
                        lesson_type='LECTURE',
                        is_active=True
                    ).count()

                    remaining = max(0, slots_needed['LECTURE'] - existing_lectures)

                    if remaining > 0:
                        lecture_subjects.append({
                            'subject': subject,
                            'remaining': remaining,
                            'needed': slots_needed['LECTURE'],
                            'hours_per_week': subject.lecture_hours_per_week,
                            'is_stream': is_stream,
                            'stream_count': stream_groups_count if is_stream else 1
                        })

                if slots_needed['PRACTICE'] > 0:
                    existing_practices = ScheduleSlot.objects.filter(
                        subject=subject,
                        group=selected_group,
                        semester=selected_semester,
                        lesson_type='PRACTICE',
                        is_active=True
                    ).count()

                    remaining = max(0, slots_needed['PRACTICE'] - existing_practices)

                    if remaining > 0:
                        practice_subjects.append({
                            'subject': subject,
                            'remaining': remaining,
                            'needed': slots_needed['PRACTICE'],
                            'hours_per_week': subject.practice_hours_per_week,
                            'is_stream': False
                        })

                if slots_needed['SRSP'] > 0:
                    existing_control = ScheduleSlot.objects.filter(
                        subject=subject,
                        group=selected_group,
                        semester=selected_semester,
                        lesson_type='SRSP',
                        is_active=True
                    ).count()

                    remaining = max(0, slots_needed['SRSP'] - existing_control)

                    if remaining > 0:
                        control_subjects.append({
                            'subject': subject,
                            'remaining': remaining,
                            'needed': slots_needed['SRSP'],
                            'hours_per_week': subject.control_hours_per_week,
                            'is_stream': False
                        })

            valid_slot_ids = list(time_slots.values_list('id', flat=True))

            schedule_slots = ScheduleSlot.objects.filter(
                group=selected_group,
                semester=selected_semester,
                time_slot_id__in=valid_slot_ids,
                is_active=True
            ).select_related('subject', 'teacher__user', 'time_slot')

            schedule_data[selected_group.id] = {}
            for slot in schedule_slots:
                if slot.day_of_week not in schedule_data[selected_group.id]:
                    schedule_data[selected_group.id][slot.day_of_week] = {}
                schedule_data[selected_group.id][slot.day_of_week][slot.time_slot.id] = slot

        except Group.DoesNotExist:
            pass

    context = {
        'groups': groups,
        'semesters': semesters,
        'group': selected_group,
        'semester': selected_semester,
        'time_slots': time_slots,
        'lecture_subjects': lecture_subjects,
        'practice_subjects': practice_subjects,
        'control_subjects': control_subjects,
        'days': days,
        'schedule_data': schedule_data,
    }
    return render(request, 'schedule/constructor_with_limits.html', context)


@login_required
@user_passes_test(is_dean)
@require_POST
def create_schedule_slot(request):
    try:
        data = json.loads(request.body)
        force = data.get('force', False)

        # --- НОВАЯ ЛОГИКА: ВОЕННАЯ КАФЕДРА ---
        if data.get('is_military_day'):
            group_id = data.get('group')
            day_of_week = data.get('day_of_week')
            semester_id = data.get('semester_id')

            group = get_object_or_404(Group, id=group_id)
            if not group.has_military_training:
                return JsonResponse({'success': False, 'error': 'У этой группы нет военной кафедры!'}, status=400)

            semester = get_object_or_404(Semester, id=semester_id)

            # Удаляем старые слоты в этот день
            ScheduleSlot.objects.filter(
                group=group,
                semester=semester,
                day_of_week=day_of_week
            ).delete()

            # Создаем слоты военной кафедры для всех пар смены
            time_slots = get_time_slots_for_shift(semester.shift)

            # Создаем фиктивный предмет "Военная кафедра" для связности
            military_subject, _ = Subject.objects.get_or_create(
                name="Кафедраи ҳарбӣ",
                code="MILITARY",
                defaults={'department_id': 1}  # ID дефолтной кафедры
            )

            created_count = 0
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
                    lesson_type='PRACTICE'
                )
                created_count += 1

            return JsonResponse({'success': True, 'message': f'Военная кафедра установлена на весь день ({created_count} пар)'})

        # --- СТАРАЯ ЛОГИКА: ОБЫЧНЫЙ СЛОТ ---
        group_id = data.get('group')
        subject_id = data.get('subject')
        day_of_week = data.get('day_of_week')
        time_slot_id = data.get('time_slot')
        lesson_type = data.get('lesson_type', 'LECTURE')
        semester_id = data.get('semester_id')

        main_group = get_object_or_404(Group, id=group_id)
        subject = get_object_or_404(Subject, id=subject_id)
        time_slot = get_object_or_404(TimeSlot, id=time_slot_id)

        # 1. Валидация семестра
        if semester_id:
            active_semester = get_object_or_404(Semester, id=semester_id)
        else:
            active_semester = get_active_semester_for_group(main_group)

        if not active_semester:
            return JsonResponse({'success': False, 'error': 'Нет активного семестра'}, status=400)

        # 2. Валидация смены
        start_h = time_slot.start_time.hour
        if active_semester.shift == 'MORNING' and start_h >= 13:
            return JsonResponse({'success': False, 'error': 'Ошибка смены: Слот ДНЕВНОЙ, а семестр УТРЕННИЙ.'}, status=400)
        if active_semester.shift == 'DAY' and start_h < 13:
            return JsonResponse({'success': False, 'error': 'Ошибка смены: Слот УТРЕННИЙ, а семестр ДНЕВНОЙ.'}, status=400)

        groups_to_schedule = [main_group]
        is_stream = False
        stream_id = None

        # Логика потоков (Stream Logic)
        if lesson_type == 'LECTURE' and subject.groups.count() > 1:
            all_subject_groups = list(subject.groups.all())

            if len(all_subject_groups) > 3:
                return JsonResponse({
                    'success': False,
                    'error': f'Слишком большой поток! Предмет привязан к {len(all_subject_groups)} группам. Максимум разрешено 3.'
                }, status=400)

            groups_to_schedule = all_subject_groups
            is_stream = True
            stream_id = uuid.uuid4()

        conflicts = []

        if not force:
            # Проверка занятости групп
            for target_group in groups_to_schedule:
                busy_slot = ScheduleSlot.objects.filter(
                    group=target_group,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    semester=active_semester,
                    is_active=True
                ).first()

                if busy_slot:
                    conflicts.append(f"Группа {target_group.name} уже занята: {busy_slot.subject.name}")

            # Проверка преподавателя
            if subject.teacher:
                teacher_slots = ScheduleSlot.objects.filter(
                    teacher=subject.teacher,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    semester=active_semester,
                    is_active=True
                )
                if teacher_slots.exists():
                    conflicts.append(f"Преподаватель {subject.teacher.user.get_full_name()} уже занят в это время.")

        if conflicts:
            return JsonResponse({
                'success': False,
                'is_conflict': True,
                'error': "<br>".join(conflicts)
            }, status=400)

        # Создание записей
        with transaction.atomic():
            created_slots = []
            for target_group in groups_to_schedule:
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

        return JsonResponse({
            'success': True,
            'count': len(created_slots),
            'is_stream': is_stream
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': f"Ошибка сервера: {str(e)}"}, status=500)



@login_required
@require_POST
def update_schedule_room(request, slot_id):
    try:
        data = json.loads(request.body)
        room_number = data.get('room', '').strip()
        
        slot = get_object_or_404(ScheduleSlot, id=slot_id)

        classroom = None
        if room_number:
            classroom = Classroom.objects.filter(number=room_number, is_active=True).first()
            if not classroom:
                return JsonResponse({'success': False, 'error': f'Кабинет {room_number} не найден в базе'}, status=400)
            
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

            if occupants.exists():
                other = occupants.first()
                return JsonResponse({
                    'success': False,
                    'error': f'Кабинет занят: Группа {other.group.name}, {other.subject.name}'
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
                # Delete entire stream
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
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f'Предмет "{subject.name}" создан')
            return redirect('schedule:manage_subjects')
    else:
        form = SubjectForm()
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
        form = SemesterForm(request.POST)
        if form.is_valid():
            semester = form.save()
            messages.success(request, f'Семестр "{semester.name}" создан')
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm()
    return render(request, 'schedule/semester_form.html', {'form': form, 'title': 'Добавить семестр'})

@user_passes_test(is_dean)
def edit_semester(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if request.method == 'POST':
        form = SemesterForm(request.POST, instance=semester)
        if form.is_valid():
            form.save()
            messages.success(request, 'Семестр обновлен')
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm(instance=semester)
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
        messages.error(request, 'Библиотека python-docx не установлена.')
        return redirect('schedule:view')

    group_id = request.GET.get('group')
    group = get_object_or_404(Group, id=group_id)
    active_semester = get_active_semester_for_group(group)
    
    if not active_semester:
        return HttpResponse("Нет активного семестра", status=400)

    specialty = group.specialty
    department = specialty.department
    faculty = department.faculty
    institute = faculty.institute

    director = Director.objects.filter(institute=institute).first()
    director_name = director.user.get_full_name() if director else "________________"
    
    vice = ProRector.objects.filter(institute=institute).first()
    vice_name = vice.user.get_full_name() if vice else "________________"
    
    head_edu_name = "Ҷалилов Р.Р." 

    doc = Document()
    
    section = doc.sections[0]
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.0)
    section.bottom_margin = Cm(1.0)

    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = True
    header_table.width = section.page_width - section.left_margin - section.right_margin
    
    c1 = header_table.cell(0, 0)
    p1 = c1.paragraphs[0]
    p1.add_run("Мувофиқа карда шуд:\n").bold = True
    p1.add_run("сардори раёсати таълим\n")
    p1.add_run(f"________ дотсент {head_edu_name}\n")
    p1.add_run("«___» _________ 2025с")
    
    c2 = header_table.cell(0, 1)
    p2 = c2.paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p2.add_run("Тасдиқ мекунам:\n").bold = True
    p2.add_run("муовини ректор оид ба корҳои таълимӣ\n") 
    p2.add_run(f"________ дотсент {vice_name}\n")
    p2.add_run("«___»_________ 2025c")

    doc.add_paragraph() # Spacer

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_p.add_run("ҶАДВАЛИ ДАРСӢ")
    run.bold = True
    run.font.size = Pt(14)
    run.font.name = 'Times New Roman'

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sem_text = "якуми" if active_semester.number == 1 else "дуюми"
    year_text = active_semester.academic_year
    shift_text = "1" if active_semester.shift == "MORNING" else "2"
    
    text = f"дар нимсолаи {sem_text} соли таҳсили {year_text} барои донишҷӯёни курси {group.course}-юми " \
           f"{institute.name}-и Донишгоҳи байналмилаии сайёҳӣ ва соҳибкории Тоҷикистон"
    
    run_sub = subtitle.add_run(text)
    run_sub.font.name = 'Times New Roman'
    run_sub.font.size = Pt(12)
    
    shift_p = doc.add_paragraph(f"(БАСТИ {shift_text})")
    shift_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    shift_p.runs[0].bold = True

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
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(10)

    time_slots = get_time_slots_for_shift(active_semester.shift)
    days = [(0, 'ДУШАНБЕ'), (1, 'СЕШАНБЕ'), (2, 'ЧОРШАНБЕ'), (3, 'ПАНҶШАНБЕ'), (4, 'ҶУМЪА'), (5, 'ШАНБЕ')]

    for day_num, day_name in days:
        is_military_day = ScheduleSlot.objects.filter(
            group=group, semester=active_semester, day_of_week=day_num, is_military=True
        ).exists()

        if is_military_day:
            first_row_idx = len(table.rows)
            for i, ts in enumerate(time_slots):
                row = table.add_row()
                row.cells[1].text = f'{ts.start_time.strftime("%H:%M")}-{ts.end_time.strftime("%H:%M")}'
                
                if i == 0:
                    row.cells[0].text = day_name
                    pass 
            
            day_cell = table.rows[first_row_idx].cells[0]
            day_cell.merge(table.rows[len(table.rows)-1].cells[0])
            
            mil_cell_top = table.rows[first_row_idx].cells[2]
            mil_cell_top.merge(table.rows[first_row_idx].cells[3])
            mil_cell_top.text = "Кафедраи ҳарбӣ"
            mil_cell_top.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            mil_cell_top.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            
            run = mil_cell_top.paragraphs[0].runs[0]
            run.bold = True
            run.font.size = Pt(36)
            
            mil_cell_top.merge(table.rows[len(table.rows)-1].cells[3]) 

        else:
            first_row_idx = len(table.rows)
            for ts in time_slots:
                row = table.add_row()
                row.cells[1].text = f'{ts.start_time.strftime("%H:%M")}-{ts.end_time.strftime("%H:%M")}'
                
                slot = ScheduleSlot.objects.filter(
                    group=group, semester=active_semester, day_of_week=day_num, time_slot=ts, is_active=True
                ).first()
                
                if slot:
                    cell_text = f"{slot.subject.name} ({slot.get_lesson_type_display()})\n"
                    if slot.teacher:
                        cell_text += f"{slot.teacher.user.get_full_name()}"
                    row.cells[2].text = cell_text
                    row.cells[3].text = slot.room if slot.room else ""
                
            day_cell = table.rows[first_row_idx].cells[0]
            day_cell.text = day_name
            day_cell.paragraphs[0].runs[0].bold = True
            day_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            day_cell.merge(table.rows[len(table.rows)-1].cells[0])

    doc.add_paragraph().add_run('\n')
    dean_table = doc.add_table(rows=1, cols=2)
    dean_table.autofit = True
    dean_table.width = section.page_width
    
    dean_cell = dean_table.cell(0, 0)
    dean_name = faculty.dean_manager.user.get_full_name() if hasattr(faculty, 'dean_manager') else "________________"
    p = dean_cell.paragraphs[0]
    p.add_run(f"Декани факултети\n{faculty.name}").bold = True
    
    dean_sign = dean_table.cell(0, 1)
    p_s = dean_sign.paragraphs[0]
    p_s.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_s.add_run(f"________ {dean_name}").bold = True

    f = BytesIO()
    doc.save(f)
    f.seek(0)
    
    filename = f"Jadval_{group.name}.docx"
    response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response







