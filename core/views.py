from django.shortcuts import render
from django.contrib.auth.decorators import login_required

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
    
    return render(request, template, context)