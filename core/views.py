from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime
from django.db.models import Avg, Count

@login_required
def dashboard(request):
    user = request.user
    
    template_map = {
        'STUDENT': 'core/dashboard_student.html',
        'TEACHER': 'core/dashboard_teacher.html',
        'DEAN': 'core/dashboard_dean.html',
    }
    
    template = template_map.get(user.role, 'core/dashboard_dean.html')
    
    context = {
        'user': user
    }
    
    # ДОБАВЛЕНО: Загрузка новостей для всех ролей
    from news.models import News
    context['news_list'] = News.objects.filter(is_published=True).order_by('-is_pinned', '-created_at')[:5]
    
    if user.role == 'STUDENT':
        context['profile'] = user.student_profile
    elif user.role == 'TEACHER':
        context['profile'] = user.teacher_profile
    elif user.role == 'DEAN':
        context['profile'] = user.dean_profile
        
        # ИСПРАВЛЕНО: Статистика для декана
        from accounts.models import Student, Teacher, Group
        from journal.models import StudentStatistics
        
        context['total_students'] = Student.objects.count()
        context['total_teachers'] = Teacher.objects.count()
        context['total_groups'] = Group.objects.count()
        
        all_stats = StudentStatistics.objects.all()
        if all_stats.exists():
            context['avg_gpa'] = all_stats.aggregate(Avg('overall_gpa'))['overall_gpa__avg'] or 0
        else:
            context['avg_gpa'] = 0
        
        course_stats = []
        for course_num in range(1, 6):
            groups = Group.objects.filter(course=course_num)
            students = Student.objects.filter(group__course=course_num)
            
            if students.exists():
                stats = StudentStatistics.objects.filter(student__in=students)
                course_stats.append({
                    'course': course_num,
                    'groups_count': groups.count(),
                    'students_count': students.count(),
                    'avg_gpa': stats.aggregate(Avg('overall_gpa'))['overall_gpa__avg'] or 0,
                    'avg_attendance': stats.aggregate(Avg('attendance_percentage'))['attendance_percentage__avg'] or 0,
                })
        
        context['course_stats'] = course_stats
    
    # Расписание на сегодня
    try:
        from schedule.models import ScheduleSlot
        from accounts.models import Student, Teacher
        
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
        
        context['classes'] = classes
        context['current_time'] = current_time
        context['today'] = today
        
    except Exception as e:
        context['classes'] = []
        context['current_time'] = datetime.now().time()
        context['today'] = datetime.now()
    
    return render(request, template, context)