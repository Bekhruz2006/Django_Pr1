from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
import json
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from django.utils import timezone
from django.http import JsonResponse
from .models import JournalEntry, JournalChangeLog, StudentStatistics, MatrixStructure, MatrixColumn, StudentMatrixScore
from .forms import JournalEntryForm, BulkGradeForm, JournalFilterForm, ChangeLogFilterForm
from accounts.models import Student, Teacher, Group
from schedule.models import Subject, ScheduleSlot, Semester
from .models import SubjectRating


def get_active_semester_for_group(group):
    from schedule.models import Semester
    if group and group.specialty and group.specialty.department.faculty:
        faculty = group.specialty.department.faculty
        semester = Semester.objects.filter(faculty=faculty, is_active=True, course=group.course).first()
        if semester:
            return semester
    semester = Semester.objects.filter(course=group.course, is_active=True).first()
    if not semester:
        semester = Semester.objects.filter(is_active=True).first()
    return semester

def is_teacher_or_management(user):
    return user.is_authenticated and (
        hasattr(user, 'teacher_profile') or 
        hasattr(user, 'dean_profile') or 
        hasattr(user, 'vicedean_profile') or 
        user.is_superuser
    )



def is_dean_or_admin(user):
    return user.is_authenticated and (
        user.is_superuser or 
        hasattr(user, 'dean_profile') or 
        hasattr(user, 'vicedean_profile')
    )

def is_teacher(user):
    return user.is_authenticated and hasattr(user, 'teacher_profile')

def is_dean(user):
    return user.is_authenticated and hasattr(user, 'dean_profile')

def is_student(user):
    return user.is_authenticated and hasattr(user, 'student_profile')

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from datetime import datetime, timedelta
from django.db.models import Avg

@login_required
@user_passes_test(is_teacher_or_management)
def journal_view(request):
    user_is_admin = is_dean_or_admin(request.user)
    teacher = getattr(request.user, 'teacher_profile', None)

    group_id = request.GET.get('group')
    subject_id = request.GET.get('subject')
    week_num = request.GET.get('week')

    if not group_id or not subject_id:
        form = JournalFilterForm(user=request.user)
        return render(request, 'journal/select_journal.html', {'form': form})

    group = get_object_or_404(Group, id=group_id)

    if user_is_admin:
        subject = get_object_or_404(Subject, id=subject_id)
    else:
        subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)

    schedule_slots = ScheduleSlot.objects.filter(
        group=group,
        subject=subject,
        is_active=True
    )

    if not schedule_slots.exists():
        messages.warning(
            request,
            _('Расписание для группы %(group_name)s по предмету %(subject_name)s не найдено') % {
                'group_name': group.name,
                'subject_name': subject.name
            }
        )
        return redirect('journal:journal_view')

    active_semester = schedule_slots.first().semester

    if week_num:
        week_num = int(week_num)
    else:
        if active_semester:
            week_num = active_semester.get_current_week_number()
        else:
            week_num = 1

    if week_num < 1:
        week_num = 1
    if week_num > 20:
        week_num = 20

    if active_semester and active_semester.start_date:
        week_start = active_semester.start_date + timedelta(weeks=week_num - 1)
    else:
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())

    schedule_slots = schedule_slots.filter(semester=active_semester)

    students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
    days_with_lessons =[]

    current_week_type = 'RED' if week_num % 2 != 0 else 'BLUE'

    for slot in schedule_slots:
        if slot.week_type == 'EVERY' or slot.week_type == current_week_type:
            lesson_date = week_start + timedelta(days=slot.day_of_week)
            days_with_lessons.append({
                'date': lesson_date,
                'time': slot.start_time,
                'day_name': slot.get_day_of_week_display(),
                'slot': slot
            })

    days_with_lessons.sort(key=lambda x: (x['date'], x['time']))

    journal_data =[]
    for student in students:
        student_row = {'student': student, 'entries':[]}
        for day_info in days_with_lessons:
            entry, created = JournalEntry.objects.get_or_create(
                student=student,
                subject=subject,
                lesson_date=day_info['date'],
                lesson_time=day_info['time'],
                defaults={
                    'lesson_type': subject.type,
                    'created_by': teacher,
                    'modified_by': teacher
                }
            )
            student_row['entries'].append({
                'entry': entry,
                'is_locked': entry.is_locked(),
                'form': JournalEntryForm(instance=entry, user=request.user, prefix=f'entry_{entry.id}')
            })
        journal_data.append(student_row)

    day_stats =[]
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

    current_week_actual = active_semester.get_current_week_number() if active_semester else 1
    is_future_week = week_num > current_week_actual

    user_is_admin = is_dean_or_admin(request.user)
    can_edit_weekly_score = user_is_admin or not is_future_week

    faculty = group.specialty.department.faculty if group.specialty else None
    matrix_structure = MatrixStructure.objects.filter(Q(faculty=faculty) | Q(faculty__isnull=True), is_active=True).first()

    weekly_column = None
    weekly_scores_dict = {}
    if matrix_structure:
        weekly_column = MatrixColumn.objects.filter(structure=matrix_structure, col_type='WEEK', week_number=week_num).first()
        if weekly_column:
            scores = StudentMatrixScore.objects.filter(subject=subject, column=weekly_column, student__in=students)
            weekly_scores_dict = {s.student_id: s.score for s in scores}

    for row in journal_data:
        row['weekly_score'] = weekly_scores_dict.get(row['student'].id, "")

    return render(request, 'journal/journal_table_weekly.html', {
        'group': group,
        'subject': subject,
        'week_num': week_num,
        'current_week_actual': current_week_actual,
        'days_with_lessons': days_with_lessons,
        'journal_data': journal_data,
        'day_stats': day_stats,
        'can_edit': True,
        'can_edit_weekly_score': can_edit_weekly_score,
        'is_future_week': is_future_week,
        'user_is_admin': user_is_admin,
        'weekly_column': weekly_column,
        'is_red_week': current_week_type == 'RED'
    })





@login_required
@user_passes_test(is_teacher)
def update_entry(request, entry_id):
    entry = get_object_or_404(JournalEntry, id=entry_id)
    teacher = request.user.teacher_profile

    if entry.is_locked():
        messages.error(request, _('🔒 Запись заблокирована!'))
        return redirect(request.META.get('HTTP_REFERER', 'journal:journal_view'))
    if entry.subject.teacher != teacher:
        messages.error(request, _('Нет прав на редактирование'))
        return redirect('journal:journal_view')

    if request.method == 'POST':
        old_grade, old_attendance = entry.grade, entry.attendance_status
        new_grade = request.POST.get('grade')
        new_attendance = request.POST.get('attendance_status')

        with transaction.atomic():
            if new_grade and new_grade.strip():
                grade_value = int(new_grade)

                active_semester = Semester.objects.filter(
                    is_active=True,
                    course=entry.student.group.course
                ).first()

                if active_semester:
                    week_num = active_semester.get_current_week_number()
                    week_start = active_semester.start_date + timedelta(weeks=week_num - 1)
                    week_end = week_start + timedelta(days=6)

                    weekly_entries = JournalEntry.objects.filter(
                        student=entry.student,
                        subject=entry.subject,
                        lesson_date__gte=week_start,
                        lesson_date__lte=week_end
                    )
                    for weekly_entry in weekly_entries:
                        if not weekly_entry.is_locked():
                            weekly_entry.grade = grade_value
                            weekly_entry.attendance_status = 'PRESENT'
                            weekly_entry.modified_by = teacher
                            weekly_entry.save()
                    messages.success(
                        request,
                        _('✅ Балл %(grade_value)s выставлен за неделю') % {'grade_value': grade_value}
                    )
                else:
                    entry.grade, entry.attendance_status = grade_value, 'PRESENT'
                    entry.modified_by = teacher
                    entry.save()
                    messages.success(
                        request,
                        _('✅ Балл %(grade_value)s выставлен') % {'grade_value': grade_value}
                    )

            elif new_attendance and new_attendance != old_attendance:
                entry.attendance_status = new_attendance
                if new_attendance != 'PRESENT':
                    entry.grade = None
                entry.modified_by = teacher
                entry.save()
                JournalChangeLog.objects.create(
                    entry=entry,
                    changed_by=teacher,
                    old_grade=old_grade,
                    old_attendance=old_attendance,
                    new_grade=entry.grade,
                    new_attendance=entry.attendance_status,
                    comment="Обновление посещаемости"
                )
                messages.success(request, _('✅ НБ обновлено'))

            stats, created = StudentStatistics.objects.get_or_create(student=entry.student)
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
            messages.error(request, _('Выберите статус посещаемости'))
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
            messages.success(request, _('✅ Обновлено: %(updated_count)s') % {'updated_count': updated_count})
        if locked_count > 0:
            messages.warning(request, _('⚠️ Заблокировано: %(locked_count)s') % {'locked_count': locked_count})
    else:
        messages.error(request, _('Ошибка формы'))
    
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
    
    stats, created = StudentStatistics.objects.get_or_create(student=student)
    
    return render(request, 'journal/student_view.html', {
        'student': student, 'subjects_data': subjects_data.values(), 'stats': stats
    })

@login_required
@user_passes_test(is_dean_or_admin)
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
            stats, created = StudentStatistics.objects.get_or_create(student=student)
            
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
@user_passes_test(is_dean_or_admin)
def department_report(request):
    import json
    sort_by = request.GET.get('sort', 'group')
    groups = Group.objects.all()
    groups_data = []

    chart_labels = []
    chart_gpa = []
    chart_attendance = []
    chart_absent_breakdown = {
        'illness': [],
        'valid': [],
        'invalid': []
    }

    for group in groups:
        students = Student.objects.filter(group=group)
        if not students.exists():
            continue

        group_stats = []
        total_gpa = 0
        total_attendance = 0
        total_absent = 0

        g_illness = 0
        g_valid = 0
        g_invalid = 0

        count = 0

        for student in students:
            stats, created = StudentStatistics.objects.get_or_create(student=student)
            
            group_stats.append({
                'student': student, 'stats': stats,
                'is_at_risk': stats.overall_gpa < 3.0 or stats.attendance_percentage < 60
            })
            total_gpa += stats.overall_gpa
            total_attendance += stats.attendance_percentage
            total_absent += stats.total_absent

            g_illness += stats.absent_illness
            g_valid += stats.absent_valid
            g_invalid += stats.absent_invalid

            count += 1

        avg_gpa = round(total_gpa / count, 2) if count > 0 else 0
        avg_attendance = round(total_attendance / count, 1) if count > 0 else 0
        avg_absent = round(total_absent / count, 1) if count > 0 else 0

        groups_data.append({
            'group': group, 'students_count': count,
            'avg_gpa': avg_gpa, 'avg_attendance': avg_attendance,
            'avg_absent': avg_absent, 'total_absent': total_absent,
            'students': sorted(group_stats, key=lambda x: x['stats'].overall_gpa, reverse=True),
            'at_risk_count': sum(1 for s in group_stats if s['is_at_risk'])
        })

        chart_labels.append(group.name)
        chart_gpa.append(avg_gpa)
        chart_attendance.append(avg_attendance)
        chart_absent_breakdown['illness'].append(g_illness)
        chart_absent_breakdown['valid'].append(g_valid)
        chart_absent_breakdown['invalid'].append(g_invalid)

    if sort_by == 'gpa':
        groups_data.sort(key=lambda x: x['avg_gpa'], reverse=True)
    elif sort_by == 'attendance':
        groups_data.sort(key=lambda x: x['avg_attendance'], reverse=True)
    elif sort_by == 'absent':
        groups_data.sort(key=lambda x: x['avg_absent'], reverse=True)
    else:
        groups_data.sort(key=lambda x: x['group'].name)

    risk_data_raw = []
    for item in groups_data:
        risk_data_raw.append({'name': item['group'].name, 'count': item['at_risk_count']})

    risk_data_raw.sort(key=lambda x: x['count'], reverse=True)

    chart_risk_labels = [x['name'] for x in risk_data_raw[:10]]
    chart_risk_values = [x['count'] for x in risk_data_raw[:10]]

    total_students = sum(g['students_count'] for g in groups_data)
    total_at_risk = sum(g['at_risk_count'] for g in groups_data)

    overall_gpa = 0
    overall_attendance = 0
    if total_students > 0:
        overall_gpa = sum(g['avg_gpa'] * g['students_count'] for g in groups_data) / total_students
        overall_attendance = sum(g['avg_attendance'] * g['students_count'] for g in groups_data) / total_students

    overall_absent = sum(g['total_absent'] for g in groups_data)

    context = {
        'groups_data': groups_data,
        'total_students': total_students,
        'total_at_risk': total_at_risk,
        'overall_gpa': overall_gpa,
        'overall_attendance': overall_attendance,
        'overall_absent': overall_absent,
        'sort_by': sort_by,
        'chart_labels': json.dumps(chart_labels),
        'chart_gpa': json.dumps(chart_gpa),
        'chart_attendance': json.dumps(chart_attendance),
        'chart_illness': json.dumps(chart_absent_breakdown['illness']),
        'chart_valid': json.dumps(chart_absent_breakdown['valid']),
        'chart_invalid': json.dumps(chart_absent_breakdown['invalid']),
        'chart_risk_labels': json.dumps(chart_risk_labels),
        'chart_risk_values': json.dumps(chart_risk_values),
    }

    return render(request, 'journal/department_report.html', context)

@login_required
@user_passes_test(is_dean)
def group_detailed_report(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    students = Student.objects.filter(group=group).select_related('user')
    subjects = Subject.objects.filter(journal_entries__student__group=group).distinct()
    students_data = []
    
    for student in students:
        stats, created = StudentStatistics.objects.get_or_create(student=student)
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
            return JsonResponse({'success': False, 'error': _('Запись заблокирована (прошло 24 часа)')}, status=403)
        if entry.subject.teacher != teacher:
            return JsonResponse({'success': False, 'error': _('Это не ваш предмет')}, status=403)

        old_grade = entry.grade
        old_attendance = entry.attendance_status
        
        response_data = {}

        with transaction.atomic():
            if value == '' or value == '-':
                entry.grade = None
                entry.attendance_status = 'PRESENT'
                entry.participation = 'NONE'
                response_data['display'] = ''
                response_data['type'] = 'clear'
                
            elif value in ['н', 'нб', 'nb', 'n', 'abs']:
                entry.grade = None
                entry.attendance_status = 'ABSENT_INVALID' 
                response_data['display'] = 'НБ'
                response_data['type'] = 'absent'
                
            elif value in ['г', 'готов', 'g']:
                entry.participation = 'READY'
                entry.attendance_status = 'PRESENT'
                response_data['display'] = 'Готов'
                response_data['type'] = 'ready'
                
            elif value in ['нг', 'не готов', 'ng']:
                entry.participation = 'NOT_READY'
                entry.attendance_status = 'PRESENT'
                response_data['display'] = 'Не готов'
                response_data['type'] = 'not_ready'
                
            else:
                try:
                    grade = float(value.replace(',', '.'))
                    if 0 <= grade <= 100:
                        entry.grade = grade
                        entry.attendance_status = 'PRESENT'
                        response_data['display'] = str(grade)
                        response_data['type'] = 'grade'
                    else:
                        return JsonResponse({'success': False, 'error': _('Оценка должна быть от 0 до 100')}, status=400)
                except ValueError:
                    return JsonResponse({'success': False, 'error': _('Введите число (до 100), "нб", "г" (готов) или "нг" (не готов)')}, status=400)

            entry.modified_by = teacher
            entry.save()
            if old_grade != entry.grade or old_attendance != entry.attendance_status:
                JournalChangeLog.objects.create(
                    entry=entry, changed_by=teacher,
                    old_grade=old_grade, old_attendance=old_attendance,
                    new_grade=entry.grade, new_attendance=entry.attendance_status,
                    comment="Быстрый ввод"
                )
                
            stats, created = StudentStatistics.objects.get_or_create(student=entry.student)
            stats.recalculate()

        response_data['success'] = True
        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    



@login_required
@user_passes_test(is_teacher_or_management)
def performance_journal_view(request):
    group_id = request.GET.get('group')
    subject_id = request.GET.get('subject')
    
    if not group_id or not subject_id:
        return redirect('journal:journal_view')
        
    group = get_object_or_404(Group, id=group_id)
    subject = get_object_or_404(Subject, id=subject_id)
    
    faculty = group.specialty.department.faculty if group.specialty else None
    matrix_structure = MatrixStructure.objects.filter(Q(faculty=faculty) | Q(faculty__isnull=True), is_active=True).first()
    
    columns =[]
    if matrix_structure:
        columns = matrix_structure.columns.all()
    
    students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
    
    scores = StudentMatrixScore.objects.filter(subject=subject, student__in=students)
    scores_dict = {(s.student_id, s.column_id): s.score for s in scores}
    
    students_data = []
    for s in students:
        student_scores =[]
        total_score = 0
        
        for col in columns:
            val = scores_dict.get((s.id, col.id))
            student_scores.append({
                'column': col,
                'value': val
            })
            if val and col.col_type in['RATING', 'WEEK', 'EXAM']:
                total_score += val 
                
        students_data.append({
            'obj': s,
            'scores': student_scores,
            'total': round(total_score, 2)
        })
        
    return render(request, 'journal/performance_journal.html', {
        'group': group,
        'subject': subject,
        'matrix_structure': matrix_structure,
        'columns': columns,
        'students_data': students_data,
        'is_admin': is_dean_or_admin(request.user)
    })

@login_required
@require_POST
def update_matrix_cell(request):
    import json
    data = json.loads(request.body)
    student_id = data.get('student_id')
    subject_id = data.get('subject_id')
    col_type = data.get('col_type')
    week = data.get('week')
    value = data.get('value', '').strip()
    
    try:
        if col_type not in ['r1', 'r2', 'exam']:
            return JsonResponse({'success': True})

        rating, _ = SubjectRating.objects.get_or_create(student_id=student_id, subject_id=subject_id)
        val_float = float(value.replace(',', '.')) if value else None
        
        if val_float is not None and (val_float < 0 or val_float > 100):
            return JsonResponse({'success': False, 'error': 'Оценка должна быть от 0 до 100'})
            
        if col_type == 'r1' and week == 'pb': rating.r1_pb = val_float
        elif col_type == 'r1' and week == 'to': rating.r1_to = val_float
        elif col_type == 'r2' and week == 'pb': rating.r2_pb = val_float
        elif col_type == 'r2' and week == 'to': rating.r2_to = val_float
        elif col_type == 'exam' and week == 'pb': rating.exam_pb = val_float
        elif col_type == 'exam' and week == 'main': rating.exam_main = val_float
        elif col_type == 'exam' and week == 'dop': rating.exam_dop = val_float
        
        rating.save()
        
        return JsonResponse({
            'success': True,
            'r1_total': f"{rating.r1_total:.2f}" if rating.r1_total is not None else "0.00",
            'r2_total': f"{rating.r2_total:.2f}" if rating.r2_total is not None else "0.00",
            'itogo': f"{rating.itogo:.2f}",
            'letter': rating.letter_grade
        })
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Введите корректное число'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def update_weekly_score(request):
    import json
    from .models import MatrixColumn, StudentMatrixScore
    from accounts.models import Student
    
    data = json.loads(request.body)
    student_id = data.get('student_id')
    subject_id = data.get('subject_id')
    column_id = data.get('column_id')
    value = data.get('value', '').strip()
    
    try:
        column = get_object_or_404(MatrixColumn, id=column_id)
        student = get_object_or_404(Student, id=student_id)
        
        if column.col_type == 'WEEK' and column.week_number:
            active_sem = get_active_semester_for_group(student.group)
            curr_week = active_sem.get_current_week_number() if active_sem else 1
            
            if column.week_number > curr_week and not is_dean_or_admin(request.user):
                return JsonResponse({'success': False, 'error': 'Нельзя выставлять баллы за будущие недели!'})

        score_val = float(value.replace(',', '.')) if value else None
        
        if score_val is not None and (score_val < 0 or score_val > column.max_score):
            return JsonResponse({'success': False, 'error': f'Балл должен быть от 0 до {column.max_score}'})
            
        obj, created = StudentMatrixScore.objects.update_or_create(
            student_id=student_id,
            subject_id=subject_id,
            column=column,
            defaults={'score': score_val, 'updated_by': request.user}
        )
        
        return JsonResponse({'success': True, 'score': obj.score})
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Введите корректное число'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})





@login_required
def matrix_constructor(request):
    if not is_dean_or_admin(request.user):
        messages.error(request, "Доступ запрещен")
        return redirect('core:dashboard')
        
    faculty = None
    institute = None
    
    if hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        institute = faculty.institute if faculty else None
    elif hasattr(request.user, 'director_profile'):
        institute = request.user.director_profile.institute
        
    structure = MatrixStructure.objects.filter(faculty=faculty).first()
    if not structure and institute:
        structure = MatrixStructure.objects.filter(institute=institute, faculty__isnull=True).first()
        
    if not structure:
        structure = MatrixStructure.objects.create(
            institute=institute,
            faculty=faculty,
            name=f"Матрица {faculty.code if faculty else (institute.abbreviation if institute else 'Глобальная')}"
        )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_col':
            MatrixColumn.objects.create(
                structure=structure, 
                name=request.POST.get('name'), 
                col_type=request.POST.get('col_type'),
                max_score=request.POST.get('max_score', 100), 
                order=request.POST.get('order', 0)
            )
            messages.success(request, "Колонка добавлена")
            
        elif action == 'edit_col':
            MatrixColumn.objects.filter(id=request.POST.get('col_id'), structure=structure).update(
                name=request.POST.get('name'), 
                col_type=request.POST.get('col_type'), 
                max_score=request.POST.get('max_score', 100), 
                order=request.POST.get('order', 0)
            )
            messages.success(request, "Колонка обновлена")

        elif action == 'del_col':
            MatrixColumn.objects.filter(id=request.POST.get('col_id'), structure=structure).delete()
            messages.success(request, "Колонка удалена")
            
        return redirect('journal:matrix_constructor')
        
    columns = structure.columns.all().order_by('order', 'id')
    return render(request, 'journal/matrix_constructor.html', {
        'structure': structure,
        'columns': columns
    })



    