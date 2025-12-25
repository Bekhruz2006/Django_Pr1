from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime

@login_required
def dashboard(request):
    user = request.user
    
    template_map = {
        'STUDENT': 'core/dashboard_student.html',
        'TEACHER': 'core/dashboard_teacher.html',
        'DEAN': 'core/dashboard_dean.html',
    }
    
    template = template_map.get(user.role, 'core/dashboard.html')
    
    context = {
        'user': user
    }
    
    if user.role == 'STUDENT':
        context['profile'] = user.student_profile
    elif user.role == 'TEACHER':
        context['profile'] = user.teacher_profile
    elif user.role == 'DEAN':
        context['profile'] = user.dean_profile
    
    # Добавляем данные для виджета "Сегодня"
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
    
    return render(request, template, context)