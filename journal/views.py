from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta

from django.views.decorators.http import require_POST
from django.utils import timezone


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
    teacher = request.user.teacher_profile
    group_id = request.GET.get('group')
    subject_id = request.GET.get('subject')
    week_num = request.GET.get('week')
    
    if not group_id or not subject_id:
        form = JournalFilterForm(teacher=teacher) 
        return render(request, 'journal/select_journal.html', {'form': form})

    
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    current_week = AcademicWeek.get_current()
    
    if week_num:
        week_num = int(week_num)
    elif current_week:
        week_num = current_week.current_week
    else:
        week_num = 1
    schedule_slots = ScheduleSlot.objects.filter(
        group=group, subject=subject, is_active=True
    ).order_by('day_of_week', 'start_time')
    
    if not schedule_slots.exists():
        messages.warning(request, f'Расписание для группы {group.name} по предмету {subject.name} не найдено')
        return redirect('journal:journal_view')

    if current_week:
        week_start = current_week.semester_start_date + timedelta(weeks=week_num - 1)
    else:
        week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())

    students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
    days_with_lessons = []
    
    for slot in schedule_slots:
        lesson_date = week_start + timedelta(days=slot.day_of_week)
        days_with_lessons.append({
            'date': lesson_date,
            'time': slot.start_time,
            'day_name': slot.get_day_of_week_display(),
            'slot': slot
        })

    journal_data = []
    for student in students:
        student_row = {'student': student, 'entries': []}
        for day_info in days_with_lessons:
            entry, _ = JournalEntry.objects.get_or_create(
                student=student, subject=subject,
                lesson_date=day_info['date'], lesson_time=day_info['time'],
                defaults={'lesson_type': subject.type, 'created_by': teacher, 'modified_by': teacher}
            )
            student_row['entries'].append({
                'entry': entry, 'is_locked': entry.is_locked(),
                'form': JournalEntryForm(instance=entry, user=request.user, prefix=f'entry_{entry.id}')
            })
        journal_data.append(student_row)

    day_stats = []
    for day_info in days_with_lessons:
        day_entries = JournalEntry.objects.filter(
            subject=subject, lesson_date=day_info['date'], lesson_time=day_info['time']
        )
        total = day_entries.count()
        present = day_entries.filter(attendance_status='PRESENT').count()
        avg_grade = day_entries.filter(grade__isnull=False).aggregate(Avg('grade'))['grade__avg'] or 0
        day_stats.append({
            'attendance_pct': (present / total * 100) if total > 0 else 0,
            'avg_grade': round(avg_grade, 1)
        })
    
    return render(request, 'journal/journal_table_weekly.html', {
        'group': group, 'subject': subject, 'week_num': week_num,
        'days_with_lessons': days_with_lessons, 'journal_data': journal_data,
        'day_stats': day_stats, 'can_edit': True
    })

@login_required
@user_passes_test(is_teacher)
def update_entry(request, entry_id):
    entry = get_object_or_404(JournalEntry, id=entry_id)
    teacher = request.user.teacher_profile

    if entry.is_locked():
        messages.error(request, '🔒 Запись заблокирована!')
        return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))
    if entry.subject.teacher != teacher:
        messages.error(request, 'Нет прав на редактирование')
        return redirect('journal:journal_view')
    
    if request.method == 'POST':
        old_grade, old_attendance = entry.grade, entry.attendance_status
        new_grade = request.POST.get('grade')
        new_attendance = request.POST.get('attendance_status')
        
        with transaction.atomic():
            if new_grade and new_grade.strip():
                grade_value = int(new_grade)
                current_week = AcademicWeek.get_current()
                
                if current_week:
                    delta = entry.lesson_date - current_week.semester_start_date
                    week_num = (delta.days // 7) + 1
                    week_start = current_week.semester_start_date + timedelta(weeks=week_num - 1)
                    week_end = week_start + timedelta(days=6)
                    
                    weekly_entries = JournalEntry.objects.filter(
                        student=entry.student, subject=entry.subject,
                        lesson_date__gte=week_start, lesson_date__lte=week_end
                    )
                    for weekly_entry in weekly_entries:
                        if not weekly_entry.is_locked():
                            weekly_entry.grade = grade_value
                            weekly_entry.attendance_status = 'PRESENT'
                            weekly_entry.modified_by = teacher
                            weekly_entry.save()
                    messages.success(request, f'✅ Балл {grade_value} выставлен за неделю')
                else:
                    entry.grade, entry.attendance_status = grade_value, 'PRESENT'
                    entry.modified_by = teacher
                    entry.save()
                    messages.success(request, f'✅ Балл {grade_value} выставлен')
            
            elif new_attendance and new_attendance != old_attendance:
                entry.attendance_status = new_attendance
                if new_attendance != 'PRESENT':
                    entry.grade = None
                entry.modified_by = teacher
                entry.save()
                JournalChangeLog.objects.create(
                    entry=entry, changed_by=teacher,
                    old_grade=old_grade, old_attendance=old_attendance,
                    new_grade=entry.grade, new_attendance=entry.attendance_status,
                    comment="Обновление посещаемости"
                )
                messages.success(request, f'✅ НБ обновлено')
            
            stats, _ = StudentStatistics.objects.get_or_create(student=entry.student)
            stats.recalculate()
    
    return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))

@login_required
@user_passes_test(is_teacher)
def bulk_update(request):
    if request.method != 'POST':
        return redirect('journal:journal_view')
    
    teacher = request.user.teacher_profile
    group_id, subject_id = request.POST.get('group_id'), request.POST.get('subject_id')
    lesson_date, lesson_time = request.POST.get('lesson_date'), request.POST.get('lesson_time')
    
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    
    students_queryset = Student.objects.filter(group=group)
    form = BulkGradeForm(request.POST, students_queryset=students_queryset)
    
    if form.is_valid():
        selected_students = form.cleaned_data['students']
        attendance = form.cleaned_data.get('attendance_status')
        
        if not attendance:
            messages.error(request, 'Выберите статус посещаемости')
            return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))
        
        updated_count = locked_count = 0
        with transaction.atomic():
            for student_id in selected_students:
                student = Student.objects.get(id=student_id)
                try:
                    entry = JournalEntry.objects.get(
                        student=student, subject=subject,
                        lesson_date=lesson_date, lesson_time=lesson_time
                    )
                    if entry.is_locked():
                        locked_count += 1
                        continue
                    
                    old_attendance = entry.attendance_status
                    entry.attendance_status = attendance
                    if attendance != 'PRESENT':
                        entry.grade = None
                    entry.modified_by = teacher
                    entry.save()
                    
                    JournalChangeLog.objects.create(
                        entry=entry, changed_by=teacher,
                        old_grade=entry.grade, old_attendance=old_attendance,
                        new_grade=entry.grade, new_attendance=entry.attendance_status,
                        comment="Массовое обновление НБ"
                    )
                    updated_count += 1
                except JournalEntry.DoesNotExist:
                    pass
        
        StudentStatistics.recalculate_group(group)
        if updated_count > 0:
            messages.success(request, f'✅ Обновлено: {updated_count}')
        if locked_count > 0:
            messages.warning(request, f'⚠️ Заблокировано: {locked_count}')
    else:
        messages.error(request, 'Ошибка формы')
    
    return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))

@login_required
@user_passes_test(is_teacher)
def change_log_view(request):
    teacher = request.user.teacher_profile
    group_id, subject_id = request.GET.get('group'), request.GET.get('subject')
    
    if not group_id or not subject_id:
        return redirect('journal:journal_view')
    
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    logs = JournalChangeLog.objects.filter(
        entry__subject=subject, entry__student__group=group
    ).select_related('entry__student__user', 'changed_by__user').order_by('-changed_at')

    filter_form = ChangeLogFilterForm(request.GET, group=group, subject=subject)
    
    if filter_form.is_valid():
        date_from, date_to = filter_form.cleaned_data.get('date_from'), filter_form.cleaned_data.get('date_to')
        student_id, teacher_id = filter_form.cleaned_data.get('student'), filter_form.cleaned_data.get('teacher')
        
        if date_from:
            logs = logs.filter(changed_at__date__gte=date_from)
        if date_to:
            logs = logs.filter(changed_at__date__lte=date_to)
        if student_id:
            logs = logs.filter(entry__student_id=student_id)
        if teacher_id:
            logs = logs.filter(changed_by_id=teacher_id)
    
    return render(request, 'journal/change_log.html', {
        'logs': logs[:100], 'group': group, 'subject': subject, 'filter_form': filter_form
    })

@login_required
@user_passes_test(is_student)
def student_journal_view(request):
    student = request.user.student_profile
    entries = JournalEntry.objects.filter(student=student).select_related('subject').order_by('lesson_date')
    subjects_data = {}
    
    for entry in entries:
        if entry.subject.id not in subjects_data:
            subjects_data[entry.subject.id] = {
                'subject': entry.subject, 'entries': [],
                'total_grade': 0, 'count_grades': 0,
                'attended': 0, 'total_lessons': 0
            }
        subjects_data[entry.subject.id]['entries'].append(entry)
        subjects_data[entry.subject.id]['total_lessons'] += 1
        if entry.grade:
            subjects_data[entry.subject.id]['total_grade'] += entry.grade
            subjects_data[entry.subject.id]['count_grades'] += 1
        if entry.attendance_status == 'PRESENT':
            subjects_data[entry.subject.id]['attended'] += 1
    
    for subject_id in subjects_data:
        data = subjects_data[subject_id]
        data['avg_grade'] = data['total_grade'] / data['count_grades'] if data['count_grades'] > 0 else 0
        data['attendance_pct'] = data['attended'] / data['total_lessons'] * 100 if data['total_lessons'] > 0 else 0
    
    stats, _ = StudentStatistics.objects.get_or_create(student=student)
    stats.recalculate()
    
    return render(request, 'journal/student_view.html', {
        'student': student, 'subjects_data': subjects_data.values(), 'stats': stats
    })


@login_required
@user_passes_test(is_dean)
def dean_journal_view(request):
    group_id, view_type = request.GET.get('group'), request.GET.get('view', 'summary')
    groups = Group.objects.all()
    selected_group, group_stats, at_risk_students = None, None, []
    
    if group_id:
        selected_group = get_object_or_404(Group, id=group_id)
        students = Student.objects.filter(group=selected_group)
        group_stats = {'total_students': students.count(), 'avg_gpa': 0, 'avg_attendance': 0, 'subjects': []}
        all_stats = []
        
        for student in students:
            stats, _ = StudentStatistics.objects.get_or_create(student=student)
            stats.recalculate()
            all_stats.append(stats)
            if stats.overall_gpa < 4.0 or stats.attendance_percentage < 60:
                at_risk_students.append({
                    'student': student, 'stats': stats, 'reason': []
                })
                if stats.overall_gpa < 4.0:
                    at_risk_students[-1]['reason'].append(f'Низкий балл: {stats.overall_gpa:.1f}')
                if stats.attendance_percentage < 60:
                    at_risk_students[-1]['reason'].append(f'Низкая посещаемость: {stats.attendance_percentage:.0f}%')
        
        if all_stats:
            group_stats['avg_gpa'] = sum(s.overall_gpa for s in all_stats) / len(all_stats)
            group_stats['avg_attendance'] = sum(s.attendance_percentage for s in all_stats) / len(all_stats)
        
        subjects = Subject.objects.filter(
            journal_entries__student__group=selected_group
        ).distinct().select_related('teacher__user')
        
        for subject in subjects:
            subject_entries = JournalEntry.objects.filter(subject=subject, student__group=selected_group)
            grades = subject_entries.filter(grade__isnull=False).aggregate(Avg('grade'))
            attendance, total = subject_entries.filter(attendance_status='PRESENT').count(), subject_entries.count()
            group_stats['subjects'].append({
                'name': subject.name,
                'teacher_name': subject.teacher.user.get_full_name() if subject.teacher else 'Не назначен',
                'avg_grade': round(grades['grade__avg'] or 0, 1),
                'attendance_pct': (attendance / total * 100) if total > 0 else 0
            })
    
    return render(request, 'journal/dean_view.html', {
        'groups': groups, 'selected_group': selected_group, 'view_type': view_type,
        'group_stats': group_stats, 'at_risk_students': at_risk_students
    })

@login_required
@user_passes_test(is_dean)
def department_report(request):
    sort_by = request.GET.get('sort', 'group')
    groups = Group.objects.all()
    groups_data = []
    
    for group in groups:
        students = Student.objects.filter(group=group)
        if not students.exists():
            continue
        
        group_stats = []
        total_gpa = total_attendance = total_absent = count = 0
        
        for student in students:
            stats, _ = StudentStatistics.objects.get_or_create(student=student)
            stats.recalculate()
            group_stats.append({
                'student': student, 'stats': stats,
                'is_at_risk': stats.overall_gpa < 4.0 or stats.attendance_percentage < 60
            })
            total_gpa += stats.overall_gpa
            total_attendance += stats.attendance_percentage
            total_absent += stats.total_absent
            count += 1
        
        avg_gpa = total_gpa / count if count > 0 else 0
        avg_attendance = total_attendance / count if count > 0 else 0
        avg_absent = total_absent / count if count > 0 else 0
        
        groups_data.append({
            'group': group, 'students_count': count,
            'avg_gpa': avg_gpa, 'avg_attendance': avg_attendance,
            'avg_absent': avg_absent, 'total_absent': total_absent,
            'students': sorted(group_stats, key=lambda x: x['stats'].overall_gpa, reverse=True),
            'at_risk_count': sum(1 for s in group_stats if s['is_at_risk'])
        })
    
    if sort_by == 'gpa':
        groups_data.sort(key=lambda x: x['avg_gpa'], reverse=True)
    elif sort_by == 'attendance':
        groups_data.sort(key=lambda x: x['avg_attendance'], reverse=True)
    elif sort_by == 'absent':
        groups_data.sort(key=lambda x: x['avg_absent'], reverse=True)
    else:
        groups_data.sort(key=lambda x: x['group'].name)
    
    total_students = sum(g['students_count'] for g in groups_data)
    total_at_risk = sum(g['at_risk_count'] for g in groups_data)
    overall_gpa = sum(g['avg_gpa'] * g['students_count'] for g in groups_data) / total_students if total_students > 0 else 0
    overall_attendance = sum(g['avg_attendance'] * g['students_count'] for g in groups_data) / total_students if total_students > 0 else 0
    overall_absent = sum(g['total_absent'] for g in groups_data)
    
    return render(request, 'journal/department_report.html', {
        'groups_data': groups_data, 'total_students': total_students,
        'total_at_risk': total_at_risk, 'overall_gpa': overall_gpa,
        'overall_attendance': overall_attendance, 'overall_absent': overall_absent,
        'sort_by': sort_by
    })

@login_required
@user_passes_test(is_dean)
def group_detailed_report(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    students = Student.objects.filter(group=group).select_related('user')
    subjects = Subject.objects.filter(journal_entries__student__group=group).distinct()
    students_data = []
    
    for student in students:
        stats, _ = StudentStatistics.objects.get_or_create(student=student)
        stats.recalculate()
        subjects_performance = []
        
        for subject in subjects:
            entries = JournalEntry.objects.filter(student=student, subject=subject)
            if entries.exists():
                grades = entries.filter(grade__isnull=False).values_list('grade', flat=True)
                avg_grade = sum(grades) / len(grades) if grades else 0
                total_lessons = entries.count()
                attended = entries.filter(attendance_status='PRESENT').count()
                attendance_pct = (attended / total_lessons * 100) if total_lessons > 0 else 0
                absent = total_lessons - attended
                subjects_performance.append({
                    'subject': subject, 'avg_grade': avg_grade,
                    'attendance': attendance_pct, 'total_lessons': total_lessons,
                    'absent': absent
                })
        
        students_data.append({
            'student': student, 'stats': stats,
            'subjects': subjects_performance,
            'is_at_risk': stats.overall_gpa < 4.0 or stats.attendance_percentage < 60
        })
    
    students_data.sort(key=lambda x: x['stats'].overall_gpa, reverse=True)
    
    return render(request, 'journal/group_detailed_report.html', {
        'group': group, 'students_data': students_data, 'subjects': subjects
    })




@login_required
@user_passes_test(is_teacher)
@require_POST
def update_journal_cell(request):
    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')
        value = str(data.get('value', '')).strip().lower()
        
        entry = get_object_or_404(JournalEntry, id=entry_id)
        teacher = request.user.teacher_profile

        if entry.is_locked():
            return JsonResponse({'success': False, 'error': 'Запись заблокирована (прошло 24 часа)'}, status=403)
        if entry.subject.teacher != teacher:
            return JsonResponse({'success': False, 'error': 'Это не ваш предмет'}, status=403)

        old_grade = entry.grade
        old_attendance = entry.attendance_status
        
        response_data = {}

        with transaction.atomic():
            if value == '' or value == '-':
                entry.grade = None
                entry.attendance_status = 'PRESENT'
                response_data['display'] = ''
                
            elif value.isdigit():
                grade = int(value)
                if 1 <= grade <= 12:
                    entry.grade = grade
                    entry.attendance_status = 'PRESENT'
                    response_data['display'] = str(grade)
                    response_data['type'] = 'grade'
                else:
                    return JsonResponse({'success': False, 'error': 'Оценка должна быть от 1 до 12'}, status=400)
            
            elif value in ['н', 'нб', 'nb', 'n', 'abs']:
                entry.grade = None
                entry.attendance_status = 'ABSENT_INVALID' 
                response_data['display'] = 'НБ'
                response_data['type'] = 'absent'
            
            else:
                return JsonResponse({'success': False, 'error': 'Введите число (оценка) или "нб" (прогул)'}, status=400)

            entry.modified_by = teacher
            entry.save()

            if old_grade != entry.grade or old_attendance != entry.attendance_status:
                JournalChangeLog.objects.create(
                    entry=entry, changed_by=teacher,
                    old_grade=old_grade, old_attendance=old_attendance,
                    new_grade=entry.grade, new_attendance=entry.attendance_status,
                    comment="Быстрый ввод"
                )
                
            stats, _ = StudentStatistics.objects.get_or_create(student=entry.student)
            stats.recalculate()

        response_data['success'] = True
        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
