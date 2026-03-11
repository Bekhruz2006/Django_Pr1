from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncMonth
from django.utils import timezone
from accounts.models import Student, Teacher, Group, Institute, Department, Order, User
from news.models import News
from journal.models import StudentStatistics
from schedule.models import ScheduleSlot
import json
from datetime import datetime
from schedule.models import Semester, SubjectMaterial

def get_ai_report_status():
    active_sems = Semester.objects.filter(is_active=True)
    ai_report_ready = False
    days_until_report = 30
    
    for sem in active_sems:
        if sem.start_date:
            days_passed = (timezone.now().date() - sem.start_date).days
            if days_passed >= 30:
                ai_report_ready = True
                days_until_report = 0
                break
            else:
                if 30 - days_passed < days_until_report:
                    days_until_report = 30 - days_passed
                    
    return ai_report_ready, max(1, days_until_report)


def get_algorithmic_risk_report(faculty=None, limit=5):
    qs = StudentStatistics.objects.filter(student__status='ACTIVE').select_related('student__user', 'student__group')
    
    if faculty:
        qs = qs.filter(student__group__specialty__department__faculty=faculty)
        
    problematic = qs.filter(
        Q(overall_gpa__lt=3.0, overall_gpa__gt=0) | 
        Q(attendance_percentage__lt=70.0, total_lessons__gt=0) | 
        Q(total_absent__gt=8)
    )
    
    risk_list = []
    for stat in problematic:
        reasons = []
        risk_score = 0
        
        if 0 < stat.overall_gpa < 2.5:
            reasons.append(f"Критический средний балл: {stat.overall_gpa:.1f}")
            risk_score += 3
        elif 0 < stat.overall_gpa < 3.0:
            reasons.append(f"Низкий средний балл: {stat.overall_gpa:.1f}")
            risk_score += 1
            
        if stat.total_lessons > 0:
            if stat.attendance_percentage < 50.0:
                reasons.append(f"Критическая посещаемость: {stat.attendance_percentage:.0f}%")
                risk_score += 3
            elif stat.attendance_percentage < 70.0:
                reasons.append(f"Низкая посещаемость: {stat.attendance_percentage:.0f}%")
                risk_score += 1
            
        if stat.total_absent > 15:
            reasons.append(f"Слишком много прогулов: {stat.total_absent} (НБ)")
            risk_score += 2
        elif stat.total_absent > 8:
            reasons.append(f"Частые пропуски: {stat.total_absent} (НБ)")
            risk_score += 1
            
        if risk_score >= 3:
            level = 'HIGH'
            level_display = 'Высокий риск'
            color = 'danger'
        elif risk_score > 0:
            level = 'MEDIUM'
            level_display = 'Средний риск'
            color = 'warning'
        else:
            continue
            
        risk_list.append({
            'student': stat.student,
            'gpa': stat.overall_gpa,
            'level': level,
            'level_display': level_display,
            'color': color,
            'reasons': reasons,
            'score': risk_score
        })
        
    risk_list.sort(key=lambda x: x['score'], reverse=True)
    return risk_list[:limit]


@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}

    context['news_list'] = News.objects.filter(is_published=True).order_by('-is_pinned', '-created_at')[:5]

    ai_report_ready, days_until_report = get_ai_report_status()
    context['ai_report_ready'] = ai_report_ready
    context['days_until_report'] = days_until_report

    if hasattr(user, 'director_profile') or hasattr(user, 'prorector_profile'):
        selected_institute_id = request.GET.get('institute_id')
        selected_institute = None
        institutes = Institute.objects.prefetch_related('faculties').all()

        students_qs = Student.objects.filter(status='ACTIVE')
        teachers_qs = Teacher.objects.all()
        groups_qs = Group.objects.all()
        orders_qs = Order.objects.filter(status='DRAFT').select_related('created_by').prefetch_related('items__student__user', 'items__student__group').order_by('date')


        if selected_institute_id:
            try:
                selected_institute = institutes.get(id=selected_institute_id)
                faculties_ids = selected_institute.faculties.values_list('id', flat=True)
                students_qs = students_qs.filter(group__specialty__department__faculty__in=faculties_ids)
                teachers_qs = teachers_qs.filter(department__faculty__in=faculties_ids)
                groups_qs = groups_qs.filter(specialty__department__faculty__in=faculties_ids)
                orders_qs = orders_qs.filter(
                    items__student__group__specialty__department__faculty__in=faculties_ids
                ).distinct()
            except Institute.DoesNotExist:
                pass

        context.update({
            'institutes': institutes,
            'selected_institute': selected_institute,
            'total_students': students_qs.count(),
            'total_teachers': teachers_qs.count(),
            'total_debtors': students_qs.filter(financing_type='CONTRACT').count(),
            'total_groups': groups_qs.count(),
            'pending_orders': orders_qs[:10],
            'pending_count': orders_qs.count(),
            'risk_report': get_algorithmic_risk_report(limit=5)
        })
        return render(request, 'core/dashboard_rector.html', context)

    elif user.is_superuser:
            selected_institute_id = request.GET.get('institute_id')
            selected_institute = None
            institutes = Institute.objects.prefetch_related('faculties').all()

            students_qs = Student.objects.filter(status='ACTIVE')
            teachers_qs = Teacher.objects.all()
            groups_qs = Group.objects.all()
            departments_qs = Department.objects.all()
            active_semesters = Semester.objects.filter(is_active=True).select_related('faculty')

            if selected_institute_id:
                try:
                    selected_institute = institutes.get(id=selected_institute_id)
                    faculties_ids = selected_institute.faculties.values_list('id', flat=True)
                    
                    students_qs = students_qs.filter(group__specialty__department__faculty__in=faculties_ids)
                    teachers_qs = teachers_qs.filter(department__faculty__in=faculties_ids)
                    groups_qs = groups_qs.filter(specialty__department__faculty__in=faculties_ids)
                    departments_qs = departments_qs.filter(faculty__in=faculties_ids)
                    active_semesters = active_semesters.filter(faculty__institute=selected_institute)
                except Institute.DoesNotExist:
                    pass

            context.update({
                'institutes': institutes,
                'selected_institute': selected_institute,
                'total_students': students_qs.count(),
                'total_groups': groups_qs.count(),
                'total_teachers': teachers_qs.count(),
                'total_departments': departments_qs.count(),
                'total_users': User.objects.count(),
                'latest_orders': Order.objects.all().order_by('-created_at')[:5],
                'active_semesters': active_semesters,
                'risk_report': get_algorithmic_risk_report(limit=5)
            })
            return render(request, 'core/dashboard_admin.html', context)
            
    elif hasattr(user, 'hr_profile'):
        context['total_students'] = Student.objects.filter(status='ACTIVE').count()
        context['unassigned_students'] = Student.objects.filter(group__isnull=True, status='ACTIVE').count()
        context['total_teachers'] = Teacher.objects.count()
        context['latest_users'] = User.objects.order_by('-date_joined')[:10]
        
        return render(request, 'core/dashboard_hr.html', context)

    elif hasattr(user, 'dean_profile') or hasattr(user, 'vicedean_profile'):
        profile = getattr(user, 'dean_profile', None) or getattr(user, 'vicedean_profile', None)
        faculty = profile.faculty if profile else None
        context['profile'] = profile
        context['faculty'] = faculty

        if not Semester.objects.filter(is_active=True).exists():
            messages.warning(request, "Внимание! Активный семестр не выбран. Расписание может не работать.")

        if faculty:
            students_count = Student.objects.filter(group__specialty__department__faculty=faculty).count()
            groups_count = Group.objects.filter(specialty__department__faculty=faculty).count()
            teachers_count = Teacher.objects.filter(department__faculty=faculty).count()

            context.update({
                'students_count': students_count,
                'groups_count': groups_count,
                'teachers_count': teachers_count,
                'departments': Department.objects.filter(faculty=faculty).prefetch_related('specialties'),
                'my_drafts': Order.objects.filter(created_by=user, status='DRAFT').count(),
                'risk_report': get_algorithmic_risk_report(faculty=faculty, limit=5)
            })

            course_stats = []
            chart_courses = []
            chart_gpa = []
            chart_attendance = []

            for course_num in range(1, 6):
                students = Student.objects.filter(
                    group__course=course_num,
                    group__specialty__department__faculty=faculty
                )
                if students.exists():
                    stats = StudentStatistics.objects.filter(student__in=students)
                    avg_gpa = stats.aggregate(Avg('overall_gpa'))['overall_gpa__avg'] or 0
                    avg_att = stats.aggregate(Avg('attendance_percentage'))['attendance_percentage__avg'] or 0

                    course_stats.append({
                        'course': course_num,
                        'students_count': students.count(),
                        'avg_gpa': avg_gpa,
                        'avg_attendance': avg_att,
                    })

                    chart_courses.append(f"{course_num} курс")
                    chart_gpa.append(round(avg_gpa, 2))
                    chart_attendance.append(round(avg_att, 1))

            context['course_stats'] = course_stats
            context['json_courses'] = json.dumps(chart_courses)
            context['json_gpa'] = json.dumps(chart_gpa)
            context['json_attendance'] = json.dumps(chart_attendance)

        return render(request, 'core/dashboard_dean.html', context)

    elif hasattr(user, 'teacher_profile') or hasattr(user, 'head_of_dept_profile'):
            if hasattr(user, 'teacher_profile'):
                context['profile'] = user.teacher_profile
                
                context['my_materials'] = SubjectMaterial.objects.filter(
                    subject__teacher=user.teacher_profile
                ).order_by('-uploaded_at')[:10]
            elif hasattr(user, 'head_of_dept_profile'):
                context['profile'] = user.head_of_dept_profile
            return render(request, 'core/dashboard_teacher.html', context)

    elif hasattr(user, 'student_profile'):
        context['profile'] = user.student_profile
    else:
        context['profile'] = None

    try:
        today = datetime.now()
        day_of_week = today.weekday()
        current_time = today.time()
        classes = []

        if hasattr(user, 'student_profile'):
            try:
                student = user.student_profile
                if student.group:
                    classes = ScheduleSlot.objects.filter(
                        group=student.group,
                        day_of_week=day_of_week,
                        is_active=True
                    ).select_related('subject', 'teacher').order_by('start_time')
            except Exception:
                pass

        elif hasattr(user, 'teacher_profile') or hasattr(user, 'head_of_dept_profile'):
            try:
                if hasattr(user, 'teacher_profile'):
                    teacher = user.teacher_profile
                    classes = ScheduleSlot.objects.filter(
                        teacher=teacher,
                        day_of_week=day_of_week,
                        is_active=True
                    ).select_related('subject', 'group').order_by('start_time')
            except Exception:
                pass

        context['classes'] = classes
        context['current_time'] = current_time
        context['today'] = today

    except Exception:
        context['classes'] = []
        context['current_time'] = datetime.now().time()
        context['today'] = datetime.now()

    return render(request, 'core/dashboard_student.html', context)
