from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Q
from django.urls import reverse
from datetime import datetime, timedelta

try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from .models import Subject, ScheduleSlot, ScheduleException, AcademicWeek
from .forms import SubjectForm, ScheduleSlotForm, ScheduleExceptionForm, AcademicWeekForm
from accounts.models import Group, Student, Teacher

def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'

def is_teacher(user):
    return user.is_authenticated and user.role == 'TEACHER'

def is_student(user):
    return user.is_authenticated and user.role == 'STUDENT'


@login_required
def schedule_view(request):
    """Просмотр расписания для всех ролей"""
    user = request.user
    group = None
    schedule_slots = []
    
    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                schedule_slots = ScheduleSlot.objects.filter(
                    group=group,
                    is_active=True
                ).select_related('subject', 'teacher', 'group').order_by('day_of_week', 'start_time')
        except Student.DoesNotExist:
            pass
    
    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            schedule_slots = ScheduleSlot.objects.filter(
                teacher=teacher,
                is_active=True
            ).select_related('subject', 'group').order_by('day_of_week', 'start_time')
        except Teacher.DoesNotExist:
            pass
    
    elif user.role == 'DEAN':
        group_id = request.GET.get('group')
        groups = Group.objects.all()
        
        if group_id:
            group = get_object_or_404(Group, id=group_id)
            schedule_slots = ScheduleSlot.objects.filter(
                group=group,
                is_active=True
            ).select_related('subject', 'teacher').order_by('day_of_week', 'start_time')
        
        return render(request, 'schedule/schedule_dean.html', {
            'groups': groups,
            'selected_group': group,
            'schedule_slots': schedule_slots,
        })
    
    # Организация по дням недели
    schedule_by_day = {}
    for slot in schedule_slots:
        day = slot.get_day_of_week_display()
        if day not in schedule_by_day:
            schedule_by_day[day] = []
        schedule_by_day[day].append(slot)
    
    return render(request, 'schedule/schedule_view.html', {
        'group': group,
        'schedule_by_day': schedule_by_day,
        'schedule_slots': schedule_slots,
    })


@login_required
def today_classes(request):
    """Виджет 'Сегодня' - показывает пары на сегодня"""
    user = request.user
    today = datetime.now()
    day_of_week = today.weekday()
    current_time = today.time()
    
    classes = []
    
    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            if student.group:
                classes = ScheduleSlot.objects.filter(
                    group=student.group,
                    day_of_week=day_of_week,
                    is_active=True
                ).select_related('subject', 'teacher').order_by('start_time')
        except Student.DoesNotExist:
            pass
    
    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            classes = ScheduleSlot.objects.filter(
                teacher=teacher,
                day_of_week=day_of_week,
                is_active=True
            ).select_related('subject', 'group').order_by('start_time')
        except Teacher.DoesNotExist:
            pass
    
    return render(request, 'schedule/today_widget.html', {
        'classes': classes,
        'current_time': current_time,
        'today': today,
    })


@user_passes_test(is_dean)
def schedule_constructor(request):
    """Конструктор расписания для декана"""
    groups = Group.objects.all()
    subjects = Subject.objects.all()
    teachers = Teacher.objects.all()
    
    selected_group_id = request.GET.get('group')
    selected_group = None
    schedule_slots = []
    
    if selected_group_id:
        selected_group = get_object_or_404(Group, id=selected_group_id)
        schedule_slots = ScheduleSlot.objects.filter(
            group=selected_group,
            is_active=True
        ).select_related('subject', 'teacher').order_by('day_of_week', 'start_time')
    
    # Организация по дням и временным слотам
    time_slots = [
        ('08:30', '10:00'),
        ('10:10', '11:40'),
        ('12:10', '13:40'),
        ('13:50', '15:20'),
        ('15:30', '17:00'),
        ('17:10', '18:40'),
    ]
    
    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    # Создание сетки расписания
    schedule_grid = {}
    for i, day in enumerate(days):
        schedule_grid[i] = {}
        for slot in time_slots:
            schedule_grid[i][slot] = None
    
    # Заполнение сетки существующими занятиями
    for slot in schedule_slots:
        time_key = (slot.start_time.strftime('%H:%M'), slot.end_time.strftime('%H:%M'))
        if time_key in time_slots:
            schedule_grid[slot.day_of_week][time_key] = slot
    
    return render(request, 'schedule/constructor.html', {
        'groups': groups,
        'subjects': subjects,
        'teachers': teachers,
        'selected_group': selected_group,
        'schedule_grid': schedule_grid,
        'time_slots': time_slots,
        'days': days,
    })


@user_passes_test(is_dean)
def add_schedule_slot(request):
    """Добавление слота расписания"""
    if request.method == 'POST':
        form = ScheduleSlotForm(request.POST)
        if form.is_valid():
            slot = form.save()
            messages.success(request, 'Занятие успешно добавлено')
            return redirect(f"{reverse('schedule:constructor')}?group={slot.group.id}")
    else:
        form = ScheduleSlotForm()
        
        # Предзаполнение группы если передана
        group_id = request.GET.get('group')
        if group_id:
            form.fields['group'].initial = group_id
    
    return render(request, 'schedule/add_slot.html', {'form': form})


@user_passes_test(is_dean)
def edit_schedule_slot(request, slot_id):
    """Редактирование слота расписания"""
    slot = get_object_or_404(ScheduleSlot, id=slot_id)
    
    if request.method == 'POST':
        form = ScheduleSlotForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
            messages.success(request, 'Занятие успешно обновлено')
            return redirect(f"{reverse('schedule:constructor')}?group={slot.group.id}")
    else:
        form = ScheduleSlotForm(instance=slot)
    
    return render(request, 'schedule/edit_slot.html', {'form': form, 'slot': slot})


@user_passes_test(is_dean)
def delete_schedule_slot(request, slot_id):
    """Удаление слота расписания"""
    slot = get_object_or_404(ScheduleSlot, id=slot_id)
    group_id = slot.group.id
    slot.delete()
    messages.success(request, 'Занятие удалено')
    return redirect(f"{reverse('schedule:constructor')}?group={group_id}")


@user_passes_test(is_dean)
def manage_exceptions(request, slot_id):
    """Управление исключениями для слота"""
    slot = get_object_or_404(ScheduleSlot, id=slot_id)
    exceptions = ScheduleException.objects.filter(schedule_slot=slot)
    
    if request.method == 'POST':
        form = ScheduleExceptionForm(request.POST)
        if form.is_valid():
            exception = form.save(commit=False)
            exception.schedule_slot = slot
            exception.created_by = request.user
            exception.save()
            messages.success(request, 'Исключение добавлено')
            return redirect('schedule:manage_exceptions', slot_id=slot_id)
    else:
        form = ScheduleExceptionForm()
    
    return render(request, 'schedule/manage_exceptions.html', {
        'slot': slot,
        'exceptions': exceptions,
        'form': form,
    })


@user_passes_test(is_dean)
def delete_exception(request, exception_id):
    """Удаление исключения"""
    exception = get_object_or_404(ScheduleException, id=exception_id)
    slot_id = exception.schedule_slot.id
    exception.delete()
    messages.success(request, 'Исключение удалено')
    return redirect('schedule:manage_exceptions', slot_id=slot_id)


@user_passes_test(is_dean)
def manage_academic_week(request):
    """Управление учебными неделями"""
    current_week = AcademicWeek.get_current()
    
    if request.method == 'POST':
        if current_week:
            form = AcademicWeekForm(request.POST, instance=current_week)
        else:
            form = AcademicWeekForm(request.POST)
        
        if form.is_valid():
            week = form.save(commit=False)
            week.is_active = True
            week.save()
            messages.success(request, 'Учебная неделя обновлена')
            return redirect('schedule:manage_academic_week')
    else:
        if current_week:
            form = AcademicWeekForm(instance=current_week)
        else:
            form = AcademicWeekForm()
    
    return render(request, 'schedule/manage_academic_week.html', {
        'form': form,
        'current_week': current_week,
    })


@login_required
def export_schedule(request):
    """Экспорт расписания в DOCX"""
    
    if not DOCX_AVAILABLE:
        messages.error(request, 'Библиотека python-docx не установлена. Установите: pip install python-docx')
        return redirect('schedule:view')
    
    user = request.user
    group = None
    schedule_slots = []
    
    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                schedule_slots = ScheduleSlot.objects.filter(
                    group=group,
                    is_active=True
                ).select_related('subject', 'teacher').order_by('day_of_week', 'start_time')
        except Student.DoesNotExist:
            messages.error(request, 'Профиль студента не найден')
            return redirect('schedule:view')
    
    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            schedule_slots = ScheduleSlot.objects.filter(
                teacher=teacher,
                is_active=True
            ).select_related('subject', 'group').order_by('day_of_week', 'start_time')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль преподавателя не найден')
            return redirect('schedule:view')
    
    elif user.role == 'DEAN':
        group_id = request.GET.get('group')
        if group_id:
            group = get_object_or_404(Group, id=group_id)
            schedule_slots = ScheduleSlot.objects.filter(
                group=group,
                is_active=True
            ).select_related('subject', 'teacher').order_by('day_of_week', 'start_time')
    
    if not schedule_slots:
        messages.error(request, 'Нет данных для экспорта')
        return redirect('schedule:view')
    
    # Создание документа DOCX
    doc = Document()
    
    if group:
        heading = doc.add_heading(f'Расписание группы {group.name}', 0)
    else:
        heading = doc.add_heading(f'Расписание преподавателя {user.get_full_name()}', 0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Создание таблицы
    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    table = doc.add_table(rows=1, cols=7)
    table.style = 'Light Grid Accent 1'
    
    header_cells = table.rows[0].cells
    header_cells[0].text = 'Время'
    for i, day in enumerate(days):
        header_cells[i + 1].text = day
    
    # Организация по дням и времени
    schedule_by_day_time = {}
    for slot in schedule_slots:
        time_key = f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
        if time_key not in schedule_by_day_time:
            schedule_by_day_time[time_key] = {i: None for i in range(6)}
        schedule_by_day_time[time_key][slot.day_of_week] = slot
    
    # Заполнение таблицы
    for time_key in sorted(schedule_by_day_time.keys()):
        row_cells = table.add_row().cells
        row_cells[0].text = time_key
        
        for day_num in range(6):
            slot = schedule_by_day_time[time_key][day_num]
            if slot:
                if user.role == 'TEACHER':
                    cell_text = f"{slot.subject.name}\n{slot.group.name}\n{slot.classroom}"
                else:
                    cell_text = f"{slot.subject.name}\n{slot.teacher.user.get_full_name()}\n{slot.classroom}"
                row_cells[day_num + 1].text = cell_text
    
    # Сохранение
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    filename = f'schedule_{group.name if group else user.username}_{datetime.now().strftime("%Y%m%d")}.docx'
    response['Content-Disposition'] = f'attachment; filename={filename}'
    
    doc.save(response)
    return response


@login_required
def group_list(request):
    """Список групп со студентами"""
    user = request.user
    
    if user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            group_ids = ScheduleSlot.objects.filter(
                teacher=teacher,
                is_active=True
            ).values_list('group_id', flat=True).distinct()
            groups = Group.objects.filter(id__in=group_ids)
        except Teacher.DoesNotExist:
            groups = Group.objects.none()
    
    elif user.role == 'DEAN':
        groups = Group.objects.all()
    
    else:
        messages.error(request, 'Доступ запрещен')
        return redirect('core:dashboard')
    
    # Получение студентов для каждой группы
    groups_with_students = []
    for group in groups:
        students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
        groups_with_students.append({
            'group': group,
            'students': students
        })
    
    return render(request, 'schedule/group_list.html', {
        'groups_with_students': groups_with_students,
    })