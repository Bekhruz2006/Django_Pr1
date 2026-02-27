from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db import models
from django.http import HttpResponseForbidden, HttpRequest, JsonResponse
from django.utils.translation import gettext as _
from .services import StudentImportService
from schedule.models import Semester, Subject, AcademicPlan
from django.db.models import Prefetch
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
    UserEditForm, CustomPasswordChangeForm, PasswordResetByDeanForm,
    GroupForm, GroupTransferForm, DepartmentCreateForm, SpecialtyCreateForm,
    InstituteForm, FacultyForm, DepartmentForm, SpecialtyForm, HeadOfDepartmentForm,
    OrderForm, DocumentTemplateForm, SpecializationForm
)

from django.core.exceptions import ObjectDoesNotExist
from .forms import InstituteManagementForm, InstituteForm, FacultyFullForm
from django.http import HttpResponse
from typing import List, Optional
from django.core.exceptions import ValidationError

def is_hr_or_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == 'HR')

def is_dean_or_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role in ['DEAN', 'VICE_DEAN'])


def generate_student_id():
    from datetime import datetime
    year = datetime.now().year
    base_id = f"{year}S"
    last_student = Student.objects.filter(
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
    return user.is_authenticated and user.role == 'DEAN'

def is_admin_or_rector(user):
    return user.is_authenticated and (user.is_superuser or user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR'])

def is_management(user):
    return user.is_authenticated and (user.is_superuser or user.role in ['DEAN', 'VICE_DEAN', 'RECTOR', 'PRO_RECTOR', 'DIRECTOR'])

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
def logout_view(request):
    logout(request)
    messages.success(request, _('Вы успешно вышли из системы'))
    return redirect('accounts:login')

@login_required
def profile_view(request):
    user = request.user
    profile = None
    context = {'profile': profile}
    
    if user.role == 'STUDENT':
        profile = get_object_or_404(Student, user=user)
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
        
    elif user.role == 'TEACHER':
        profile = get_object_or_404(Teacher, user=user)
        from schedule.models import ScheduleSlot
        from journal.models import StudentStatistics
        
        group_ids = ScheduleSlot.objects.filter(
            teacher=profile, is_active=True
        ).values_list('group_id', flat=True).distinct()
        
        groups = Group.objects.filter(id__in=group_ids)
        
        teacher_groups = []
        for group in groups:
            students = Student.objects.filter(group=group)
            students_count = students.count()
            
            if students_count > 0:
                stats_list = []
                for student in students:
                    stats, created = StudentStatistics.objects.get_or_create(student=student)
                    stats_list.append(stats)
                
                avg_gpa = sum(s.overall_gpa for s in stats_list) / len(stats_list) if stats_list else 0
                avg_attendance = sum(s.attendance_percentage for s in stats_list) / len(stats_list) if stats_list else 0
                
                teacher_groups.append({
                    'group': group,
                    'students_count': students_count,
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
        
    elif user.role == 'DEAN':
        profile = get_object_or_404(Dean, user=user)
        context['profile'] = profile
        
    elif user.role == 'HEAD_OF_DEPT':
        profile = get_object_or_404(HeadOfDepartment, user=user)
        context['profile'] = profile
        
    elif user.role in ['DIRECTOR', 'PRO_RECTOR']:
        if user.role == 'DIRECTOR':
            profile = get_object_or_404(Director, user=user)
        else:
            profile = get_object_or_404(ProRector, user=user)
        context['profile'] = profile
    
    template_name = f'accounts/profile_{user.role.lower()}.html' if user.role in ['STUDENT', 'TEACHER', 'DEAN'] else 'accounts/profile_teacher.html'
    return render(request, template_name, context)

@login_required
def edit_profile(request):
    user = request.user
    
    if request.method == 'POST':
        user_form = UserEditForm(request.POST, request.FILES, instance=user)
        
        profile_form = None
        if user.role == 'STUDENT':
            profile_form = StudentForm(request.POST, instance=user.student_profile)
        elif user.role == 'TEACHER':
            profile_form = TeacherForm(request.POST, instance=user.teacher_profile)
        elif user.role == 'DEAN':
            profile_form = DeanForm(request.POST, instance=user.dean_profile)
        elif user.role == 'HEAD_OF_DEPT':
            profile_form = HeadOfDepartmentForm(request.POST, instance=user.head_of_dept_profile)
        
        if user_form.is_valid() and (profile_form is None or profile_form.is_valid()):
            user_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, _('Профиль успешно обновлен'))
            return redirect('accounts:profile')
    else:
        user_form = UserEditForm(instance=user)
        
        profile_form = None
        if user.role == 'STUDENT':
            profile_form = StudentForm(instance=user.student_profile)
        elif user.role == 'TEACHER':
            profile_form = TeacherForm(instance=user.teacher_profile)
        elif user.role == 'DEAN':
            profile_form = DeanForm(instance=user.dean_profile)
        elif user.role == 'HEAD_OF_DEPT':
            profile_form = HeadOfDepartmentForm(instance=user.head_of_dept_profile)
    
    return render(request, 'accounts/edit_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form
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

    users = users.select_related('student_profile', 'teacher_profile', 'dean_profile')

    users_with_profiles = []
    for user_obj in users:
        user_data = {
            'user': user_obj,
            'has_profile': True,
            'profile_id': None
        }

        try:
            if user_obj.role == 'STUDENT':
                if hasattr(user_obj, 'student_profile'):
                    user_data['profile_id'] = user_obj.student_profile.id
                else:
                    user_data['has_profile'] = False
            elif user_obj.role == 'TEACHER':
                if hasattr(user_obj, 'teacher_profile'):
                    user_data['profile_id'] = user_obj.teacher_profile.id
                else:
                    user_data['has_profile'] = False
            elif user_obj.role == 'DEAN':
                if hasattr(user_obj, 'dean_profile'):
                    user_data['profile_id'] = user_obj.dean_profile.id
                else:
                    user_data['has_profile'] = False
        except ObjectDoesNotExist:
            user_data['has_profile'] = False

        users_with_profiles.append(user_data)

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
            messages.success(request, _(f"Импортировано: {results['created']} студентов."))
            if results['errors']:
                messages.warning(request, _(f"Ошибки ({len(results['errors'])}): {'; '.join(results['errors'][:3])}..."))
        except Exception as e:
            messages.error(request, _(f"Критическая ошибка импорта: {str(e)}"))
            
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
                        student.student_id = generate_student_id()
                        student.course = 1
                        student.admission_year = 2025
                        student.save()
                        
                    elif role == 'TEACHER':
                        teacher = user.teacher_profile
                        if department_id:
                            dept = Department.objects.get(id=department_id)
                            if request.user.role == 'DEAN' and dept.faculty != request.user.dean_profile.faculty:
                                pass 
                            else:
                                teacher.department = dept
                                teacher.save()
                                
                    
                    messages.success(request, _(f'Пользователь {user.username} ({user.get_role_display()}) успешно создан.'))
                    
                    if department_id:
                        return redirect('accounts:manage_structure')
                        
                    return redirect('accounts:user_management')
                    
                except Exception as e:
                    messages.error(request, _(f'Ошибка при настройке профиля: {str(e)}'))
                    print(e)
    else:
        user_form = UserCreateForm(creator=request.user, initial=initial_data)
    
    return render(request, 'accounts/add_user.html', {'form': user_form})

@user_passes_test(is_management)
def edit_user(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
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
        user_form = UserEditForm(request.POST, request.FILES, instance=user_obj)
        
        profile_form = None
        if user_obj.role == 'STUDENT':
            profile_form = StudentForm(request.POST, instance=user_obj.student_profile)
        elif user_obj.role == 'TEACHER':
            profile_form = TeacherForm(request.POST, instance=user_obj.teacher_profile)
        elif user_obj.role == 'DEAN':
            profile_form = DeanForm(request.POST, instance=user_obj.dean_profile)
        elif user_obj.role == 'HEAD_OF_DEPT':
            profile_form = HeadOfDepartmentForm(request.POST, instance=user_obj.head_of_dept_profile)
        
        if user_form.is_valid() and (profile_form is None or profile_form.is_valid()):
            user_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, _('Пользователь успешно обновлен'))
            return redirect('accounts:user_management')
    else:
        user_form = UserEditForm(instance=user_obj)
        
        profile_form = None
        if user_obj.role == 'STUDENT':
            profile_form = StudentForm(instance=user_obj.student_profile)
        elif user_obj.role == 'TEACHER':
            profile_form = TeacherForm(instance=user_obj.teacher_profile)
        elif user_obj.role == 'DEAN':
            profile_form = DeanForm(instance=user_obj.dean_profile)
        elif user_obj.role == 'HEAD_OF_DEPT':
            profile_form = HeadOfDepartmentForm(instance=user_obj.head_of_dept_profile)
    
    return render(request, 'accounts/edit_user.html', {
        'user_form': user_form,
        'profile_form': profile_form,
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
            messages.success(request, _(f'Пароль для {user_obj.username} успешно сброшен'))
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
    messages.success(request, _(f'Пользователь {user_obj.username} {status}'))
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
                
                GroupTransferHistory.objects.create(
                    student=student,
                    from_group=old_group,
                    to_group=new_group,
                    reason=form.cleaned_data['reason'],
                    transferred_by=request.user
                )
                student.group = new_group
                student.save()
                
                messages.success(request, _(f'Студент переведен из {old_group} в {new_group}'))
                return redirect('accounts:user_management')
    else:
        form = GroupTransferForm()
    
    return render(request, 'accounts/transfer_student.html', {
        'form': form,
        'student': student
    })

@login_required
def view_user_profile(request, user_id):
    if not is_management(request.user) and request.user.role != 'TEACHER':
         messages.error(request, _('Доступ запрещен'))
         return redirect('core:dashboard')

    user_obj = get_object_or_404(User, id=user_id)
    profile = None
    template = 'accounts/profile_student.html'
    context = {
        'user': user_obj,
        'viewing_as_dean': True
    }

    if user_obj.role == 'STUDENT':
        profile = get_object_or_404(Student, user=user_obj)
        from journal.models import StudentStatistics
        stats, created = StudentStatistics.objects.get_or_create(student=profile)
        stats.recalculate()
        profile.statistics = stats
        context['profile'] = profile
        context['templates_cert'] = DocumentTemplate.objects.filter(context_type='STUDENT_CERT', is_active=True)
        template = 'accounts/profile_student.html'

    elif user_obj.role == 'TEACHER':
        profile = get_object_or_404(Teacher, user=user_obj)
        context['profile'] = profile
        template = 'accounts/profile_teacher.html'

    elif user_obj.role == 'DEAN':
        profile = get_object_or_404(Dean, user=user_obj)
        context['profile'] = profile
        template = 'accounts/profile_dean.html'

    return render(request, template, context)

@user_passes_test(is_management)
def group_management(request):
    groups = Group.objects.all().order_by('course', 'name')
    search = request.GET.get('search', '')
    course_filter = request.GET.get('course', '')
    
    if search:
        groups = groups.filter(
            models.Q(name__icontains=search) |
            models.Q(specialty__icontains=search)
        )
    
    if course_filter:
        groups = groups.filter(course=course_filter)
    
    return render(request, 'accounts/group_management.html', {
        'groups': groups,
        'search': search,
        'course_filter': course_filter,
    })

@login_required
def add_group(request):
    if not (request.user.is_superuser or request.user.role in ['DEAN', 'VICE_DEAN']):
        messages.error(request, _("Нет доступа"))
        return redirect('core:dashboard')

    specialty_id = request.GET.get('specialty')
    
    initial_data = {}
    if specialty_id:
        try:
            specialty = Specialty.objects.get(id=specialty_id)
            if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
                if specialty.department.faculty != request.user.dean_profile.faculty:
                    messages.error(request, _("Это специальность чужого факультета"))
                    return redirect('accounts:manage_structure')
            initial_data['specialty'] = specialty
        except Specialty.DoesNotExist:
            pass

    def configure_form(form):
        if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
            faculty = request.user.dean_profile.faculty
            if faculty:
                form.fields['specialty'].queryset = Specialty.objects.filter(department__faculty=faculty)

    if request.method == 'POST':
        form = GroupForm(request.POST, initial=initial_data) 
        configure_form(form) 

        if form.is_valid():
            try:
                if is_dean(request.user):
                    spec = form.cleaned_data['specialty']
                    if spec.department.faculty != request.user.dean_profile.faculty:
                        raise Exception(_("Попытка создания группы на чужом факультете"))

                group = form.save()
                messages.success(request, _(f'Группа {group.name} успешно создана'))
                messages.success(request, _(f'Группа {group.name} успешно создана! Учебный план (РУП) для неё сгенерирован автоматически.'))

                if specialty_id:
                    return redirect('accounts:manage_structure')
                return redirect('accounts:group_management')
            except Exception as e:
                messages.error(request, _(f"Ошибка сохранения: {str(e)}"))
        else:
            messages.error(request, _("Пожалуйста, исправьте ошибки в форме."))
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
            messages.success(request, _(f'Группа {group.name} успешно обновлена'))
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
            messages.error(request, _(f'Невозможно удалить группу {group.name}. В ней есть {students_count} студентов.'))
        else:
            group.delete()
            messages.success(request, _(f'Группа {group.name} успешно удалена'))
        return redirect('accounts:group_management')
    return render(request, 'accounts/delete_group.html', {'group': group, 'students_count': students_count})


@login_required
def manage_structure(request):
    if not is_management(request.user):
        return redirect('core:dashboard')
        
    context = {}
    active_semester = Semester.objects.filter(is_active=True).first()
    
    if request.user.is_superuser or request.user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        institutes = Institute.objects.prefetch_related(
            'directors__user',
            'faculties__dean_manager__user',
            'faculties__departments__head__user',
            'faculties__departments__specialties',
            'faculties__departments__specialties__groups' 
        ).all()
        
        structure_data = []
        for inst in institutes:
            inst_data = {
                'obj': inst,
                'director': inst.directors.first(),
                'faculties': []
            }
            
            for fac in inst.faculties.all():
                fac_data = {
                    'obj': fac,
                    'dean': getattr(fac, 'dean_manager', None),
                    'departments': []
                }
                
                for dept in fac.departments.all():
                    dept_data = {
                        'obj': dept,
                        'head': getattr(dept, 'head', None),
                        'specialties': dept.specialties.all(),
                        'stats': {
                            'teachers': dept.teachers.count(),
                            'groups': Group.objects.filter(specialty__department=dept).count(),
                            'students': Student.objects.filter(group__specialty__department=dept).count()
                        }
                    }
                    fac_data['departments'].append(dept_data)
                
                inst_data['faculties'].append(fac_data)
            
            structure_data.append(inst_data)

        context['structure_data'] = structure_data
        context['is_admin'] = True
        
    elif request.user.role in ['DEAN', 'VICE_DEAN']:
        user_faculty = None
        if hasattr(request.user, 'dean_profile'):
            user_faculty = request.user.dean_profile.faculty
        elif hasattr(request.user, 'vicedean_profile'):
            user_faculty = request.user.vicedean_profile.faculty
            
        if user_faculty:
            departments = Department.objects.filter(faculty=user_faculty).prefetch_related(
                'specialties__groups',
                'specialties__academicplan_set',
                'head__user'
            )
            
            dept_data = []
            for dept in departments:
                current_subjects = Subject.objects.filter(department=dept)
                if active_semester:
                    current_subjects = current_subjects.filter(
                        groups__assigned_semesters=active_semester
                    ).distinct()

                total_hours = sum(s.total_auditory_hours for s in current_subjects)
                budget = dept.total_hours_budget or 1 
                load_percent = round((total_hours / budget) * 100, 1) if dept.total_hours_budget else 0
                
                specs_data = []
                for spec in dept.specialties.all():
                    last_plan = spec.academicplan_set.filter(is_active=True).order_by('-admission_year').first()
                    specs_data.append({
                        'obj': spec,
                        'groups': spec.groups.all(),
                        'plan': last_plan
                    })

                dept_data.append({
                    'obj': dept,
                    'total_hours': total_hours,
                    'load_percent': load_percent,
                    'subjects_count': current_subjects.count(),
                    'teachers_count': dept.teachers.count(),
                    'specialties_data': specs_data
                })

            context['faculty'] = user_faculty
            context['dept_data'] = dept_data
            context['is_dean'] = True
            context['active_semester'] = active_semester
        else:
            messages.error(request, _("Ваш профиль не привязан к факультету"))
            return redirect('core:dashboard')
            
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
    return render(request, 'accounts/confirm_delete.html', {'obj': institute, 'title': 'Удалить Институт'})

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

            messages.success(request, _(f"Факультет {faculty.name} успешно создан!"))
            return redirect('accounts:manage_structure')
    else:
        form = FacultyFullForm(initial=initial_data)
    
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Добавить Факультет (Расширенный)'})

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
    return render(request, 'accounts/confirm_delete.html', {'obj': faculty, 'title': 'Удалить Факультет'})

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

            messages.success(request, _(f"Кафедра {dept.name} создана"))
            return redirect('accounts:manage_structure')
    else:
        form = DepartmentForm(initial=initial, faculty_context=faculty_context)
        if is_dean(request.user) and hasattr(request.user, 'dean_profile') and request.user.dean_profile.faculty:
            faculty = request.user.dean_profile.faculty
            form.fields['faculty'].queryset = Faculty.objects.filter(id=faculty.id)

    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Добавить кафедру'})

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

    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Редактировать кафедру'})



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
    return render(request, 'accounts/confirm_delete.html', {'obj': dept, 'title': 'Удалить кафедру'})

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
        
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Добавить специальность'})

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

    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Редактировать специальность'})

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
    return render(request, 'accounts/confirm_delete.html', {'obj': spec, 'title': 'Удалить специальность'})


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
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Добавить Институт'})


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
            OrderItem.objects.create(order=order, student=student)
            messages.success(request, _(f'Проект приказа №{order.number} создан.'))
            return redirect('accounts:user_management')
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
        students = students.filter(group_id=group_id)
        
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
        'show_debtors': show_debtors
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





@user_passes_test(lambda u: u.is_superuser or u.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR'])
def approve_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        if order.status == 'DRAFT':
            order.apply_effect(request.user)
            messages.success(request, _(f"Приказ №{order.number} утвержден! Статус студентов обновлен."))
        else:
            messages.warning(request, _("Приказ уже обработан."))
            
    return redirect('accounts:all_orders')




@user_passes_test(is_dean_or_admin)
def unassigned_students(request):
    faculty = request.user.dean_profile.faculty
    students = Student.objects.filter(
        group__isnull=True, 
        status='ACTIVE'
    )
    
    groups = Group.objects.filter(specialty__department__faculty=faculty)
    
    if request.method == 'POST':
        student_ids = request.POST.getlist('students')
        target_group_id = request.POST.get('target_group')
        if student_ids and target_group_id:
            Student.objects.filter(id__in=student_ids).update(group_id=target_group_id)
            messages.success(request, f"Успешно распределено {len(student_ids)} студентов.")
        return redirect('accounts:unassigned_students')
        
    return render(request, 'accounts/unassigned_students.html', {
        'students': students,
        'groups': groups
    })


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
            
            if not user.is_superuser and target_group.specialty.department.faculty != faculty:
                messages.error(request, _("Ошибка доступа: попытка распределить в группу чужого факультета."))
                return redirect('accounts:unassigned_students')
            
            updated_count = Student.objects.filter(id__in=student_ids).update(group=target_group)
            
            from journal.models import StudentStatistics
            StudentStatistics.recalculate_group(target_group)
            
            messages.success(request, _(f"Успешно распределено {updated_count} студентов в группу {target_group.name}."))
        else:
            messages.warning(request, _(" Выберите студентов и укажите группу для распределения."))
        
        return redirect('accounts:unassigned_students')

    return render(request, 'accounts/unassigned_students.html', {
        'students': students,
        'groups': groups,
        'faculty': faculty
    })


@login_required
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
        messages.error(request, f"Ошибка генерации документа: {str(e)}")
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

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'GET':
        group_id: str = request.GET.get('group_id', '')
        if group_id and group_id.isdigit():
            students = Student.objects.filter(group_id=int(group_id), status='ACTIVE').select_related('user', 'group')
            data = [
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

                messages.success(request, _(f"Проект приказа №{new_order.number} успешно сформирован на {len(order_items)} студентов! Отправлен на подпись."))
                return redirect('accounts:all_orders')
                
            except Exception as e:
                messages.error(request, _(f"Ошибка при создании приказа: {str(e)}"))

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
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': _('Добавить специализацию (Тахассус)')})

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

    return render(request, 'accounts/form_generic.html', {'form': form, 'title': _('Редактировать специализацию')})

@login_required
@user_passes_test(is_management)
def delete_specialization(request, pk):
    spec = get_object_or_404(Specialization, pk=pk)
    if request.method == 'POST':
        spec.delete()
        messages.success(request, _("Специализация удалена!"))
        return redirect('accounts:manage_structure')
    return render(request, 'accounts/confirm_delete.html', {'obj': spec, 'title': _('Удалить специализацию')})











