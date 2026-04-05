from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db import models
from django.http import HttpResponseForbidden, HttpRequest, JsonResponse
from django.utils.translation import gettext as _
from .services import StudentImportService
from schedule.models import Semester, Subject, AcademicPlan, ScheduleSlot
from django.db.models import Prefetch, Sum
from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncMonth 
from django.utils import timezone
import json
from .document_engine import DocumentGenerator
from .models import (
    User, Student, Teacher, Dean, Group, GroupTransferHistory,
    Department, Specialty, Institute, Faculty, HeadOfDepartment, Director, ProRector, ViceDean,
    DocumentTemplate, Order, OrderItem, Diploma, Specialization
)
from .forms import (
    UserCreateForm, StudentForm, TeacherForm, DeanForm,
    UserEditForm, AdminUserEditForm, CustomPasswordChangeForm, PasswordResetByDeanForm,
    GroupForm, GroupTransferForm, DepartmentCreateForm, SpecialtyCreateForm,
    InstituteForm, FacultyForm, DepartmentForm, SpecialtyForm, HeadOfDepartmentForm,
    OrderForm, DocumentTemplateForm, SpecializationForm
)

from django.core.exceptions import ObjectDoesNotExist
from .forms import InstituteManagementForm, InstituteForm, FacultyFullForm
from django.http import HttpResponse
from typing import List, Optional
from django.core.exceptions import ValidationError
import logging
logger = logging.getLogger(__name__)
from .models import AdmissionPlan
from .forms import AdmissionPlanForm

def is_hr_or_admin(user):
    return user.is_authenticated and (user.is_superuser or hasattr(user, 'hr_profile') or user.role == 'HR')

def is_dean_or_admin(user):
    return user.is_authenticated and (user.is_superuser or hasattr(user, 'dean_profile') or hasattr(user, 'vicedean_profile'))


def generate_student_id():
    from datetime import datetime
    year = datetime.now().year
    base_id = f"{year}S"
    with transaction.atomic():
        last_student = Student.objects.select_for_update().filter(
            student_id__startswith=base_id
        ).order_by('-student_id').first()
        
        if last_student:
            try:
                last_number = int(last_student.student_id[len(base_id):])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        return f"{base_id}{new_number:04d}"

def is_dean(user):
    return user.is_authenticated and hasattr(user, 'dean_profile')

def is_admin_or_rector(user):
    return user.is_authenticated and (user.is_superuser or hasattr(user, 'director_profile') or hasattr(user, 'prorector_profile'))

def is_management(user):
    return user.is_authenticated and user.is_management

def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('core:dashboard')
        else:
            messages.error(request, _('Неверный логин или пароль'))
    
    return render(request, 'accounts/login.html')


@login_required
@require_POST
def update_financing_type(request):
    if not (request.user.is_superuser or request.user.role in ['HR', 'DEAN']):
        return JsonResponse({'success': False, 'error': 'Нет прав'})
    try:
        data = json.loads(request.body)
        ft = data.get('financing_type')
        if ft not in dict(Student.FINANCING_CHOICES):
            return JsonResponse({'success': False, 'error': str(_('Недопустимое значение'))})
        student = Student.objects.get(id=data['student_id'])
        student.financing_type = ft
        student.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, _('Вы успешно вышли из системы'))
    return redirect('accounts:login')

@login_required
def profile_view(request):
    user = request.user
    profile = None
    context = {'profile': profile}
    
    template_name = 'accounts/profile_teacher.html'
    
    if hasattr(user, 'student_profile'):
        profile = user.student_profile
        from journal.models import StudentStatistics, JournalEntry
        
        stats, created = StudentStatistics.objects.get_or_create(student=profile)
        stats.recalculate()
        profile.statistics = stats
        
        monthly_data = JournalEntry.objects.filter(student=profile).annotate(
            month=TruncMonth('lesson_date')
        ).values('month').annotate(
            avg_grade=Avg('grade'),
            total_lessons=Count('id'),
            attended=Count('id', filter=Q(attendance_status='PRESENT'))
        ).order_by('month')

        chart_labels = []
        chart_gpa = []
        chart_attendance = []

        if monthly_data:
            for entry in monthly_data:
                if entry['month']:
                    month_name = entry['month'].strftime('%b')
                    chart_labels.append(month_name)
                    chart_gpa.append(round(entry['avg_grade'] or 0, 2))
                    att_pct = (entry['attended'] / entry['total_lessons'] * 100) if entry['total_lessons'] > 0 else 0
                    chart_attendance.append(round(att_pct, 1))
        else:
            today = timezone.now()
            chart_labels = [today.strftime('%b')] 
            chart_gpa = [0]
            chart_attendance = [0]

        donut_data = [
            stats.attended_lessons,
            stats.absent_illness,
            stats.absent_valid,
            stats.absent_invalid
        ]
        
        if sum(donut_data) == 0:
            donut_data = [1, 0, 0, 0] 
            donut_empty = True
        else:
            donut_empty = False

        context['profile'] = profile
        context['chart_labels'] = json.dumps(chart_labels)
        context['chart_gpa'] = json.dumps(chart_gpa)
        context['chart_attendance'] = json.dumps(chart_attendance)
        context['donut_data'] = json.dumps(donut_data)
        context['donut_empty'] = json.dumps(donut_empty)
        template_name = 'accounts/profile_student.html'
        
    elif hasattr(user, 'teacher_profile'):
        profile = user.teacher_profile
        from schedule.models import ScheduleSlot
        from journal.models import StudentStatistics
        
        group_ids = ScheduleSlot.objects.filter(
            teacher=profile, is_active=True
        ).values_list('group_id', flat=True).distinct()
        
        groups = Group.objects.filter(id__in=group_ids).annotate(
            students_count=Count('students')
        )
        
        all_stats = StudentStatistics.objects.filter(
            student__group__in=groups
        ).values('student__group_id', 'overall_gpa', 'attendance_percentage')

        stats_by_group = {}
        for stat in all_stats:
            g_id = stat['student__group_id']
            if g_id not in stats_by_group:
                stats_by_group[g_id] = {'gpa_sum': 0, 'att_sum': 0, 'count': 0}
            stats_by_group[g_id]['gpa_sum'] += stat['overall_gpa']
            stats_by_group[g_id]['att_sum'] += stat['attendance_percentage']
            stats_by_group[g_id]['count'] += 1
        
        teacher_groups =[]
        for group in groups:
            if group.students_count > 0:
                g_stats = stats_by_group.get(group.id)
                if g_stats and g_stats['count'] > 0:
                    avg_gpa = g_stats['gpa_sum'] / g_stats['count']
                    avg_attendance = g_stats['att_sum'] / g_stats['count']
                else:
                    avg_gpa = 0
                    avg_attendance = 0
                
                teacher_groups.append({
                    'group': group,
                    'students_count': group.students_count,
                    'avg_gpa': avg_gpa,
                    'avg_attendance': avg_attendance,
                })
        
        context['profile'] = profile
        context['teacher_groups'] = teacher_groups
        
        from datetime import datetime
        today = datetime.now()
        day_of_week = today.weekday()
        current_time = today.time()
        
        classes = ScheduleSlot.objects.filter(
            teacher=profile, day_of_week=day_of_week, is_active=True
        ).select_related('subject', 'group').order_by('start_time')
        
        context['classes'] = classes
        context['current_time'] = current_time
        context['today'] = today
        template_name = 'accounts/profile_teacher.html'
        
    elif hasattr(user, 'dean_profile'):
        profile = user.dean_profile
        context['profile'] = profile
        template_name = 'accounts/profile_dean.html'
        
    elif hasattr(user, 'head_of_dept_profile'):
        profile = user.head_of_dept_profile
        context['profile'] = profile
        template_name = 'accounts/profile_teacher.html'
        
    elif hasattr(user, 'director_profile'):
        profile = user.director_profile
        context['profile'] = profile
        template_name = 'accounts/profile_teacher.html'
        
    elif hasattr(user, 'prorector_profile'):
        profile = user.prorector_profile
        context['profile'] = profile
        template_name = 'accounts/profile_teacher.html'
        
    return render(request, template_name, context)

@login_required
def edit_profile(request):
    user = request.user
    
    if request.method == 'POST':
        user_form = UserEditForm(request.POST, request.FILES, instance=user)
        
        profile_forms = []
        if hasattr(user, 'student_profile'):
            profile_forms.append(StudentForm(request.POST, instance=user.student_profile, prefix='student'))
        if hasattr(user, 'teacher_profile'):
            profile_forms.append(TeacherForm(request.POST, instance=user.teacher_profile, prefix='teacher'))
        if hasattr(user, 'dean_profile'):
            profile_forms.append(DeanForm(request.POST, instance=user.dean_profile, prefix='dean'))
        if hasattr(user, 'head_of_dept_profile'):
            profile_forms.append(HeadOfDepartmentForm(request.POST, instance=user.head_of_dept_profile, prefix='head'))
        
        all_valid = user_form.is_valid()
        for pf in profile_forms:
            if not pf.is_valid():
                all_valid = False
                
        if all_valid:
            user_form.save()
            for pf in profile_forms:
                pf.save()
            messages.success(request, _('Профиль успешно обновлен'))
            return redirect('accounts:profile')
    else:
        user_form = UserEditForm(instance=user)
        
        profile_forms = []
        if hasattr(user, 'student_profile'):
            f = StudentForm(instance=user.student_profile, prefix='student')
            f.form_title = _("Профиль Студента")
            profile_forms.append(f)
        if hasattr(user, 'teacher_profile'):
            f = TeacherForm(instance=user.teacher_profile, prefix='teacher')
            f.form_title = _("Профиль Преподавателя")
            profile_forms.append(f)
        if hasattr(user, 'dean_profile'):
            f = DeanForm(instance=user.dean_profile, prefix='dean')
            f.form_title = _("Профиль Декана")
            profile_forms.append(f)
        if hasattr(user, 'head_of_dept_profile'):
            f = HeadOfDepartmentForm(instance=user.head_of_dept_profile, prefix='head')
            f.form_title = _("Профиль Зав. кафедрой")
            profile_forms.append(f)
    
    return render(request, 'accounts/edit_profile.html', {
        'user_form': user_form,
        'profile_forms': profile_forms
    })

@login_required
def change_password(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, _('Пароль успешно изменен'))
            return redirect('accounts:profile')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@user_passes_test(is_management)
def user_management(request):
    role_filter = request.GET.get('role', '')
    dept_filter = request.GET.get('department', '')  
    search = request.GET.get('search', '')

    users = User.objects.all()

    if role_filter:
        users = users.filter(role=role_filter)

    if dept_filter and role_filter == 'TEACHER':
        users = users.filter(teacher_profile__department_id=dept_filter)

    if search:
        users = users.filter(
            models.Q(username__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search)
        )

    users = users.select_related('student_profile', 'teacher_profile', 'dean_profile', 'head_of_dept_profile', 'vicedean_profile', 'prorector_profile', 'director_profile', 'hr_profile', 'specialist_profile')

    users_with_profiles = []
    for user_obj in users:
        profile_id = None
        has_profile = False
        
        if hasattr(user_obj, 'student_profile'):
            profile_id = user_obj.student_profile.id
            has_profile = True
        elif hasattr(user_obj, 'teacher_profile'):
            profile_id = user_obj.teacher_profile.id
            has_profile = True
        elif hasattr(user_obj, 'dean_profile'):
            profile_id = user_obj.dean_profile.id
            has_profile = True
        elif hasattr(user_obj, 'head_of_dept_profile'):
            profile_id = user_obj.head_of_dept_profile.id
            has_profile = True
            
        users_with_profiles.append({
            'user': user_obj,
            'has_profile': has_profile,
            'profile_id': profile_id
        })

    return render(request, 'accounts/user_management.html', {
        'users': users,
        'users_with_profiles': users_with_profiles,
        'role_filter': role_filter,
        'dept_filter': dept_filter, 
        'search': search
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.role == 'HR') 
def import_students(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        specialty_id = request.POST.get('specialty_id') 
        
        if not excel_file.name.endswith('.xlsx'):
            messages.error(request, _('Пожалуйста, загрузите файл .xlsx'))
            return redirect('accounts:import_students')

        try:
            results = StudentImportService.import_from_excel(excel_file, specialty_id)
            messages.success(
                request,
                _("Импортировано: %(created)s студентов.") % {'created': results['created']}
            )
            if results['errors']:
                messages.warning(request, _(f"Ошибки ({len(results['errors'])}): {'; '.join(results['errors'][:3])}..."))
        except Exception as e:
            logger.exception("import_students")
            messages.error(request, _("Критическая ошибка импорта. См. журнал сервера."))
            
        return redirect('accounts:user_management') 
    
    specialties = Specialty.objects.select_related('department__faculty').all().order_by('department__faculty__name', 'name')
    return render(request, 'accounts/import_students.html', {'specialties': specialties})




@user_passes_test(is_hr_or_admin)
def add_user(request):
    department_id = request.GET.get('department')
    initial_data = {}
    
    role_param = request.GET.get('role')
    if role_param:
        initial_data['role'] = role_param

    if request.method == 'POST':
        user_form = UserCreateForm(request.POST, request.FILES, creator=request.user)
        
        if user_form.is_valid():
            with transaction.atomic():
                user = user_form.save()
                role = user_form.cleaned_data['role']
                
                if request.user.role == 'DEAN' and role in ['DIRECTOR', 'RECTOR', 'PRO_RECTOR']:
                    messages.error(request, _("У вас нет прав создавать руководство института."))
                    transaction.set_rollback(True)
                    return redirect('accounts:add_user')

                try:
                    if role == 'STUDENT':
                        student = user.student_profile
                        student.course = 1
                        student.admission_year = 2025
                        for attempt in range(3):
                            try:
                                student.student_id = generate_student_id()
                                student.save()
                                break
                            except IntegrityError:
                                if attempt == 2:
                                    raise
                        
                    elif role == 'TEACHER':
                        teacher = user.teacher_profile
                        if department_id:
                            dept = Department.objects.get(id=department_id)
                            if request.user.role == 'DEAN' and dept.faculty != request.user.dean_profile.faculty:
                                pass 
                            else:
                                teacher.department = dept
                                teacher.save()
                                
                    
                    messages.success(
                        request,
                        _('Пользователь %(username)s (%(role)s) успешно создан.') % {
                            'username': user.username,
                            'role': user.get_role_display()
                        }
                    )
                    
                    if department_id:
                        return redirect('accounts:manage_structure')
                        
                    return redirect('accounts:user_management')
                    
                except Exception as e:
                    logger.exception("add_user profile setup")
                    messages.error(request, _('Ошибка при настройке профиля. См. журнал сервера.'))
    else:
        user_form = UserCreateForm(creator=request.user, initial=initial_data)
    
    return render(request, 'accounts/add_user.html', {'form': user_form})

@user_passes_test(is_management)
def edit_user(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        allowed = True
        if user_obj.role == 'STUDENT' and hasattr(user_obj, 'student_profile'):
            s = user_obj.student_profile
            if s.group and s.group.specialty and s.group.specialty.department.faculty != faculty:
                allowed = False
            elif s.specialty and s.specialty.department.faculty != faculty:
                allowed = False
        elif user_obj.role in ['TEACHER', 'HEAD_OF_DEPT'] and hasattr(user_obj, 'teacher_profile'):
            if user_obj.teacher_profile.department and user_obj.teacher_profile.department.faculty != faculty:
                allowed = False
        if not allowed:
            messages.error(request, _("Нет доступа к этому пользователю"))
            return redirect('accounts:user_management')

    if request.method == 'POST':
        user_form = AdminUserEditForm(request.POST, request.FILES, instance=user_obj)
        
        student_form = StudentForm(request.POST, instance=user_obj.student_profile) if hasattr(user_obj, 'student_profile') else None
        teacher_form = TeacherForm(
            request.POST,
            instance=getattr(user_obj, 'teacher_profile', None)
        )
        dean_form = DeanForm(request.POST, instance=user_obj.dean_profile) if hasattr(user_obj, 'dean_profile') else None
        head_form = HeadOfDepartmentForm(request.POST, instance=user_obj.head_of_dept_profile) if hasattr(user_obj, 'head_of_dept_profile') else None
        
        user_valid = user_form.is_valid()
        student_valid = student_form.is_valid() if student_form else True
        teacher_valid = teacher_form.is_valid() if teacher_form else True
        dean_valid = dean_form.is_valid() if dean_form else True
        head_valid = head_form.is_valid() if head_form else True
        
        if user_valid and student_valid and teacher_valid and dean_valid and head_valid:
            user = user_form.save()
            
            is_teacher_checked = user_form.cleaned_data.get('is_teacher')
            is_head_checked = user_form.cleaned_data.get('is_head_of_dept')
            is_dean_checked = user_form.cleaned_data.get('is_dean')
            
            if is_teacher_checked:
                teacher_obj, created_teacher = Teacher.objects.get_or_create(user=user)
                if teacher_form:
                    teacher_form.instance = teacher_obj
                    teacher_form.save()
            elif hasattr(user, 'teacher_profile'):
                user.teacher_profile.delete()
                
            if is_head_checked:
                head_obj, created_head = HeadOfDepartment.objects.get_or_create(user=user)
                if head_form:
                    head_form.instance = head_obj
                    head_form.save()
            elif hasattr(user, 'head_of_dept_profile'):
                user.head_of_dept_profile.delete()
                
            if is_dean_checked:
                dean_obj, created_dean = Dean.objects.get_or_create(user=user)
                if dean_form:
                    dean_form.instance = dean_obj
                    dean_form.save()
            elif hasattr(user, 'dean_profile'):
                user.dean_profile.delete()

            if student_form:
                student_form.save()

            messages.success(request, _('Пользователь успешно обновлен'))
            return redirect('accounts:user_management')
    else:
        user_form = AdminUserEditForm(instance=user_obj)
        student_form = StudentForm(instance=user_obj.student_profile) if hasattr(user_obj, 'student_profile') else None
        teacher_form = TeacherForm(instance=getattr(user_obj, 'teacher_profile', None))
        dean_form = DeanForm(instance=user_obj.dean_profile) if hasattr(user_obj, 'dean_profile') else None
        head_form = HeadOfDepartmentForm(instance=user_obj.head_of_dept_profile) if hasattr(user_obj, 'head_of_dept_profile') else None
    
    return render(request, 'accounts/edit_user.html', {
        'user_form': user_form,
        'student_form': student_form,
        'teacher_form': teacher_form,
        'dean_form': dean_form,
        'head_form': head_form,
        'user_obj': user_obj
    })

@user_passes_test(is_management)
def reset_password(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)

    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        allowed = True
        if user_obj.role == 'STUDENT' and hasattr(user_obj, 'student_profile'):
            s = user_obj.student_profile
            if s.group and s.group.specialty and s.group.specialty.department.faculty != faculty:
                allowed = False
        elif user_obj.role in ['TEACHER', 'HEAD_OF_DEPT'] and hasattr(user_obj, 'teacher_profile'):
            if user_obj.teacher_profile.department and user_obj.teacher_profile.department.faculty != faculty:
                allowed = False
        if not allowed:
            messages.error(request, _("Нет доступа к этому пользователю"))
            return redirect('accounts:user_management')


    if request.method == 'POST':
        form = PasswordResetByDeanForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            user_obj.set_password(new_password)
            user_obj.save()
            messages.success(
                request,
                _('Пароль для %(username)s успешно сброшен') % {'username': user_obj.username}
            )
            return redirect('accounts:user_management')
    else:
        form = PasswordResetByDeanForm()
    
    return render(request, 'accounts/reset_password.html', {
        'form': form,
        'user_obj': user_obj
    })

@user_passes_test(is_management)
def toggle_user_active(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)

    if user_obj.id == request.user.id:
        messages.error(request, _('❌ Вы не можете заблокировать сам себя!'))
        return redirect('accounts:user_management')

    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        allowed = True
        if user_obj.role == 'STUDENT' and hasattr(user_obj, 'student_profile'):
            s = user_obj.student_profile
            if s.group and s.group.specialty and s.group.specialty.department.faculty != faculty:
                allowed = False
        elif user_obj.role in ['TEACHER', 'HEAD_OF_DEPT'] and hasattr(user_obj, 'teacher_profile'):
            if user_obj.teacher_profile.department and user_obj.teacher_profile.department.faculty != faculty:
                allowed = False
        if not allowed:
            messages.error(request, _("Нет доступа к этому пользователю"))
            return redirect('accounts:user_management')

    if user_obj.is_superuser and not request.user.is_superuser:
        messages.error(request, _('❌ Вы не можете заблокировать суперпользователя!'))
        return redirect('accounts:user_management')

    user_obj.is_active = not user_obj.is_active
    user_obj.save()

    status = _("активирован") if user_obj.is_active else _("заблокирован")
    messages.success(
        request,
        _('Пользователь %(username)s %(status)s') % {'username': user_obj.username, 'status': status}
    )
    return redirect('accounts:user_management')

@user_passes_test(is_management)
def transfer_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if student.group and student.group.specialty and student.group.specialty.department.faculty != faculty:
            messages.error(request, _("Нет доступа к этому студенту"))
            return redirect('accounts:user_management')

    if request.method == 'POST':
        form = GroupTransferForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                old_group = student.group
                new_group = form.cleaned_data['to_group']
                
                if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
                    faculty = request.user.dean_profile.faculty
                    if new_group.specialty and new_group.specialty.department.faculty != faculty:
                        messages.error(request, _("Ошибка: невозможно перевести студента в группу другого факультета."))
                        return render(request, 'accounts/transfer_student.html', {
                            'form': form,
                            'student': student
                        })
                
                GroupTransferHistory.objects.create(
                    student=student,
                    from_group=old_group,
                    to_group=new_group,
                    reason=form.cleaned_data['reason'],
                    transferred_by=request.user
                )
                student.group = new_group
                student.save()
                
                messages.success(
                    request,
                    _('Студент переведен из %(from_group)s в %(to_group)s') % {
                        'from_group': old_group,
                        'to_group': new_group,
                    }
                )
                return redirect('accounts:user_management')
    else:
        form = GroupTransferForm()
    
    return render(request, 'accounts/transfer_student.html', {
        'form': form,
        'student': student
    })

@login_required
def view_user_profile(request, user_id):
    if not is_management(request.user) and not hasattr(request.user, 'teacher_profile'):
         messages.error(request, _('Доступ запрещен'))
         return redirect('core:dashboard')

    user_obj = get_object_or_404(User, id=user_id)
    profile = None
    template = 'accounts/profile_student.html'
    context = {
        'user': user_obj,
        'viewing_as_dean': True
    }

    if hasattr(user_obj, 'student_profile'):
            profile = user_obj.student_profile
            from journal.models import StudentStatistics, JournalEntry
            from django.db.models.functions import TruncMonth
            from django.db.models import Avg, Count, Q
            import json
            
            stats, created = StudentStatistics.objects.get_or_create(student=profile)
            stats.recalculate()
            profile.statistics = stats
            context['profile'] = profile
            context['templates_cert'] = DocumentTemplate.objects.filter(context_type='STUDENT_CERT', is_active=True)
            
            monthly_data = JournalEntry.objects.filter(student=profile).annotate(
                month=TruncMonth('lesson_date')
            ).values('month').annotate(
                avg_grade=Avg('grade'),
                total_lessons=Count('id'),
                attended=Count('id', filter=Q(attendance_status='PRESENT'))
            ).order_by('month')

            chart_labels =[]
            chart_gpa = []
            chart_attendance =[]

            if monthly_data:
                for entry in monthly_data:
                    if entry['month']:
                        month_name = entry['month'].strftime('%b')
                        chart_labels.append(month_name)
                        chart_gpa.append(round(entry['avg_grade'] or 0, 2))
                        att_pct = (entry['attended'] / entry['total_lessons'] * 100) if entry['total_lessons'] > 0 else 0
                        chart_attendance.append(round(att_pct, 1))
            else:
                today = timezone.now()
                chart_labels = [today.strftime('%b')] 
                chart_gpa = [0]
                chart_attendance = [0]

            donut_data =[
                stats.attended_lessons,
                stats.absent_illness,
                stats.absent_valid,
                stats.absent_invalid
            ]
            
            if sum(donut_data) == 0:
                donut_data = [1, 0, 0, 0] 
                donut_empty = True
            else:
                donut_empty = False

            context['chart_labels'] = json.dumps(chart_labels)
            context['chart_gpa'] = json.dumps(chart_gpa)
            context['chart_attendance'] = json.dumps(chart_attendance)
            context['donut_data'] = json.dumps(donut_data)
            context['donut_empty'] = json.dumps(donut_empty)
            
            risk_reasons =[]
            risk_score = 0
            if stats.overall_gpa < 2.5:
                risk_reasons.append(f"Критический средний балл: {stats.overall_gpa:.1f}")
                risk_score += 3
            elif stats.overall_gpa < 3.0:
                risk_reasons.append(f"Низкий средний балл: {stats.overall_gpa:.1f}")
                risk_score += 1
                
            if stats.total_lessons > 0:
                if stats.attendance_percentage < 50.0:
                    risk_reasons.append(f"Критическая посещаемость: {stats.attendance_percentage:.0f}%")
                    risk_score += 3
                elif stats.attendance_percentage < 70.0:
                    risk_reasons.append(f"Низкая посещаемость: {stats.attendance_percentage:.0f}%")
                    risk_score += 1
                
            if stats.total_absent > 15:
                risk_reasons.append(f"Слишком много прогулов: {stats.total_absent} (НБ)")
                risk_score += 2
            elif stats.total_absent > 8:
                risk_reasons.append(f"Частые пропуски: {stats.total_absent} (НБ)")
                risk_score += 1
                
            if risk_score >= 3:
                risk_level = 'Высокий риск'
                risk_color = 'danger'
            elif risk_score > 0:
                risk_level = 'Средний риск'
                risk_color = 'warning'
            else:
                risk_level = 'В норме'
                risk_color = 'success'
                risk_reasons.append("Показатели в пределах нормы")
                
            context['risk_data'] = {
                'level': risk_level,
                'color': risk_color,
                'reasons': risk_reasons
            }
            
            template = 'accounts/profile_student.html'

    elif hasattr(user_obj, 'teacher_profile'):
        profile = user_obj.teacher_profile
        context['profile'] = profile
        template = 'accounts/profile_teacher.html'

    elif hasattr(user_obj, 'dean_profile'):
        profile = user_obj.dean_profile
        context['profile'] = profile
        template = 'accounts/profile_dean.html'
        
    elif hasattr(user_obj, 'head_of_dept_profile'):
        profile = user_obj.head_of_dept_profile
        context['profile'] = profile
        template = 'accounts/profile_teacher.html'

    return render(request, template, context)

@user_passes_test(is_management)
def group_management(request):
    groups = Group.objects.all().order_by('course', 'name')
    
    if hasattr(request.user, 'head_of_dept_profile'):
        groups = groups.filter(specialty__department=request.user.head_of_dept_profile.department)
    elif hasattr(request.user, 'dean_profile'):
        groups = groups.filter(specialty__department__faculty=request.user.dean_profile.faculty)

    search = request.GET.get('search', '')
    course_filter = request.GET.get('course', '')
    
    if search:
        groups = groups.filter(
            models.Q(name__icontains=search) |
            models.Q(specialty__name__icontains=search) |
            models.Q(specialty__code__icontains=search)
        )
    
    if course_filter:
        groups = groups.filter(course=course_filter)
    
    return render(request, 'accounts/group_management.html', {
        'groups': groups,
        'search': search,
        'course_filter': course_filter,
        'is_head_of_dept': hasattr(request.user, 'head_of_dept_profile')
    })

@login_required
def add_group(request):
    if not (request.user.is_superuser or hasattr(request.user, 'dean_profile') or hasattr(request.user, 'vicedean_profile')):
        messages.error(request, _("Нет доступа"))
        return redirect('core:dashboard')

    specialty_id = request.GET.get('specialty') or request.session.get('last_specialty_id')
    
    initial_data = {}
    if specialty_id:
        try:
            specialty = Specialty.objects.get(id=specialty_id)
            if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
                if specialty.department.faculty != request.user.dean_profile.faculty:
                    specialty = None
            if specialty:
                initial_data['specialty'] = specialty
        except Specialty.DoesNotExist:
            pass

    def configure_form(form):
        if hasattr(request.user, 'dean_profile'):
            faculty = request.user.dean_profile.faculty
            if faculty:
                form.fields['specialty'].queryset = Specialty.objects.filter(department__faculty=faculty)

    if request.method == 'POST':
        form = GroupForm(request.POST, instance=None)
        configure_form(form)

        if form.is_valid():
            try:
                group = form.save()
                
                if group.specialty:
                    request.session['last_specialty_id'] = group.specialty.id

                messages.success(
                    request,
                    _('Группа %(name)s успешно создана!') % {'name': group.name}
                )

                if request.GET.get('specialty'):
                    return redirect('accounts:manage_structure')
                return redirect('accounts:group_management')
            except Exception as e:
                logger.exception("add_group")
                messages.error(request, _("Ошибка сохранения. См. журнал сервера."))
    else:
        form = GroupForm(initial=initial_data)
        configure_form(form)

    return render(request, 'accounts/add_group.html', {'form': form})

@user_passes_test(is_management)
def edit_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if group.specialty and group.specialty.department.faculty != faculty:
            messages.error(request, _("Нет доступа к этой группе"))
            return redirect('accounts:group_management')
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                _('Группа %(name)s успешно обновлена') % {'name': group.name}
            )
            return redirect('accounts:group_management')
        else:
            print(_("Ошибки формы:"), form.errors) 
    else:
        form = GroupForm(instance=group)
    return render(request, 'accounts/edit_group.html', {'form': form, 'group': group})

@user_passes_test(is_management)
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if group.specialty and group.specialty.department.faculty != faculty:
            messages.error(request, _("Нет доступа к этой группе"))
            return redirect('accounts:group_management')
    students_count = Student.objects.filter(group=group).count()
    if request.method == 'POST':
        if students_count > 0:
            messages.error(
                request,
                _('Невозможно удалить группу %(name)s. В ней есть %(count)s студентов.') % {
                    'name': group.name,
                    'count': students_count,
                }
            )
        else:
            group.delete()
            messages.success(
                request,
                _('Группа %(name)s успешно удалена') % {'name': group.name}
            )
        return redirect('accounts:group_management')
    return render(request, 'accounts/delete_group.html', {'group': group, 'students_count': students_count})


@login_required
def manage_structure(request):
    from django.db.models import OuterRef, Subquery, IntegerField
 
    if not is_management(request.user):
        return redirect('core:dashboard')
 
    context = {}
    active_semester = Semester.get_current()
 
    if request.user.is_superuser or request.user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
 
        
        
 
        _staff_sq = (
            Teacher.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(cnt=Count('id'))
            .values('cnt')
        )
 
        _credits_sq = (
            Subject.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(total=Sum('credits'))
            .values('total')
        )
 
        _group_sq = (
            Group.objects
            .filter(specialty__department=OuterRef('pk'))
            .values('specialty__department')
            .annotate(cnt=Count('id', distinct=True))
            .values('cnt')
        )
 
        _student_sq = (
            Student.objects
            .filter(
                group__specialty__department=OuterRef('pk'),
                status='ACTIVE',
            )
            .values('group__specialty__department')
            .annotate(cnt=Count('id', distinct=True))
            .values('cnt')
        )
 
        _specialty_sq = (
            Specialty.objects
            .filter(department__faculty=OuterRef('pk'))
            .values('department__faculty')
            .annotate(cnt=Count('id', distinct=True))
            .values('cnt')
        )
 
        
        departments_qs = (
            Department.objects
            .annotate(
                staff_count=Subquery(_staff_sq, output_field=IntegerField()),
                total_credits=Subquery(_credits_sq, output_field=IntegerField()),
                group_count=Subquery(_group_sq, output_field=IntegerField()),
                student_count=Subquery(_student_sq, output_field=IntegerField()),
            )
            .select_related('faculty')
            .prefetch_related(
                Prefetch('head__user'),
                Prefetch(
                    'specialties',
                    queryset=Specialty.objects.prefetch_related('groups'),
                ),
            )
        )
 
        
        faculties_qs = (
            Faculty.objects
            .annotate(
                specialty_count=Subquery(_specialty_sq, output_field=IntegerField()),
            )
            .select_related('institute')
            .prefetch_related(
                Prefetch('dean_manager__user'),
                Prefetch('departments', queryset=departments_qs),
            )
        )
 
        institutes = Institute.objects.prefetch_related(
            Prefetch('directors__user'),
            Prefetch('faculties', queryset=faculties_qs),
        ).all()
 
        
        structure_data = []
        for inst in institutes:
            inst_data = {
                'obj': inst,
                'director': inst.directors.all().first(),
                'faculties': [],
            }
 
            for fac in inst.faculties.all():
                fac_data = {
                    'obj': fac,
                    'specialty_count': getattr(fac, 'specialty_count', 0) or 0,
                    'dean': getattr(fac, 'dean_manager', None),
                    'departments': [],
                }
 
                for dept in fac.departments.all():
                    dept_data = {
                        'obj': dept,
                        'head': getattr(dept, 'head', None),
                        'specialties': dept.specialties.all(),
                        'stats': {
                            
                            'teachers': getattr(dept, 'staff_count', 0) or 0,
                            'groups':   getattr(dept, 'group_count', 0) or 0,
                            'students': getattr(dept, 'student_count', 0) or 0,
                            'total_credits': getattr(dept, 'total_credits', 0) or 0,
                        },
                    }
                    fac_data['departments'].append(dept_data)
 
                inst_data['faculties'].append(fac_data)
 
            structure_data.append(inst_data)
 
        context['structure_data'] = structure_data
        context['is_admin'] = True
 
    elif hasattr(request.user, 'dean_profile') or hasattr(request.user, 'vicedean_profile'):
        user_faculty = None
        if hasattr(request.user, 'dean_profile'):
            user_faculty = request.user.dean_profile.faculty
        elif hasattr(request.user, 'vicedean_profile'):
            user_faculty = request.user.vicedean_profile.faculty
 
        if not user_faculty:
            messages.error(request, _("Ваш профиль не привязан к факультету"))
            return redirect('core:dashboard')
 
        
        from django.db.models import OuterRef, Subquery, IntegerField
 
        _dean_staff_sq = (
            Teacher.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(cnt=Count('id'))
            .values('cnt')
        )
 
        _dean_credits_sq = (
            Subject.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(total=Sum('credits'))
            .values('total')
        )
 
        departments = (
            Department.objects
            .filter(faculty=user_faculty)
            .annotate(
                staff_count=Subquery(_dean_staff_sq, output_field=IntegerField()),
                total_credits=Subquery(_dean_credits_sq, output_field=IntegerField()),
            )
            .prefetch_related(
                Prefetch('head__user'),
                Prefetch(
                    'specialties',
                    queryset=Specialty.objects.prefetch_related(
                        'groups',
                        'academicplan_set',
                    ),
                ),
                Prefetch(
                    'subjects',
                    queryset=Subject.objects.prefetch_related(
                        Prefetch(
                            'scheduleslot_set',
                            queryset=ScheduleSlot.objects.filter(
                                semester=active_semester,
                            ).select_related('semester'),
                        ),
                    ),
                ),
            )
        )
 
        dept_data = []
        for dept in departments:
            current_subjects = [
                s for s in dept.subjects.all()
                if s.scheduleslot_set.all()
            ]
            total_hours = sum(s.total_auditory_hours for s in current_subjects)
            budget = dept.total_hours_budget or 1
            load_percent = round((total_hours / budget) * 100, 1) if dept.total_hours_budget else 0
 
            specs_data = []
            for spec in dept.specialties.all():
                last_plan = spec.academicplan_set.filter(
                    is_active=True
                ).order_by('-admission_year').first()
                specs_data.append({
                    'obj': spec,
                    'groups': spec.groups.all(),
                    'plan': last_plan,
                })
 
            dept_data.append({
                'obj': dept,
                'total_hours': total_hours,
                'load_percent': load_percent,
                'subjects_count': len(current_subjects),
                
                'teachers_count': getattr(dept, 'staff_count', 0) or 0,
                'total_credits':  getattr(dept, 'total_credits', 0) or 0,
                'specialties_data': specs_data,
            })
 
        context['faculty'] = user_faculty
        context['dept_data'] = dept_data
        context['is_dean'] = True
        context['active_semester'] = active_semester
 
    return render(request, 'accounts/structure_manage.html', context)

@user_passes_test(is_admin_or_rector)
def edit_institute(request, pk):
    institute = get_object_or_404(Institute, pk=pk)
    
    current_director = institute.directors.first()
    current_vice = institute.prorectors.filter(title__icontains='таълим').first()
    
    initial_data = {
        'director': current_director.user if current_director else None,
        'vice_director_edu': current_vice.user if current_vice else None,
        'vice_director_edu_title': current_vice.title if current_vice else "Муовини директор оид ба корҳои таълимӣ",
    }

    if request.method == 'POST':
        form = InstituteForm(request.POST, instance=institute)
        mgmt_form = InstituteManagementForm(request.POST)
        
        if form.is_valid() and mgmt_form.is_valid():
            with transaction.atomic():
                form.save()
                
                new_director_user = mgmt_form.cleaned_data['director']
                
                if new_director_user:
                    if new_director_user.role != 'DIRECTOR' and not new_director_user.is_superuser:
                        new_director_user.role = 'DIRECTOR'
                        new_director_user.save()

                    if current_director and current_director.user != new_director_user:
                        current_director.institute = None
                        current_director.save()

                    director_profile, created = Director.objects.get_or_create(user=new_director_user)
                    
                    director_profile.institute = institute
                    director_profile.save()
                
                elif current_director:
                    current_director.institute = None
                    current_director.save()

                new_vice_user = mgmt_form.cleaned_data['vice_director_edu']
                title = mgmt_form.cleaned_data['vice_director_edu_title']
                
                if new_vice_user:
                    if new_vice_user.role != 'PRO_RECTOR' and not new_vice_user.is_superuser:
                        new_vice_user.role = 'PRO_RECTOR'
                        new_vice_user.save()

                    if current_vice and current_vice.user != new_vice_user:
                        current_vice.institute = None
                        current_vice.save()

                    vice_profile, created = ProRector.objects.get_or_create(user=new_vice_user)
                    vice_profile.institute = institute
                    vice_profile.title = title
                    vice_profile.save()

            messages.success(request, _("Институт и руководство обновлены"))
            return redirect('accounts:manage_structure')
    else:
        form = InstituteForm(instance=institute)
        mgmt_form = InstituteManagementForm(initial=initial_data)

    return render(request, 'accounts/edit_institute_full.html', {
        'form': form, 
        'mgmt_form': mgmt_form,
        'institute': institute
    })


@user_passes_test(is_admin_or_rector)
def delete_institute(request, pk):
    institute = get_object_or_404(Institute, pk=pk)
    if request.method == 'POST':
        institute.delete()
        messages.success(request, _("Институт удален"))
        return redirect('accounts:manage_structure')
    return render(request, 'core/confirm_delete.html', {'obj': institute, 'title': 'Удалить Институт'})

@user_passes_test(is_admin_or_rector)
def add_faculty(request):
    initial_data = {}
    institute_id = request.GET.get('institute')
    if institute_id:
        initial_data['institute'] = get_object_or_404(Institute, pk=institute_id)

    if request.method == 'POST':
        form = FacultyFullForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                faculty = form.save()

                dean_user = form.cleaned_data['dean_user']
                if dean_user:
                    if dean_user.role != 'DEAN' and not dean_user.is_superuser:
                        dean_user.role = 'DEAN'
                        dean_user.save()
                    
                    dean_profile, created = Dean.objects.get_or_create(user=dean_user)
                    dean_profile.faculty = faculty
                    dean_profile.office_location = form.cleaned_data['office_location']
                    dean_profile.contact_email = form.cleaned_data['contact_email']
                    dean_profile.save()

                vice_user = form.cleaned_data['vice_dean_user']
                if vice_user:
                    if vice_user.role != 'VICE_DEAN' and not vice_user.is_superuser:
                        vice_user.role = 'VICE_DEAN'
                        vice_user.save()
                    
                    vice_profile, created = ViceDean.objects.get_or_create(user=vice_user)
                    vice_profile.faculty = faculty
                    vice_profile.title = "Муовини декан оид ба таълим" 
                    vice_profile.save()

            messages.success(
                request,
                _("Факультет %(name)s успешно создан!") % {'name': faculty.name}
            )
            return redirect('accounts:manage_structure')
    else:
        form = FacultyFullForm(initial=initial_data)
    
    return render(request, 'core/form_generic.html', {'form': form, 'title': 'Добавить Факультет (Расширенный)'})


@user_passes_test(is_admin_or_rector)
def edit_faculty(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    
    if request.method == 'POST':
        form = FacultyFullForm(request.POST, instance=faculty)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                
                new_dean_user = form.cleaned_data['dean_user']
                current_dean_profile = getattr(faculty, 'dean_manager', None)

                if new_dean_user:
                    if current_dean_profile and current_dean_profile.user != new_dean_user:
                        current_dean_profile.faculty = None
                        current_dean_profile.save()
                    
                    if new_dean_user.role != 'DEAN' and not new_dean_user.is_superuser:
                        new_dean_user.role = 'DEAN'
                        new_dean_user.save()

                    new_profile, created = Dean.objects.get_or_create(user=new_dean_user)
                    new_profile.faculty = faculty
                    new_profile.office_location = form.cleaned_data['office_location']
                    new_profile.contact_email = form.cleaned_data['contact_email']
                    new_profile.save()
                elif current_dean_profile:
                    current_dean_profile.faculty = None
                    current_dean_profile.save()

                new_vice_user = form.cleaned_data['vice_dean_user']
                current_vice_profile = faculty.vice_deans.first()

                if new_vice_user:
                    if current_vice_profile and current_vice_profile.user != new_vice_user:
                        current_vice_profile.faculty = None
                        current_vice_profile.save()
                    
                    if new_vice_user.role != 'VICE_DEAN' and not new_vice_user.is_superuser:
                        new_vice_user.role = 'VICE_DEAN'
                        new_vice_user.save()

                    new_vice_prof, created = ViceDean.objects.get_or_create(user=new_vice_user)
                    new_vice_prof.faculty = faculty
                    new_vice_prof.save()
                elif current_vice_profile:
                    current_vice_profile.faculty = None
                    current_vice_profile.save()

            messages.success(request, _("Факультет и руководство обновлены"))
            return redirect('accounts:manage_structure')
    else:
        form = FacultyFullForm(instance=faculty)

    return render(request, 'accounts/edit_institute_full.html', {
        'form': form, 
        'institute': faculty.institute, 
        'title': f'Редактирование факультета: {faculty.name}'
    })

@user_passes_test(is_admin_or_rector)
def delete_faculty(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if request.method == 'POST':
        faculty.delete()
        messages.success(request, _("Факультет удален"))
        return redirect('accounts:manage_structure')
    return render(request, 'core/confirm_delete.html', {'obj': faculty, 'title': 'Удалить Факультет'})

@login_required
def add_department(request):
    if not is_management(request.user):
        return HttpResponseForbidden()

    initial = {}
    faculty_context = None

    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty_context = request.user.dean_profile.faculty
        initial['faculty'] = faculty_context

    faculty_id = request.GET.get('faculty')
    if faculty_id and is_admin_or_rector(request.user):
        faculty_context = get_object_or_404(Faculty, pk=faculty_id)
        initial['faculty'] = faculty_context

    if request.method == 'POST':
        form = DepartmentForm(request.POST, faculty_context=faculty_context)
        if form.is_valid():
            if is_dean(request.user):
                dean_faculty = request.user.dean_profile.faculty
                if form.cleaned_data['faculty'] != dean_faculty:
                    messages.error(request, _("Вы можете добавлять кафедры только в свой факультет"))
                    return redirect('accounts:manage_structure')

            with transaction.atomic():
                dept = form.save()

                head_user = form.cleaned_data.get('head_of_department')
                if head_user:
                    if head_user.role == 'TEACHER':
                        head_user.role = 'HEAD_OF_DEPT'
                        head_user.save()

                    HeadOfDepartment.objects.update_or_create(
                        user=head_user,
                        defaults={'department': dept}
                    )

            messages.success(
                request,
                _("Кафедра %(name)s создана") % {'name': dept.name}
            )
            return redirect('accounts:manage_structure')
    else:
        form = DepartmentForm(initial=initial, faculty_context=faculty_context)
        if is_dean(request.user) and hasattr(request.user, 'dean_profile') and request.user.dean_profile.faculty:
            faculty = request.user.dean_profile.faculty
            form.fields['faculty'].queryset = Faculty.objects.filter(id=faculty.id)

    return render(request, 'core/form_generic.html', {'form': form, 'title': 'Добавить кафедру'})


@login_required
def edit_department(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if not is_management(request.user):
        return HttpResponseForbidden()

    if is_dean(request.user):
        if dept.faculty != request.user.dean_profile.faculty:
            return HttpResponseForbidden(_("Это не ваша кафедра"))

    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=dept, faculty_context=dept.faculty)
        if form.is_valid():
            with transaction.atomic():
                dept = form.save()

                head_user = form.cleaned_data.get('head_of_department')
                if head_user:
                    if hasattr(dept, 'head') and dept.head.user != head_user:
                        old_head = dept.head
                        old_head.department = None
                        old_head.save()

                    if head_user.role == 'TEACHER':
                        head_user.role = 'HEAD_OF_DEPT'
                        head_user.save()

                    HeadOfDepartment.objects.update_or_create(
                        user=head_user,
                        defaults={'department': dept}
                    )
                elif not head_user and hasattr(dept, 'head'):
                    dept.head.delete()

            messages.success(request, _("Кафедра обновлена"))
            return redirect('accounts:manage_structure')
    else:
        form = DepartmentForm(instance=dept, faculty_context=dept.faculty)
        if is_dean(request.user) and hasattr(request.user, 'dean_profile') and request.user.dean_profile.faculty:
            faculty = request.user.dean_profile.faculty
            form.fields['faculty'].queryset = Faculty.objects.filter(id=faculty.id)

    return render(request, 'core/form_generic.html', {'form': form, 'title': 'Редактировать кафедру'})




@login_required
def delete_department(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if not is_management(request.user):
        return HttpResponseForbidden()
    if is_dean(request.user) and dept.faculty != request.user.dean_profile.faculty:
        return HttpResponseForbidden(_("Это не ваша кафедра"))

    if request.method == 'POST':
        dept.delete()
        messages.success(request, _("Кафедра удалена"))
        return redirect('accounts:manage_structure')
    return render(request, 'core/confirm_delete.html', {'obj': dept, 'title': 'Удалить кафедру'})


@login_required
def add_specialty(request):
    if not is_management(request.user):
        return HttpResponseForbidden()
    
    initial = {}
    dept_id = request.GET.get('department')
    if dept_id:
        initial['department'] = get_object_or_404(Department, id=dept_id)

    if request.method == 'POST':
        form = SpecialtyForm(request.POST)
        if form.is_valid():
            if is_dean(request.user):
                dean_faculty = request.user.dean_profile.faculty
                if form.cleaned_data['department'].faculty != dean_faculty:
                    messages.error(request, _("Ошибка доступа к кафедре"))
                    return redirect('accounts:manage_structure')
            form.save()
            messages.success(request, _("Специальность добавлена"))
            return redirect('accounts:manage_structure')
    else:
        form = SpecialtyForm(initial=initial)
        if is_dean(request.user):
            faculty = request.user.dean_profile.faculty
            form.fields['department'].queryset = Department.objects.filter(faculty=faculty)
        
    return render(request, 'core/form_generic.html', {'form': form, 'title': 'Добавить специальность'})

@login_required
def edit_specialty(request, pk):
    spec = get_object_or_404(Specialty, pk=pk)
    if not is_management(request.user):
        return HttpResponseForbidden()
    
    if is_dean(request.user) and spec.department.faculty != request.user.dean_profile.faculty:
        return HttpResponseForbidden(_("Это не ваша кафедра"))

    if request.method == 'POST':
        form = SpecialtyForm(request.POST, instance=spec)
        if form.is_valid():
            form.save()
            messages.success(request, _("Специальность обновлена"))
            return redirect('accounts:manage_structure')
    else:
        form = SpecialtyForm(instance=spec)
        if is_dean(request.user):
            faculty = request.user.dean_profile.faculty
            form.fields['department'].queryset = Department.objects.filter(faculty=faculty)

    return render(request, 'core/form_generic.html', {'form': form, 'title': 'Редактировать специальность'})


@login_required
def delete_specialty(request, pk):
    spec = get_object_or_404(Specialty, pk=pk)
    if not is_management(request.user):
        return HttpResponseForbidden()
    if is_dean(request.user) and spec.department.faculty != request.user.dean_profile.faculty:
        return HttpResponseForbidden(_("Это не ваша кафедра"))

    if request.method == 'POST':
        spec.delete()
        messages.success(request, _("Специальность удалена"))
        return redirect('accounts:manage_structure')
    return render(request, 'core/confirm_delete.html', {'obj': spec, 'title': 'Удалить специальность'})



@user_passes_test(is_admin_or_rector)
def add_institute(request):
    if request.method == 'POST':
        form = InstituteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Институт добавлен"))
            return redirect('accounts:manage_structure')
    else:
        form = InstituteForm()
    return render(request, 'core/form_generic.html', {'form': form, 'title': 'Добавить Институт'})


@user_passes_test(is_management)
def student_orders(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    orders = student.order_items.select_related('order').all().order_by('-order__date')
    
    if request.method == 'POST':
        form = OrderForm(request.POST, request.FILES)
        if form.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()
            OrderItem.objects.create(
                order=order, 
                student=student,
                reason=form.cleaned_data.get('reason', '')
            )
            messages.success(
                request,
                _('Проект приказа №%(number)s создан.') % {'number': order.number}
            )
            return redirect('accounts:student_orders', student_id=student.id)
    else:
        form = OrderForm(initial={'date': timezone.now().date()})
        
    return render(request, 'accounts/student_orders.html', {
        'student': student,
        'orders': orders,
        'form': form
    })

@user_passes_test(is_management)
def payment_list(request):
    students = Student.objects.filter(financing_type='CONTRACT').select_related('user', 'group')
    
    group_id = request.GET.get('group')
    if group_id:
        try:
            group_id = int(group_id)
            students = students.filter(group_id=group_id)
        except (ValueError, TypeError):
            group_id = None
        
    show_debtors = request.GET.get('debtors')
    
    context_students = []
    for s in students:
        debt = s.contract_amount - s.paid_amount
        if show_debtors and debt <= 0:
            continue
            
        context_students.append({
            'student': s,
            'debt': debt,
            'percent': int((s.paid_amount / s.contract_amount * 100) if s.contract_amount > 0 else 0)
        })
        
    groups = Group.objects.all()
    return render(request, 'accounts/payment_list.html', {
        'students': context_students,
        'groups': groups,
        'show_debtors': show_debtors,
        'group_id': group_id
    })

@user_passes_test(is_management)
def all_orders_list(request):
    search = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    
    orders = Order.objects.select_related('created_by').all()
    
    if search:
        orders = orders.filter(
            models.Q(number__icontains=search) |
            models.Q(title__icontains=search)
        )
    
    if type_filter:
        orders = orders.filter(order_type=type_filter)
        
    return render(request, 'accounts/all_orders_list.html', {
        'orders': orders,
        'search': search,
        'type_filter': type_filter,
        'order_types': Order.ORDER_TYPES
    })





@user_passes_test(lambda u: u.is_superuser or u.role in ['PRO_RECTOR', 'DIRECTOR'])
def approve_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        if order.status == 'DRAFT':
            try:
                order.apply_effect(request.user)
                messages.success(
                    request,
                    _("Приказ №%(number)s утвержден! Статус студентов обновлен.") % {'number': order.number}
                )
            except Exception as e:
                logger.exception("approve_order")
                messages.error(request, _("Ошибка при обработке приказа. См. журнал сервера."))
        else:
            messages.warning(request, _("Приказ уже обработан."))
            
    return redirect('accounts:all_orders') 






@login_required
@user_passes_test(lambda u: u.is_superuser or u.role in ['DEAN', 'VICE_DEAN'])
def unassigned_students(request):
    user = request.user
    faculty = None
    if hasattr(user, 'dean_profile') and getattr(user.dean_profile, 'faculty', None):
        faculty = user.dean_profile.faculty
    elif hasattr(user, 'vicedean_profile') and getattr(user.vicedean_profile, 'faculty', None):
        faculty = user.vicedean_profile.faculty
        
    if user.is_superuser:
        students = Student.objects.filter(group__isnull=True, status='ACTIVE').select_related('user', 'specialty')
        groups = Group.objects.all().select_related('specialty')
    else:
        if not faculty:
            messages.error(request, _("Ваш профиль не привязан к факультету."))
            return redirect('core:dashboard')
        
        if not faculty:
            messages.error(request, _("Ваш профиль не привязан к факультету."))
            return redirect('core:dashboard')
        
        students = Student.objects.filter(
            group__isnull=True, 
            status='ACTIVE',
            specialty__department__faculty=faculty
        ).select_related('user', 'specialty')
        
        groups = Group.objects.filter(specialty__department__faculty=faculty).select_related('specialty').order_by('course', 'name')

    if request.method == 'POST':
        student_ids = request.POST.getlist('students')
        target_group_id = request.POST.get('target_group')
        
        if student_ids and target_group_id:
            target_group = get_object_or_404(Group, id=target_group_id)
            
            if not user.is_superuser:
                if not target_group.specialty or not target_group.specialty.department:
                    messages.error(request, _("Ошибка: группа не связана с факультетом."))
                    return redirect('accounts:unassigned_students')
                    
                if target_group.specialty.department.faculty != faculty:
                    messages.error(request, _("Ошибка доступа: попытка распределить в группу чужого факультета."))
                    return redirect('accounts:unassigned_students')
            
            updated_count = Student.objects.filter(id__in=student_ids).update(group=target_group)
            
            from journal.models import StudentStatistics
            StudentStatistics.recalculate_group(target_group)
            
            messages.success(
                request,
                _("Успешно распределено %(count)s студентов в группу %(group)s.") % {
                    'count': updated_count,
                    'group': target_group.name,
                }
            )
        else:
            messages.warning(request, _(" Выберите студентов и укажите группу для распределения."))
        
        return redirect('accounts:unassigned_students')

    return render(request, 'accounts/unassigned_students.html', {
        'students': students,
        'groups': groups,
        'faculty': faculty
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.role in ['HR', 'DEAN', 'VICE_DEAN', 'DIRECTOR', 'PRO_RECTOR'])
def download_generated_document(request, template_id, object_id):
    try:
        file_stream, filename = DocumentGenerator.generate_document(template_id, object_id)
        
        response = HttpResponse(
            file_stream.read(), 
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        logger.exception("download_generated_document")
        messages.error(request, _("Ошибка генерации документа. См. журнал сервера."))
        return redirect(request.META.get('HTTP_REFERER', 'core:dashboard'))

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role in ['HR', 'DEAN', 'VICE_DEAN'])
def document_templates_list(request):
    templates = DocumentTemplate.objects.all().order_by('context_type', '-created_at')
    
    if request.method == 'POST':
        form = DocumentTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, _("Шаблон успешно загружен!"))
            return redirect('accounts:document_templates')
    else:
        form = DocumentTemplateForm()
        
    return render(request, 'accounts/document_templates.html', {
        'templates': templates,
        'form': form
    })

@login_required
@user_passes_test(lambda u: u.is_superuser or u.role in ['HR', 'DEAN', 'VICE_DEAN'])
def delete_document_template(request, template_id):
    template = get_object_or_404(DocumentTemplate, id=template_id)
    template.delete()
    messages.success(request, _("Шаблон удален."))
    return redirect('accounts:document_templates')


@user_passes_test(is_management)
def archive_alumni(request):
    students = Student.objects.filter(status='GRADUATED').select_related('user', 'specialty', 'diploma')
    search = request.GET.get('search', '')
    if search:
        students = students.filter(user__last_name__icontains=search)
        
    return render(request, 'accounts/archives/alumni_list.html', {
        'students': students,
        'search': search
    })

@user_passes_test(is_management)
def archive_expelled(request):
    students = Student.objects.filter(status='EXPELLED').select_related('user', 'specialty')
    search = request.GET.get('search', '')
    if search:
        students = students.filter(user__last_name__icontains=search)
        
    return render(request, 'accounts/archives/expelled_list.html', {
        'students': students,
        'search': search
    })

@user_passes_test(is_management)
def download_contingent_report(request):
    faculty = None
    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty

    file_stream, filename = DocumentGenerator.generate_contingent_report(faculty=faculty)
    
    response = HttpResponse(
        file_stream.read(), 
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(is_management)
def mass_order_create(request: HttpRequest) -> HttpResponse:
    user: User = request.user
    
    faculty: Optional[Faculty] = None
    if hasattr(user, 'dean_profile') and user.dean_profile.faculty:
        faculty = user.dean_profile.faculty
    elif hasattr(user, 'vicedean_profile') and user.vicedean_profile.faculty:
        faculty = user.vicedean_profile.faculty

    groups_qs = Group.objects.select_related('specialty').all()
    if faculty and not user.is_superuser:
        groups_qs = groups_qs.filter(specialty__department__faculty=faculty)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        if request.method == 'POST' or request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                group_id = data.get('group_id', '')
            except json.JSONDecodeError:
                group_id = request.POST.get('group_id', '')
        else:
            group_id = request.GET.get('group_id', '')

        if group_id and str(group_id).isdigit():
            students = Student.objects.filter(group_id=int(group_id), status='ACTIVE').select_related('user', 'group')
            data =[
                {
                    'id': s.id,
                    'full_name': s.user.get_full_name(),
                    'student_id': s.student_id,
                    'group_name': s.group.name if s.group else ''
                } for s in students
            ]
            return JsonResponse({'students': data})
        return JsonResponse({'students': []})

    if request.method == 'POST':
        student_ids: List[str] = request.POST.getlist('students')
        order_type: str = request.POST.get('order_type', '')
        title: str = request.POST.get('title', '').strip()
        reason: str = request.POST.get('reason', '').strip()
        target_group_id: str = request.POST.get('target_group', '')
        file_obj = request.FILES.get('file')

        if not student_ids:
            messages.error(request, _("Необходимо добавить хотя бы одного студента в приказ."))
        elif not title or not order_type:
            messages.error(request, _("Заполните обязательные поля: Заголовок и Тип приказа."))
        else:
            try:
                with transaction.atomic():
                    new_order = Order.objects.create(
                        order_type=order_type,
                        title=title,
                        status='DRAFT', 
                        created_by=user,
                        file=file_obj
                    )

                    target_group: Optional[Group] = None
                    if order_type == 'TRANSFER' and target_group_id.isdigit():
                        target_group = Group.objects.get(id=int(target_group_id))
                    
                    order_items: List[OrderItem] = []
                    for s_id in set(student_ids):
                        if s_id.isdigit():
                            order_items.append(
                                OrderItem(
                                    order=new_order,
                                    student_id=int(s_id),
                                    reason=reason,
                                    target_group=target_group
                                )
                            )
                    
                    OrderItem.objects.bulk_create(order_items)

                messages.success(
                    request,
                    _("Проект приказа №%(number)s успешно сформирован на %(students)s студентов! Отправлен на подпись.") % {
                        'number': new_order.number,
                        'students': len(order_items),
                    }
                )
                return redirect('accounts:all_orders')
                
            except Exception as e:
                logger.exception("mass_order_create")
                messages.error(request, _("Ошибка при создании приказа. См. журнал сервера."))

    context = {
        'groups': groups_qs,
        'order_types': Order.ORDER_TYPES,
    }
    return render(request, 'accounts/mass_order_create.html', context)
@login_required
@user_passes_test(is_management)
def add_specialization(request):
    initial = {}
    specialty_id = request.GET.get('specialty')
    if specialty_id:
        initial['specialty'] = get_object_or_404(Specialty, id=specialty_id)

    faculty = request.user.dean_profile.faculty if hasattr(request.user, 'dean_profile') else None
    if request.method == 'POST':
        form = SpecializationForm(request.POST, faculty=faculty)
        if form.is_valid():
            form.save()
            messages.success(request, _("Специализация (профиль) успешно добавлена!"))
            return redirect('accounts:manage_structure')
    else:
        form = SpecializationForm(initial=initial, faculty=faculty)
    return render(request, 'core/form_generic.html', {'form': form, 'title': _('Добавить специализацию (Тахассус)')})

@login_required
@user_passes_test(is_management)
def edit_specialization(request, pk):
    spec = get_object_or_404(Specialization, pk=pk)
    faculty = request.user.dean_profile.faculty if hasattr(request.user, 'dean_profile') else None

    if request.method == 'POST':
        form = SpecializationForm(request.POST, instance=spec, faculty=faculty)
        if form.is_valid():
            form.save()
            messages.success(request, _("Специализация обновлена!"))
            return redirect('accounts:manage_structure')
    else:
        form = SpecializationForm(instance=spec, faculty=faculty)

    return render(request, 'core/form_generic.html', {'form': form, 'title': _('Редактировать специализацию')})

@login_required
@user_passes_test(is_management)
def delete_specialization(request, pk):
    spec = get_object_or_404(Specialization, pk=pk)
    if request.method == 'POST':
        spec.delete()
        messages.success(request, _("Специализация удалена!"))
        return redirect('accounts:manage_structure')
    return render(request, 'core/confirm_delete.html', {'obj': spec, 'title': _('Удалить специализацию')})


@login_required
def view_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    
    if not (request.user.is_superuser or request.user.is_management):
        messages.error(request, _("Доступ запрещен"))
        return redirect('core:dashboard')
    
    if hasattr(request.user, 'dean_profile'):
        faculty = request.user.dean_profile.faculty
        if group.specialty and group.specialty.department.faculty != faculty:
            messages.error(request, _("Нет доступа к этой группе"))
            return redirect('accounts:group_management')

    students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')

    return render(request, 'accounts/view_group.html', {
        'group': group,
        'students': students
    })




@login_required
@user_passes_test(is_management)
def select2_user_search(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    user = request.user
    students_qs = Student.objects.select_related('user')
    teachers_qs = Teacher.objects.select_related('user', 'department')

    if user.is_superuser:
        pass
    elif hasattr(user, 'dean_profile') and getattr(user.dean_profile, 'faculty', None):
        faculty = user.dean_profile.faculty
        students_qs = students_qs.filter(group__specialty__department__faculty=faculty)
        teachers_qs = teachers_qs.filter(department__faculty=faculty)
    elif hasattr(user, 'vicedean_profile') and getattr(user.vicedean_profile, 'faculty', None):
        faculty = user.vicedean_profile.faculty
        students_qs = students_qs.filter(group__specialty__department__faculty=faculty)
        teachers_qs = teachers_qs.filter(department__faculty=faculty)
    elif hasattr(user, 'head_of_dept_profile') and getattr(user.head_of_dept_profile, 'department', None):
        dept = user.head_of_dept_profile.department
        students_qs = students_qs.filter(group__specialty__department=dept)
        teachers_qs = teachers_qs.filter(department=dept)
    elif hasattr(user, 'director_profile') and getattr(user.director_profile, 'institute', None):
        institute = user.director_profile.institute
        students_qs = students_qs.filter(group__specialty__department__faculty__institute=institute)
        teachers_qs = teachers_qs.filter(department__faculty__institute=institute)
    elif hasattr(user, 'prorector_profile') and getattr(user.prorector_profile, 'institute', None):
        institute = user.prorector_profile.institute
        students_qs = students_qs.filter(group__specialty__department__faculty__institute=institute)
        teachers_qs = teachers_qs.filter(department__faculty__institute=institute)
    else:
        return JsonResponse({'results': []})

    students = students_qs.filter(
        Q(user__last_name__icontains=q) |
        Q(user__first_name__icontains=q) |
        Q(student_id__icontains=q)
    )[:15]

    teachers = teachers_qs.filter(
        Q(user__last_name__icontains=q) |
        Q(user__first_name__icontains=q)
    )[:15]

    results = []
    for s in students:
        text = s.user.get_full_name()
        if user.is_superuser:
            text = f"[ID: {s.user.id}] {text}"
        results.append({
            'id': s.user.id,
            'text': text,
            'type': 'student',
            'type_display': 'Студент',
            'meta': s.student_id,
        })
    for t in teachers:
        text = t.user.get_full_name()
        if user.is_superuser:
            text = f"[ID: {t.user.id}] {text}"
        results.append({
            'id': t.user.id,
            'text': text,
            'type': 'teacher',
            'type_display': 'Преподаватель',
            'meta': t.department.name if t.department else '',
        })
    results = []
    for g in groups:
        text = f"{g.name} ({g.course} курс)"
        if user.is_superuser:
            text = f"[ID: {g.id}] {text}"
        results.append({
            'id': g.id,
            'text': text
        })

    return JsonResponse({'results': results})

@login_required
@user_passes_test(is_management)
def select2_group_search(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    user = request.user
    groups_qs = Group.objects.select_related('specialty')

    if user.is_superuser:
        pass
    elif hasattr(user, 'dean_profile') and getattr(user.dean_profile, 'faculty', None):
        faculty = user.dean_profile.faculty
        groups_qs = groups_qs.filter(specialty__department__faculty=faculty)
    elif hasattr(user, 'vicedean_profile') and getattr(user.vicedean_profile, 'faculty', None):
        faculty = user.vicedean_profile.faculty
        groups_qs = groups_qs.filter(specialty__department__faculty=faculty)
    elif hasattr(user, 'head_of_dept_profile') and getattr(user.head_of_dept_profile, 'department', None):
        dept = user.head_of_dept_profile.department
        groups_qs = groups_qs.filter(specialty__department=dept)
    elif hasattr(user, 'director_profile') and getattr(user.director_profile, 'institute', None):
        institute = user.director_profile.institute
        groups_qs = groups_qs.filter(specialty__department__faculty__institute=institute)
    elif hasattr(user, 'prorector_profile') and getattr(user.prorector_profile, 'institute', None):
        institute = user.prorector_profile.institute
        groups_qs = groups_qs.filter(specialty__department__faculty__institute=institute)
    else:
        return JsonResponse({'results': []})

    groups = groups_qs.filter(name__icontains=q)[:15]

    results = []
    for g in groups:
        text = f"{g.name} ({g.course} курс)"
        if user.is_superuser:
            text = f"[ID: {g.id}] {text}"
        results.append({
            'id': g.id,
            'text': text
        })

    return JsonResponse({'results': results})





def _check_structure_edit_permission(user, faculty=None) -> bool:
    if user.is_superuser or user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        return True
    if faculty and hasattr(user, 'dean_profile'):
        return user.dean_profile.faculty == faculty
    return False

@login_required
def api_faculty_detail(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)

    if not _check_structure_edit_permission(request.user, faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

    return JsonResponse({
        'success': True,
        'data': {
            'id':         faculty.pk,
            'name':       faculty.name,
            'short_name': faculty.short_name,
            'code':       faculty.code,
            'institute':  faculty.institute_id,
        },
    })

@login_required
@require_POST
def api_faculty_update(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)

    if not _check_structure_edit_permission(request.user, faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

    from .forms import FacultyForm as _FacultyForm
    form = _FacultyForm(request.POST, instance=faculty)
    if form.is_valid():
        form.save()
        return JsonResponse({
            'success': True,
            'message': _('Факультет «%(name)s» успешно обновлён') % {'name': faculty.name},
        })

    return JsonResponse({
        'success': False,
        'errors': form.errors.as_json(),
    }, status=422)

@login_required
def api_department_detail(request, pk):
    dept = get_object_or_404(Department, pk=pk)

    if not _check_structure_edit_permission(request.user, dept.faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

    head = getattr(dept, 'head', None)
    return JsonResponse({
        'success': True,
        'data': {
            'id':                 dept.pk,
            'name':               dept.name,
            'faculty':            dept.faculty_id,
            'total_wage_rate':    dept.total_wage_rate,
            'total_hours_budget': dept.total_hours_budget,
            'head_user_id':       head.user_id if head else None,
            'head_user_name':     head.user.get_full_name() if head else '',
        },
    })


@login_required
@require_POST
def api_department_update(request, pk):
    dept = get_object_or_404(Department, pk=pk)

    if not _check_structure_edit_permission(request.user, dept.faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

    from .forms import DepartmentForm as _DeptForm
    form = _DeptForm(request.POST, instance=dept, faculty_context=dept.faculty)
    if form.is_valid():
        with transaction.atomic():
            dept = form.save()
            head_user = form.cleaned_data.get('head_of_department')
            if head_user:
                if head_user.role == 'TEACHER':
                    head_user.role = 'HEAD_OF_DEPT'
                    head_user.save()
                HeadOfDepartment.objects.update_or_create(
                    user=head_user, defaults={'department': dept}
                )
        return JsonResponse({
            'success': True,
            'message': _('Кафедра «%(name)s» обновлена') % {'name': dept.name},
        })

    return JsonResponse({
        'success': False,
        'errors': form.errors.as_json(),
    }, status=422)



@login_required
def api_specialty_detail(request, pk):
    spec = get_object_or_404(Specialty, pk=pk)

    if not _check_structure_edit_permission(request.user, spec.department.faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

    return JsonResponse({
        'success': True,
        'data': {
            'id':              spec.pk,
            'name':            spec.name,
            'name_tj':         spec.name_tj,
            'name_ru':         spec.name_ru,
            'name_en':         spec.name_en,
            'education_level': spec.education_level,
            'code':            spec.code,
            'qualification':   spec.qualification,
            'department':      spec.department_id,
        },
    })


@login_required
@require_POST
def api_specialty_update(request, pk):
    spec = get_object_or_404(Specialty, pk=pk)

    if not _check_structure_edit_permission(request.user, spec.department.faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)

    from .forms import SpecialtyForm as _SpecForm
    form = _SpecForm(request.POST, instance=spec)
    if hasattr(request.user, 'dean_profile'):
        form.fields['department'].queryset = Department.objects.filter(
            faculty=request.user.dean_profile.faculty
        )

    if form.is_valid():
        form.save()
        return JsonResponse({
            'success': True,
            'message': _('Специальность «%(code)s» обновлена') % {'code': spec.code},
        })

    return JsonResponse({
        'success': False,
        'errors': form.errors.as_json(),
    }, status=422)



@login_required
@user_passes_test(
    lambda u: u.is_superuser
    or hasattr(u, 'dean_profile')
    or u.role in ['PRO_RECTOR', 'DIRECTOR']
)
def admission_plan_list(request):
    """
    Admission plan list with enrollment counts.
 
    KEY FIX: instead of calling plan.get_enrolled_count() inside a Python
    loop (100 plans → 101 DB queries), we fire ONE aggregated query that
    groups active students by (specialty, education_type, education_language,
    financing_type) and build a Python dict.  Each plan's count is then an
    O(1) dict lookup — the whole page costs exactly 2 SQL queries regardless
    of how many plans exist.
    """
    user = request.user
    plans = (
        AdmissionPlan.objects
        .select_related('specialty__department__faculty__institute')
        .order_by('-academic_year', 'specialty__code')
    )
 
    if hasattr(user, 'dean_profile') and not user.is_superuser:
        plans = plans.filter(
            specialty__department__faculty=user.dean_profile.faculty
        )
 
    year_filter = request.GET.get('year', '')
    if year_filter:
        plans = plans.filter(academic_year=year_filter)
 
    specialty_id = request.GET.get('specialty', '')
    if specialty_id and specialty_id.isdigit():
        plans = plans.filter(specialty_id=int(specialty_id))
 
    
    
    
    enrolled_rows = (
        Student.objects
        .filter(status='ACTIVE')
        .values('specialty_id', 'education_type', 'education_language', 'financing_type')
        .annotate(cnt=Count('id'))
    )
 
    
    enrolled_lookup: dict = {}
    for row in enrolled_rows:
        key = (
            row['specialty_id'],
            row['education_type'],
            row['education_language'],
            row['financing_type'],
        )
        enrolled_lookup[key] = row['cnt']
 
    
    plans_with_stats = []
    for plan in plans:
        edu_type = AdmissionPlan._STUDY_FORM_MAP.get(plan.study_form, 'FULL_TIME')
        fin_type = AdmissionPlan._FINANCING_MAP.get(plan.financing_type, 'BUDGET')
        key = (plan.specialty_id, edu_type, plan.education_language, fin_type)
        enrolled = enrolled_lookup.get(key, 0)
        pct = round(enrolled / plan.target_quota * 100, 1) if plan.target_quota else 0.0
        plans_with_stats.append({
            'plan': plan,
            'enrolled': enrolled,
            'fulfillment_pct': pct,
            'is_fulfilled': enrolled >= plan.target_quota,
        })
 
    available_years = (
        AdmissionPlan.objects
        .values_list('academic_year', flat=True)
        .distinct()
        .order_by('-academic_year')
    )
 
    context = {
        'plans_with_stats': plans_with_stats,
        'available_years': available_years,
        'year_filter': year_filter,
        'specialty_filter': specialty_id,
    }
    return render(request, 'accounts/admission_plans/list.html', context)




@login_required
@user_passes_test(lambda u: u.is_superuser or hasattr(u, 'dean_profile') or u.role in ['PRO_RECTOR', 'DIRECTOR'])
def admission_plan_create(request):
    faculty = None
    if hasattr(request.user, 'dean_profile') and not request.user.is_superuser:
        faculty = request.user.dean_profile.faculty

    if request.method == 'POST':
        form = AdmissionPlanForm(request.POST, faculty=faculty)
        if form.is_valid():
            plan = form.save()
            messages.success(
                request,
                _('План приёма для %(code)s на %(year)s создан') % {
                    'code': plan.specialty.code,
                    'year': plan.academic_year,
                }
            )
            return redirect('accounts:admission_plan_list')
    else:
        form = AdmissionPlanForm(faculty=faculty)

    return render(request, 'accounts/admission_plans/form.html', {
        'form': form,
        'title': _('Создать план приёма'),
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or hasattr(u, 'dean_profile') or u.role in ['PRO_RECTOR', 'DIRECTOR'])
def admission_plan_edit(request, pk):
    plan = get_object_or_404(AdmissionPlan, pk=pk)

    if hasattr(request.user, 'dean_profile') and not request.user.is_superuser:
        faculty = request.user.dean_profile.faculty
        if plan.specialty.department.faculty != faculty:
            messages.error(request, _('Нет доступа'))
            return redirect('accounts:admission_plan_list')
    else:
        faculty = None

    if request.method == 'POST':
        form = AdmissionPlanForm(request.POST, instance=plan, faculty=faculty)
        if form.is_valid():
            form.save()
            messages.success(request, _('План приёма обновлён'))
            return redirect('accounts:admission_plan_list')
    else:
        form = AdmissionPlanForm(instance=plan, faculty=faculty)

    return render(request, 'accounts/admission_plans/form.html', {
        'form': form,
        'plan': plan,
        'title': _('Редактировать план приёма'),
        'enrolled': plan.get_enrolled_count(),
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.role in ['PRO_RECTOR', 'DIRECTOR'])
def admission_plan_delete(request, pk):
    plan = get_object_or_404(AdmissionPlan, pk=pk)
    if request.method == 'POST':
        plan.delete()
        messages.success(request, _('План приёма удалён'))
        return redirect('accounts:admission_plan_list')
    return render(request, 'core/confirm_delete.html', {
        'obj': plan,
        'title': _('Удалить план приёма'),
    })




@login_required
def api_faculty_load_summary(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if not _check_structure_edit_permission(request.user, faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)
    
    departments = faculty.departments.prefetch_related('subjects', 'teachers').all()
    data = []
    
    for dept in departments:
        subjects = dept.subjects.filter(is_active=True)
        
        tot_lec = sum(s.lecture_hours for s in subjects)
        tot_prac = sum(s.practice_hours + s.lab_hours for s in subjects)
        tot_kmro = sum(s.control_hours for s in subjects)
        tot_all = tot_lec + tot_prac + tot_kmro
        
        assigned_subs = subjects.filter(teacher__isnull=False)
        ass_lec = sum(s.lecture_hours for s in assigned_subs)
        ass_prac = sum(s.practice_hours + s.lab_hours for s in assigned_subs)
        ass_kmro = sum(s.control_hours for s in assigned_subs)
        ass_all = ass_lec + ass_prac + ass_kmro
        
        rem_lec = tot_lec - ass_lec
        rem_prac = tot_prac - ass_prac
        rem_kmro = tot_kmro - ass_kmro
        rem_all = tot_all - ass_all
        
        data.append({
            'id': dept.id,
            'name': dept.name,
            'wage_rate': dept.total_wage_rate or 0,
            'hours_budget': dept.total_hours_budget or 0,
            
            'tot_all': tot_all, 'tot_lec': tot_lec, 'tot_prac': tot_prac, 'tot_kmro': tot_kmro,
            'ass_all': ass_all, 'ass_lec': ass_lec, 'ass_prac': ass_prac, 'ass_kmro': ass_kmro,
            'rem_all': rem_all, 'rem_lec': rem_lec, 'rem_prac': rem_prac, 'rem_kmro': rem_kmro,
        })
        
    return JsonResponse({'success': True, 'departments': data})


@login_required
@require_POST
def api_department_quick_update(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if not _check_structure_edit_permission(request.user, dept.faculty):
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)
        
    field = request.POST.get('field')
    value = request.POST.get('value')
    
    try:
        if field == 'wage':
            dept.total_wage_rate = float(value.replace(',', '.')) if value else 0.0
        elif field == 'hours':
            dept.total_hours_budget = int(float(value.replace(',', '.'))) if value else 0
        dept.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@login_required
@require_POST
def api_quick_update(request):
    if not request.user.is_management:
        return JsonResponse({'success': False, 'error': _('Нет прав')}, status=403)
        
    model_name = request.POST.get('model')
    obj_id = request.POST.get('id')
    field = request.POST.get('field')
    value = request.POST.get('value', '').strip()
    
    try:
        if model_name == 'faculty':
            obj = Faculty.objects.get(id=obj_id)
            setattr(obj, field, value)
            obj.save()
            
        elif model_name == 'department':
            obj = Department.objects.get(id=obj_id)
            if field == 'total_wage_rate':
                value = float(value.replace(',', '.')) if value else 0.0
            elif field == 'total_hours_budget':
                value = int(float(value.replace(',', '.'))) if value else 0
            setattr(obj, field, value)
            obj.save()
            
        elif model_name == 'specialty':
            obj = Specialty.objects.get(id=obj_id)
            setattr(obj, field, value)
            if field in ['name_ru', 'name_tj', 'name_en']:
                obj.name = value  
            obj.save()
            
        else:
            return JsonResponse({'success': False, 'error': _('Неизвестная модель')})
            
        return JsonResponse({'success': True, 'value': value})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("api_quick_update error")
        return JsonResponse({'success': False, 'error': str(e)})