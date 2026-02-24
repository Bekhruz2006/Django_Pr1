from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Course, CourseEnrolment

@login_required
def course_list(request):
    if request.user.is_superuser or request.user.role in ['SPECIALIST', 'DEAN']:
        enrolments = CourseEnrolment.objects.all().select_related('course', 'course__category')
        courses = Course.objects.all().select_related('category')
        user_courses = [{'course': c, 'role': 'MANAGER'} for c in courses]
    else:
        enrolments = CourseEnrolment.objects.filter(user=request.user).select_related('course', 'course__category')
        user_courses = [{'course': e.course, 'role': e.role} for e in enrolments]

    return render(request, 'lms/course_list.html', {
        'user_courses': user_courses
    })

@login_required
def course_detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    is_admin_or_spec = request.user.role in ['SPECIALIST', 'DEAN'] or request.user.is_superuser
    try:
        enrolment = CourseEnrolment.objects.get(course=course, user=request.user)
        user_role = enrolment.role
    except CourseEnrolment.DoesNotExist:
        if not is_admin_or_spec:
            return render(request, 'core/error.html', {'message': 'У вас нет доступа к этому курсу'})
        user_role = 'MANAGER'

    sections = course.sections.filter(is_visible=True).prefetch_related('modules')
    
    course_data = []
    for section in sections:
        modules_data = []
        for mod in section.modules.filter(is_visible=True).order_by('sequence'):
            icons = {
                'RESOURCE': 'bi-file-earmark-text text-primary',
                'ASSIGNMENT': 'bi-journal-arrow-up text-danger',
                'QUIZ': 'bi-ui-checks text-success',
                'URL': 'bi-link-45deg text-info',
                'FORUM': 'bi-chat-left-text text-warning'
            }
            modules_data.append({
                'base': mod,
                'icon': icons.get(mod.module_type, 'bi-box')
            })
            
        course_data.append({
            'section': section,
            'modules': modules_data
        })

    return render(request, 'lms/course_detail.html', {
        'course': course,
        'course_data': course_data,
        'user_role': user_role,
        'can_edit': user_role in ['TEACHER', 'MANAGER'] or is_admin_or_spec
    })