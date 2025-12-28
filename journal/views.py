from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
import json

from .models import JournalEntry, JournalChangeLog, StudentStatistics
from .forms import JournalEntryForm, BulkGradeForm, JournalFilterForm, ChangeLogFilterForm
from accounts.models import Student, Teacher, Group
from schedule.models import Subject, ScheduleSlot, AcademicWeek

def is_teacher(user):
    return user.is_authenticated and user.role == 'TEACHER'

def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'

def is_student(user):
    return user.is_authenticated and user.role == 'STUDENT'


@login_required
@user_passes_test(is_teacher)
def journal_view(request):
    """Главный интерфейс преподавателя - таблица журнала"""
    teacher = request.user.teacher_profile
    
    # Фильтрация
    group_id = request.GET.get('group')
    subject_id = request.GET.get('subject')
    week_num = request.GET.get('week')
    
    if not group_id or not subject_id:
        # Показать форму выбора
        form = JournalFilterForm(teacher=teacher)
        return render(request, 'journal/select_journal.html', {'form': form})
    
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    
    # Определение недели
    current_week = AcademicWeek.get_current()
    if week_num:
        week_num = int(week_num)
    elif current_week:
        week_num = current_week.current_week
    else:
        week_num = 1
    
    # Получение расписания для этой группы и предмета
    schedule_slots = ScheduleSlot.objects.filter(
        group=group,
        subject=subject,
        is_active=True
    ).order_by('day_of_week', 'start_time')
    
    if not schedule_slots.exists():
        messages.warning(request, f'Расписание для группы {group.name} по предмету {subject.name} не найдено')
        return redirect('journal:journal_view')
    
    # Вычисление дат занятий на выбранной неделе
    if current_week:
        week_start = current_week.semester_start_date + timedelta(weeks=week_num - 1)
    else:
        week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
    
    # Создание структуры данных для таблицы
    students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
    
    # Дни недели с занятиями
    days_with_lessons = []
    for slot in schedule_slots:
        lesson_date = week_start + timedelta(days=slot.day_of_week)
        days_with_lessons.append({
            'date': lesson_date,
            'time': slot.start_time,
            'day_name': slot.get_day_of_week_display(),
            'slot': slot
        })
    
    # Получение или создание записей
    journal_data = []
    for student in students:
        student_row = {
            'student': student,
            'entries': []
        }
        
        for day_info in days_with_lessons:
            entry, created = JournalEntry.objects.get_or_create(
                student=student,
                subject=subject,
                lesson_date=day_info['date'],
                lesson_time=day_info['time'],
                defaults={
                    'lesson_type': subject.type,
                    'created_by': teacher,
                    'modified_by': teacher,
                }
            )
            
            student_row['entries'].append({
                'entry': entry,
                'is_locked': entry.is_locked(),
                'form': JournalEntryForm(instance=entry, user=request.user, prefix=f'entry_{entry.id}')
            })
        
        journal_data.append(student_row)
    
    # Сводная статистика по дням
    day_stats = []
    for day_info in days_with_lessons:
        day_entries = JournalEntry.objects.filter(
            subject=subject,
            lesson_date=day_info['date'],
            lesson_time=day_info['time']
        )
        
        total = day_entries.count()
        present = day_entries.filter(attendance_status='PRESENT').count()
        avg_grade = day_entries.filter(grade__isnull=False).aggregate(Avg('grade'))['grade__avg'] or 0
        
        day_stats.append({
            'attendance_pct': (present / total * 100) if total > 0 else 0,
            'avg_grade': round(avg_grade, 1)
        })
    
    context = {
        'group': group,
        'subject': subject,
        'week_num': week_num,
        'days_with_lessons': days_with_lessons,
        'journal_data': journal_data,
        'day_stats': day_stats,
        'can_edit': True,  # Преподаватель может редактировать (с учетом блокировки)
    }
    
    return render(request, 'journal/journal_table.html', context)


@login_required
@user_passes_test(is_teacher)
def update_entry(request, entry_id):
    """Обновление одной ячейки журнала"""
    entry = get_object_or_404(JournalEntry, id=entry_id)
    teacher = request.user.teacher_profile
    
    # КРИТИЧНО! Проверка блокировки
    if entry.is_locked():
        messages.error(request, '🔒 Эта запись заблокирована! Прошло более 24 часов с начала занятия.')
        return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))
    
    # Проверка прав (преподаватель ведет этот предмет)
    if entry.subject.teacher != teacher:
        messages.error(request, 'У вас нет прав на редактирование этой записи')
        return redirect('journal:journal_view')
    
    if request.method == 'POST':
        # Сохранение старых значений для лога
        old_grade = entry.grade
        old_attendance = entry.attendance_status
        
        form = JournalEntryForm(request.POST, instance=entry, user=request.user, prefix=f'entry_{entry.id}')
        
        if form.is_valid():
            with transaction.atomic():
                entry = form.save(commit=False)
                entry.modified_by = teacher
                entry.save()
                
                # ОБЯЗАТЕЛЬНОЕ логирование КАЖДОГО изменения
                JournalChangeLog.objects.create(
                    entry=entry,
                    changed_by=teacher,
                    old_grade=old_grade,
                    old_attendance=old_attendance,
                    new_grade=entry.grade,
                    new_attendance=entry.attendance_status,
                    comment=request.POST.get('comment', '')
                )
                
                # Пересчет статистики студента
                stats, _ = StudentStatistics.objects.get_or_create(student=entry.student)
                stats.recalculate()
                
                messages.success(request, f'Запись для {entry.student.user.get_full_name()} обновлена')
        else:
            messages.error(request, 'Ошибка валидации формы')
    
    return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))


@login_required
@user_passes_test(is_teacher)
def bulk_update(request):
    """Массовое заполнение оценок"""
    if request.method != 'POST':
        return redirect('journal:journal_view')
    
    teacher = request.user.teacher_profile
    
    group_id = request.POST.get('group_id')
    subject_id = request.POST.get('subject_id')
    lesson_date = request.POST.get('lesson_date')
    lesson_time = request.POST.get('lesson_time')
    
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    
    students_queryset = Student.objects.filter(group=group)
    form = BulkGradeForm(request.POST, students_queryset=students_queryset)
    
    if form.is_valid():
        selected_students = form.cleaned_data['students']
        grade = form.cleaned_data.get('grade')
        attendance = form.cleaned_data.get('attendance_status')
        
        updated_count = 0
        locked_count = 0
        
        with transaction.atomic():
            for student_id in selected_students:
                student = Student.objects.get(id=student_id)
                
                try:
                    entry = JournalEntry.objects.get(
                        student=student,
                        subject=subject,
                        lesson_date=lesson_date,
                        lesson_time=lesson_time
                    )
                    
                    # Проверка блокировки
                    if entry.is_locked():
                        locked_count += 1
                        continue
                    
                    # Сохранение старых значений
                    old_grade = entry.grade
                    old_attendance = entry.attendance_status
                    
                    # Обновление
                    if grade:
                        entry.grade = grade
                        entry.attendance_status = 'PRESENT'
                    elif attendance:
                        entry.attendance_status = attendance
                        entry.grade = None
                    
                    entry.modified_by = teacher
                    entry.save()
                    
                    # Логирование
                    JournalChangeLog.objects.create(
                        entry=entry,
                        changed_by=teacher,
                        old_grade=old_grade,
                        old_attendance=old_attendance,
                        new_grade=entry.grade,
                        new_attendance=entry.attendance_status,
                        comment="Массовое обновление"
                    )
                    
                    updated_count += 1
                    
                except JournalEntry.DoesNotExist:
                    pass
        
        # Пересчет статистики группы
        StudentStatistics.recalculate_group(group)
        
        if updated_count > 0:
            messages.success(request, f'Обновлено записей: {updated_count}')
        if locked_count > 0:
            messages.warning(request, f'Заблокировано (пропущено) записей: {locked_count}')
    else:
        messages.error(request, 'Ошибка валидации формы')
    
    return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))


@login_required
@user_passes_test(is_teacher)
def change_log_view(request):
    """История изменений"""
    teacher = request.user.teacher_profile
    
    group_id = request.GET.get('group')
    subject_id = request.GET.get('subject')
    
    if not group_id or not subject_id:
        return redirect('journal:journal_view')
    
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    
    # Получение логов
    logs = JournalChangeLog.objects.filter(
        entry__subject=subject,
        entry__student__group=group
    ).select_related('entry__student__user', 'changed_by__user').order_by('-changed_at')
    
    # Фильтрация
    filter_form = ChangeLogFilterForm(request.GET, group=group, subject=subject)
    
    if filter_form.is_valid():
        date_from = filter_form.cleaned_data.get('date_from')
        date_to = filter_form.cleaned_data.get('date_to')
        student_id = filter_form.cleaned_data.get('student')
        teacher_id = filter_form.cleaned_data.get('teacher')
        
        if date_from:
            logs = logs.filter(changed_at__date__gte=date_from)
        if date_to:
            logs = logs.filter(changed_at__date__lte=date_to)
        if student_id:
            logs = logs.filter(entry__student_id=student_id)
        if teacher_id:
            logs = logs.filter(changed_by_id=teacher_id)
    
    context = {
        'logs': logs[:100],  # Ограничение на 100 записей
        'group': group,
        'subject': subject,
        'filter_form': filter_form,
    }
    
    return render(request, 'journal/change_log.html', context)


@login_required
@user_passes_test(is_student)
def student_journal_view(request):
    """Интерфейс студента - просмотр своих оценок"""
    student = request.user.student_profile
    
    # Получение всех записей студента
    entries = JournalEntry.objects.filter(
        student=student
    ).select_related('subject').order_by('lesson_date')
    
    # Группировка по предметам
    subjects_data = {}
    for entry in entries:
        if entry.subject.id not in subjects_data:
            subjects_data[entry.subject.id] = {
                'subject': entry.subject,
                'entries': [],
                'total_grade': 0,
                'count_grades': 0,
                'attended': 0,
                'total_lessons': 0,
            }
        
        subjects_data[entry.subject.id]['entries'].append(entry)
        subjects_data[entry.subject.id]['total_lessons'] += 1
        
        if entry.grade is not None and entry.grade > 0:
            subjects_data[entry.subject.id]['total_grade'] += entry.grade
            subjects_data[entry.subject.id]['count_grades'] += 1
        
        if entry.attendance_status == 'PRESENT':
            subjects_data[entry.subject.id]['attended'] += 1
    
    # Вычисление средних значений
    for subject_id in subjects_data:
        data = subjects_data[subject_id]
        data['avg_grade'] = (
            data['total_grade'] / data['count_grades'] 
            if data['count_grades'] > 0 else 0
        )
        data['attendance_pct'] = (
            data['attended'] / data['total_lessons'] * 100 
            if data['total_lessons'] > 0 else 0
        )
    
    # Статистика
    stats, _ = StudentStatistics.objects.get_or_create(student=student)
    stats.recalculate()
    
    context = {
        'student': student,
        'subjects_data': subjects_data.values(),
        'stats': stats,
    }
    
    return render(request, 'journal/student_view.html', context)


@login_required
@user_passes_test(is_dean)
def dean_journal_view(request):
    """Интерфейс декана - аналитика и просмотр"""
    
    group_id = request.GET.get('group')
    view_type = request.GET.get('view', 'summary')  # summary, details, at_risk
    
    groups = Group.objects.all()
    selected_group = None
    group_stats = None
    at_risk_students = []
    
    if group_id:
        selected_group = get_object_or_404(Group, id=group_id)
        
        # Статистика группы
        students = Student.objects.filter(group=selected_group)
        
        group_stats = {
            'total_students': students.count(),
            'avg_gpa': 0,
            'avg_attendance': 0,
            'subjects': []
        }
        
        # Средние по группе
        all_stats = []
        for student in students:
            stats, _ = StudentStatistics.objects.get_or_create(student=student)
            stats.recalculate()
            all_stats.append(stats)
            
            # Студенты под угрозой
            if stats.overall_gpa < 4.0 or stats.attendance_percentage < 60:
                at_risk_students.append({
                    'student': student,
                    'stats': stats,
                    'reason': []
                })
                if stats.overall_gpa < 4.0:
                    at_risk_students[-1]['reason'].append(f'Низкий балл: {stats.overall_gpa:.1f}')
                if stats.attendance_percentage < 60:
                    at_risk_students[-1]['reason'].append(f'Низкая посещаемость: {stats.attendance_percentage:.0f}%')
        
        if all_stats:
            group_stats['avg_gpa'] = sum(s.overall_gpa for s in all_stats) / len(all_stats)
            group_stats['avg_attendance'] = sum(s.attendance_percentage for s in all_stats) / len(all_stats)
        
        # Статистика по предметам
        subjects = Subject.objects.filter(
            journal_entries__student__group=selected_group
        ).distinct()
        
        for subject in subjects:
            subject_entries = JournalEntry.objects.filter(
                subject=subject,
                student__group=selected_group
            )
            
            grades = subject_entries.filter(grade__isnull=False).aggregate(Avg('grade'))
            attendance = subject_entries.filter(attendance_status='PRESENT').count()
            total = subject_entries.count()
            
            group_stats['subjects'].append({
                'name': subject.name,
                'avg_grade': round(grades['grade__avg'] or 0, 1),
                'attendance_pct': (attendance / total * 100) if total > 0 else 0
            })
    
    context = {
        'groups': groups,
        'selected_group': selected_group,
        'view_type': view_type,
        'group_stats': group_stats,
        'at_risk_students': at_risk_students,
    }
    
    return render(request, 'journal/dean_view.html', context)



# ДОБАВИТЬ В КОНЕЦ journal/views.py:

@login_required
@user_passes_test(is_dean)
def department_report(request):
    """Детальный отчет по всей кафедре"""
    
    sort_by = request.GET.get('sort', 'group')  # group, gpa, attendance
    
    groups = Group.objects.all()
    
    # Собираем статистику по всем группам
    groups_data = []
    
    for group in groups:
        students = Student.objects.filter(group=group)
        
        if not students.exists():
            continue
        
        # Статистика группы
        group_stats = []
        total_gpa = 0
        total_attendance = 0
        count = 0
        
        for student in students:
            stats, _ = StudentStatistics.objects.get_or_create(student=student)
            stats.recalculate()
            
            group_stats.append({
                'student': student,
                'stats': stats,
                'is_at_risk': stats.overall_gpa < 4.0 or stats.attendance_percentage < 60
            })
            
            total_gpa += stats.overall_gpa
            total_attendance += stats.attendance_percentage
            count += 1
        
        # Вычисляем средние по группе
        avg_gpa = total_gpa / count if count > 0 else 0
        avg_attendance = total_attendance / count if count > 0 else 0
        
        groups_data.append({
            'group': group,
            'students_count': count,
            'avg_gpa': avg_gpa,
            'avg_attendance': avg_attendance,
            'students': sorted(group_stats, key=lambda x: x['stats'].overall_gpa, reverse=True),
            'at_risk_count': sum(1 for s in group_stats if s['is_at_risk'])
        })
    
    # Сортировка групп
    if sort_by == 'gpa':
        groups_data.sort(key=lambda x: x['avg_gpa'], reverse=True)
    elif sort_by == 'attendance':
        groups_data.sort(key=lambda x: x['avg_attendance'], reverse=True)
    else:
        groups_data.sort(key=lambda x: x['group'].name)
    
    # Общая статистика по кафедре
    total_students = sum(g['students_count'] for g in groups_data)
    total_at_risk = sum(g['at_risk_count'] for g in groups_data)
    overall_gpa = sum(g['avg_gpa'] * g['students_count'] for g in groups_data) / total_students if total_students > 0 else 0
    overall_attendance = sum(g['avg_attendance'] * g['students_count'] for g in groups_data) / total_students if total_students > 0 else 0
    
    context = {
        'groups_data': groups_data,
        'total_students': total_students,
        'total_at_risk': total_at_risk,
        'overall_gpa': overall_gpa,
        'overall_attendance': overall_attendance,
        'sort_by': sort_by,
    }
    
    return render(request, 'journal/department_report.html', context)


@login_required
@user_passes_test(is_dean)
def group_detailed_report(request, group_id):
    """Детальный отчет по конкретной группе"""
    group = get_object_or_404(Group, id=group_id)
    students = Student.objects.filter(group=group).select_related('user')
    
    # Получаем все предметы группы
    subjects = Subject.objects.filter(
        journal_entries__student__group=group
    ).distinct()
    
    # Собираем данные по каждому студенту
    students_data = []
    for student in students:
        stats, _ = StudentStatistics.objects.get_or_create(student=student)
        stats.recalculate()
        
        # Статистика по предметам
        subjects_performance = []
        for subject in subjects:
            entries = JournalEntry.objects.filter(
                student=student,
                subject=subject
            )
            
            if entries.exists():
                grades = entries.filter(grade__isnull=False).values_list('grade', flat=True)
                avg_grade = sum(grades) / len(grades) if grades else 0
                
                total_lessons = entries.count()
                attended = entries.filter(attendance_status='PRESENT').count()
                attendance_pct = (attended / total_lessons * 100) if total_lessons > 0 else 0
                
                subjects_performance.append({
                    'subject': subject,
                    'avg_grade': avg_grade,
                    'attendance': attendance_pct,
                    'total_lessons': total_lessons,
                })
        
        students_data.append({
            'student': student,
            'stats': stats,
            'subjects': subjects_performance,
            'is_at_risk': stats.overall_gpa < 4.0 or stats.attendance_percentage < 60
        })
    
    # Сортировка по среднему баллу
    students_data.sort(key=lambda x: x['stats'].overall_gpa, reverse=True)
    
    context = {
        'group': group,
        'students_data': students_data,
        'subjects': subjects,
    }
    
    return render(request, 'journal/group_detailed_report.html', context)