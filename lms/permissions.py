from django.db.models import Q


ADMIN_ROLES    = {'DIRECTOR', 'RECTOR', 'PRO_RECTOR'}
SPECIALIST_ROLES = {'DEAN', 'VICE_DEAN', 'HEAD_OF_DEPT', 'SPECIALIST'}


def get_lms_role(user):
    if not user or not user.is_authenticated:
        return 'ANONYMOUS'
    if user.is_superuser or getattr(user, 'role', '') in ADMIN_ROLES:
        return 'ADMIN'
    if getattr(user, 'role', '') in SPECIALIST_ROLES:
        return 'SPECIALIST'
    if getattr(user, 'role', '') == 'TEACHER':
        return 'TEACHER'
    return 'STUDENT'


def is_lms_admin(user):
    return get_lms_role(user) == 'ADMIN'


def is_lms_specialist(user):
    return get_lms_role(user) in ('ADMIN', 'SPECIALIST')


def is_lms_teacher(user):
    return get_lms_role(user) in ('ADMIN', 'SPECIALIST', 'TEACHER')


def can_manage_course(user, course):
    from .models import CourseEnrolment
    role = get_lms_role(user)
    if role == 'ADMIN':
        return True
    if role == 'SPECIALIST':
        faculty = _get_user_faculty(user)
        if faculty and (course.allowed_faculty == faculty or
                        getattr(course.category, 'faculty', None) == faculty):
            return True
        dept = _get_user_department(user)
        if dept and (course.allowed_department == dept or
                     getattr(course.category, 'department', None) == dept):
            return True
        return False
    if role == 'TEACHER':
        return CourseEnrolment.objects.filter(
            course=course, user=user, role__in=('TEACHER', 'MANAGER')
        ).exists()
    return False


def can_view_course(user, course):
    from .models import CourseEnrolment
    if can_manage_course(user, course):
        return True
    
    role = get_lms_role(user)
    if role == 'SPECIALIST':
        return True
        
    return CourseEnrolment.objects.filter(course=course, user=user, is_active=True).exists()


def get_manageable_courses(user, queryset=None):
    from .models import Course
    qs = queryset if queryset is not None else Course.objects.all()
    role = get_lms_role(user)
    if role == 'ADMIN':
        return qs
    if role == 'SPECIALIST':
        faculty = _get_user_faculty(user)
        dept    = _get_user_department(user)
        filters = Q()
        if faculty:
            filters |= Q(category__faculty=faculty) | Q(allowed_faculty=faculty)
        if dept:
            filters |= Q(category__department=dept) | Q(allowed_department=dept)
        return qs.filter(filters) if filters else qs.none()
    if role == 'TEACHER':
        return qs.filter(enrolments__user=user, enrolments__role__in=('TEACHER', 'MANAGER'))
    return qs.none()


def _get_user_faculty(user):
    for attr in ('dean_profile', 'vicedean_profile'):
        profile = getattr(user, attr, None)
        if profile and getattr(profile, 'faculty', None):
            return profile.faculty
    profile = getattr(user, 'head_of_dept_profile', None)
    if profile and getattr(profile, 'department', None):
        return getattr(profile.department, 'faculty', None)
    return None


def _get_user_department(user):
    profile = getattr(user, 'head_of_dept_profile', None)
    if profile and getattr(profile, 'department', None):
        return profile.department
    profile = getattr(user, 'teacher_profile', None)
    if profile and getattr(profile, 'department', None):
        return profile.department
    return None