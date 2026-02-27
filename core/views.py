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

@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}

    context['news_list'] = News.objects.filter(is_published=True).order_by('-is_pinned', '-created_at')[:5]

    if user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        selected_institute_id = request.GET.get('institute_id')
        selected_institute = None
        institutes = Institute.objects.prefetch_related('faculties').all()

        students_qs = Student.objects.filter(status='ACTIVE')
        teachers_qs = Teacher.objects.all()
        groups_qs = Group.objects.all()
        orders_qs = Order.objects.filter(status='DRAFT').select_related('student__user', 'created_by').order_by('date')

        if selected_institute_id:
            try:
                selected_institute = institutes.get(id=selected_institute_id)
                faculties_ids = selected_institute.faculties.values_list('id', flat=True)
                students_qs = students_qs.filter(group__specialty__department__faculty__in=faculties_ids)
                teachers_qs = teachers_qs.filter(department__faculty__in=faculties_ids)
                groups_qs = groups_qs.filter(specialty__department__faculty__in=faculties_ids)
                orders_qs = orders_qs.filter(student__group__specialty__department__faculty__in=faculties_ids)
                #tye = Null
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
            'pending_count': orders_qs.count()
            
        })
        return render(request, 'core/dashboard_rector.html', context)

    elif user.is_superuser:
        institutes = Institute.objects.prefetch_related('faculties').all()
        context.update({
            'institutes': institutes,
            'total_students': Student.objects.count(),
            'total_users': User.objects.count(),
            'latest_orders': Order.objects.all().order_by('-created_at')[:5],
        })
        return render(request, 'core/dashboard_admin.html', context)
    elif user.role == 'HR':
        context['total_students'] = Student.objects.filter(status='ACTIVE').count()
        context['unassigned_students'] = Student.objects.filter(group__isnull=True, status='ACTIVE').count()
        context['total_teachers'] = Teacher.objects.count()
        context['latest_users'] = User.objects.order_by('-date_joined')[:10]
        
        return render(request, 'core/dashboard_hr.html', context)

    elif user.role in ['DEAN', 'VICE_DEAN']:
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
                'my_drafts': Order.objects.filter(created_by=user, status='DRAFT').count()
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
            #context['json_total_gpa'] = json.dumps(chart_gpa)

        return render(request, 'core/dashboard_dean.html', context)

    elif user.role in ['TEACHER', 'HEAD_OF_DEPT']:
            if hasattr(user, 'teacher_profile'):
                context['profile'] = user.teacher_profile
                
                context['my_materials'] = SubjectMaterial.objects.filter(
                    subject__teacher=user.teacher_profile
                ).order_by('-uploaded_at')[:10]
            elif hasattr(user, 'head_of_dept_profile'):
                context['profile'] = user.head_of_dept_profile
            return render(request, 'core/dashboard_teacher.html', context)

    else:
        context['profile'] = user.student_profile

    try:
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
            except Exception:
                pass

        elif user.role in ['TEACHER', 'HEAD_OF_DEPT']:
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
