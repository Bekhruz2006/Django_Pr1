from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Avg
from datetime import datetime
from accounts.models import Student, Teacher, Group, Institute, Faculty, Department
from news.models import News
import json

@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}
    
    template = 'core/dashboard_student.html'

    context['news_list'] = News.objects.filter(is_published=True).order_by('-is_pinned', '-created_at')[:5]

    if user.is_superuser or user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        context.update({
            'total_institutes': Institute.objects.count(),
            'total_faculties': Faculty.objects.count(),
            'total_departments': Department.objects.count(),
            'total_students': Student.objects.count(),
            'total_teachers': Teacher.objects.count(),
            'institutes_list': Institute.objects.prefetch_related(
                'faculties__departments'
            ).annotate(
                fac_count=Count('faculties', distinct=True)
            ).all(),
        })
        return render(request, 'core/dashboard_admin.html', context)

    elif user.role in ['DEAN', 'VICE_DEAN']:
        profile = getattr(user, 'dean_profile', None) or getattr(user, 'vicedean_profile', None)
        faculty = profile.faculty if profile else None
        context['profile'] = profile
        context['faculty'] = faculty

        from schedule.models import Semester
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
                'departments': Department.objects.filter(faculty=faculty).prefetch_related('specialties')
            })

            from journal.models import StudentStatistics
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

    elif user.role in ['TEACHER', 'HEAD_OF_DEPT']:
        if hasattr(user, 'teacher_profile'):
            context['profile'] = user.teacher_profile
        elif hasattr(user, 'head_of_dept_profile'):
            context['profile'] = user.head_of_dept_profile
            
        template = 'core/dashboard_teacher.html'

    elif user.role == 'STUDENT':
        context['profile'] = user.student_profile
        template = 'core/dashboard_student.html'

    try:
        from schedule.models import ScheduleSlot
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

    return render(request, template, context)