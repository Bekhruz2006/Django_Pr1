# schedule/views.py - ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
import json

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


# ========== HELPER ==========
def get_time_slots_for_shift(shift):
    """Возвращает временные слоты в зависимости от смены"""
    if shift == 'MORNING':
        return TimeSlot.objects.filter(
            start_time__gte='08:00:00',
            start_time__lt='14:00:00'
        ).order_by('start_time')
    else:  # DAY
        return TimeSlot.objects.filter(
            start_time__gte='13:00:00',
            start_time__lt='19:00:00'
        ).order_by('start_time')


# ============ КОНСТРУКТОР РАСПИСАНИЯ (ИСПРАВЛЕН) ============
@login_required
@user_passes_test(is_dean)
def schedule_constructor(request):
    """✅ ИСПРАВЛЕНО: Правильный подсчет по типам занятий + фильтрация семестров по курсу группы"""
    selected_group_id = request.GET.get('group')
    selected_semester_id = request.GET.get('semester')

    groups = Group.objects.all().order_by('name')

    # Фильтруем семестры в зависимости от выбранной группы
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

    # Выбор семестра
    if not selected_semester_id:
        if selected_group_id:
            group = Group.objects.get(id=selected_group_id)
            selected_semester = Semester.get_active(course=group.course)
        else:
            selected_semester = Semester.get_active()
    else:
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            if selected_group_id:
                group = Group.objects.get(id=selected_group_id)
                if selected_semester.course != group.course:
                    messages.error(request, f'❌ Семестр для {selected_semester.course} курса, а группа {group.name} на {group.course} курсе!')
                    selected_semester = Semester.get_active(course=group.course)
        except Semester.DoesNotExist:
            selected_semester = Semester.get_active()

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

            # Фильтр: только предметы этой группы
            assigned_subjects = Subject.objects.filter(
                groups=selected_group
            ).select_related('teacher__user')

            # ✅ ИСПРАВЛЕНО: Считаем по типам ОТДЕЛЬНО с фильтром по lesson_type
            for subject in assigned_subjects:
                slots_needed = subject.get_weekly_slots_needed()

                # ========== ЛЕКЦИИ ==========
                if slots_needed['LECTURE'] > 0:
                    # ✅ ИСПРАВЛЕНО: Фильтруем ТОЛЬКО лекции
                    existing_lectures = ScheduleSlot.objects.filter(
                        subject=subject,
                        group=selected_group,
                        semester=selected_semester,
                        lesson_type='LECTURE',  # ← ДОБАВЛЕНО
                        is_active=True
                    ).count()

                    remaining = max(0, slots_needed['LECTURE'] - existing_lectures)

                    if remaining > 0:
                        lecture_subjects.append({
                            'subject': subject,
                            'remaining': remaining,
                            'needed': slots_needed['LECTURE'],
                            'hours_per_week': subject.lecture_hours_per_week
                        })

                # ========== ПРАКТИКИ ==========
                if slots_needed['PRACTICE'] > 0:
                    # ✅ ИСПРАВЛЕНО: Фильтруем ТОЛЬКО практики
                    existing_practices = ScheduleSlot.objects.filter(
                        subject=subject,
                        group=selected_group,
                        semester=selected_semester,
                        lesson_type='PRACTICE',  # ← ДОБАВЛЕНО
                        is_active=True
                    ).count()

                    remaining = max(0, slots_needed['PRACTICE'] - existing_practices)

                    if remaining > 0:
                        practice_subjects.append({
                            'subject': subject,
                            'remaining': remaining,
                            'needed': slots_needed['PRACTICE'],
                            'hours_per_week': subject.practice_hours_per_week
                        })

                # ========== КМРО ==========
                if slots_needed['SRSP'] > 0:
                    # ✅ ИСПРАВЛЕНО: Фильтруем ТОЛЬКО КМРО
                    existing_control = ScheduleSlot.objects.filter(
                        subject=subject,
                        group=selected_group,
                        semester=selected_semester,
                        lesson_type='SRSP',  # ← ДОБАВЛЕНО
                        is_active=True
                    ).count()

                    remaining = max(0, slots_needed['SRSP'] - existing_control)

                    if remaining > 0:
                        control_subjects.append({
                            'subject': subject,
                            'remaining': remaining,
                            'needed': slots_needed['SRSP'],
                            'hours_per_week': subject.control_hours_per_week
                        })

            # Получаем существующее расписание
            schedule_slots = ScheduleSlot.objects.filter(
                group=selected_group,
                semester=selected_semester,
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


# ============ AJAX ENDPOINTS ============
@login_required
@require_POST
def create_schedule_slot(request):
    """✅ ИСПРАВЛЕНО: Создание занятия С ТИПОМ"""
    try:
        data = json.loads(request.body)
        group_id = data.get('group')
        subject_id = data.get('subject')
        day_of_week = data.get('day_of_week')
        time_slot_id = data.get('time_slot')
        lesson_type = data.get('lesson_type', 'LECTURE')  # ✅ НОВЫЙ ПАРАМЕТР

        if not all([group_id, subject_id, day_of_week is not None, time_slot_id]):
            return JsonResponse({'success': False, 'error': 'Не хватает данных'}, status=400)

        active_semester = Semester.get_active()
        if not active_semester:
            return JsonResponse({'success': False, 'error': 'Активный семестр не найден'}, status=400)

        try:
            group = Group.objects.get(id=group_id)
            subject = Subject.objects.get(id=subject_id)
            time_slot = TimeSlot.objects.get(id=time_slot_id)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Объект не найден: {str(e)}'}, status=404)

        # Проверка конфликтов
        if ScheduleSlot.objects.filter(
            group=group, day_of_week=day_of_week, time_slot=time_slot,
            semester=active_semester, is_active=True
        ).exists():
            return JsonResponse({
                'success': False,
                'error': f'⚠️ У группы {group.name} уже есть занятие в это время'
            }, status=400)

        if subject.teacher:
            teacher_conflict = ScheduleSlot.objects.filter(
                teacher=subject.teacher, day_of_week=day_of_week, time_slot=time_slot,
                semester=active_semester, is_active=True
            ).exclude(group=group)

            if teacher_conflict.exists():
                existing = teacher_conflict.first()
                return JsonResponse({
                    'success': False,
                    'error': f'❌ Преподаватель {subject.teacher.user.get_full_name()} занят (группа {existing.group.name})'
                }, status=400)

        # ✅ Создаем занятие С ТИПОМ
        schedule_slot = ScheduleSlot.objects.create(
            group=group, 
            subject=subject, 
            day_of_week=day_of_week,
            time_slot=time_slot, 
            semester=active_semester,
            teacher=subject.teacher, 
            lesson_type=lesson_type,  # ✅ ДОБАВЛЕНО
            room=None
        )

        return JsonResponse({'success': True, 'slot': {'id': schedule_slot.id}})

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка: {str(e)}'}, status=500)


@login_required
@require_POST
def update_schedule_room(request, slot_id):
    """Обновление номера кабинета"""
    try:
        data = json.loads(request.body)
        room = data.get('room', '').strip()
        
        schedule_slot = ScheduleSlot.objects.get(id=slot_id)
        
        if room:
            classroom_exists = Classroom.objects.filter(number=room, is_active=True).exists()
            if not classroom_exists:
                return JsonResponse({
                    'success': False,
                    'error': f'❌ Кабинет {room} не найден. Добавьте его в "Управление кабинетами".'
                }, status=400)
        
        schedule_slot.room = room if room else None
        schedule_slot.save()
        
        return JsonResponse({'success': True, 'room': schedule_slot.room or '?'})

    except ScheduleSlot.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Занятие не найдено'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка: {str(e)}'}, status=500)


@login_required
@require_POST
def delete_schedule_slot(request, slot_id):
    """Удаление занятия"""
    try:
        schedule_slot = ScheduleSlot.objects.get(id=slot_id)

        if not (request.user.is_staff or hasattr(request.user, 'dean_profile')):
            return JsonResponse({'success': False, 'error': 'Нет прав'}, status=403)

        schedule_slot.delete()
        return JsonResponse({'success': True, 'message': 'Занятие удалено'})

    except ScheduleSlot.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Занятие не найдено'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Ошибка: {str(e)}'}, status=500)


# ============ ОСТАЛЬНЫЕ VIEWS БЕЗ ИЗМЕНЕНИЙ ============
@login_required
def schedule_view(request):
    """Просмотр расписания"""
    user = request.user
    group = None
    
    # ✅ ИСПРАВЛЕНО: Получаем активный семестр с учетом курса
    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                active_semester = Semester.objects.filter(
                    course=group.course, is_active=True
                ).first()
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
            # ✅ Получаем семестр для курса этой группы
            active_semester = Semester.objects.filter(
                course=group.course, is_active=True
            ).first()
            if not active_semester:
                messages.warning(request, f'Нет активного семестра для {group.course} курса')
        
        context = {'groups': groups, 'group': group, 'active_semester': active_semester}
        if not group:
            return render(request, 'schedule/schedule_view_unified.html', context)

    if group and active_semester:
        time_slots = get_time_slots_for_shift(active_semester.shift)
        days = [(0, 'ДУШАНБЕ'), (1, 'СЕШАНБЕ'), (2, 'ЧОРШАНБЕ'), (3, 'ПАНҶШАНБЕ'), (4, 'ҶУМЪА'), (5, 'ШАНБЕ')]
        
        slots = ScheduleSlot.objects.filter(
            group=group, semester=active_semester, is_active=True
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
    """Сегодняшние занятия"""
    user = request.user
    today = datetime.now()
    day_of_week = today.weekday()
    current_time = today.time()
    
    # ✅ Получаем семестр с учетом курса
    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            if student.group:
                active_semester = Semester.objects.filter(
                    course=student.group.course, is_active=True
                ).first()
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


# ========== УПРАВЛЕНИЕ (БЕЗ ИЗМЕНЕНИЙ) ==========
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
    semesters = Semester.objects.all()
    active_semester = Semester.objects.filter(is_active=True).first()
    return render(request, 'schedule/manage_semesters.html', {'semesters': semesters, 'active_semester': active_semester})

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
    semester.save()  # Это автоматически деактивирует другие семестры того же курса
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
    """Экспорт расписания в DOCX"""
    if not DOCX_AVAILABLE:
        messages.error(request, 'Библиотека python-docx не установлена')
        return redirect('schedule:view')

    user = request.user
    group = None
    
    group_id = request.GET.get('group')
    if group_id:
        group = get_object_or_404(Group, id=group_id)
    elif user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
        except Student.DoesNotExist:
            messages.error(request, 'Профиль студента не найден')
            return redirect('schedule:view')
    
    if not group:
        messages.error(request, 'Группа не определена')
        return redirect('schedule:view')
    
    # ✅ Получаем семестр для курса группы
    active_semester = Semester.objects.filter(
        course=group.course, is_active=True
    ).first()
    
    if not active_semester:
        messages.error(request, f'Нет активного семестра для {group.course} курса')
        return redirect('schedule:view')

    doc = Document()
    heading