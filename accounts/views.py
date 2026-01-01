from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db import models
from .models import User, Student, Teacher, Dean, Group, GroupTransferHistory
from .forms import (UserCreateForm, StudentForm, TeacherForm, DeanForm, 
                   UserEditForm, CustomPasswordChangeForm, PasswordResetByDeanForm,
                   GroupForm, GroupTransferForm)

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
            messages.error(request, 'Неверный логин или пароль')
    
    return render(request, 'accounts/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы')
    return redirect('accounts:login')

@login_required
def profile_view(request):
    user = request.user
    profile = None
    
    if user.role == 'STUDENT':
        profile = get_object_or_404(Student, user=user)
    elif user.role == 'TEACHER':
        profile = get_object_or_404(Teacher, user=user)
    elif user.role == 'DEAN':
        profile = get_object_or_404(Dean, user=user)
    
    return render(request, f'accounts/profile_{user.role.lower()}.html', {
        'profile': profile
    })

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
        
        if user_form.is_valid() and (profile_form is None or profile_form.is_valid()):
            user_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, 'Профиль успешно обновлен')
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
            messages.success(request, 'Пароль успешно изменен')
            return redirect('accounts:profile')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@user_passes_test(is_dean)
def user_management(request):
    role_filter = request.GET.get('role', '')
    search = request.GET.get('search', '')
    
    users = User.objects.all()
    
    if role_filter:
        users = users.filter(role=role_filter)
    
    if search:
        users = users.filter(
            models.Q(username__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search)
        )
    
    return render(request, 'accounts/user_management.html', {
        'users': users,
        'role_filter': role_filter,
        'search': search
    })

@user_passes_test(is_dean)
def add_user(request):
    if request.method == 'POST':
        user_form = UserCreateForm(request.POST, request.FILES)
        
        if user_form.is_valid():
            with transaction.atomic():
                user = user_form.save()
                
                role = user_form.cleaned_data['role']
                
                if role == 'STUDENT':
                    student_id = generate_student_id()

                    Student.objects.create(
                        user=user,
                        student_id=student_id,
                        course=1,
                        specialty='',
                        admission_year=2025,
                        financing_type='BUDGET',
                        education_type='FULL_TIME',
                        education_language='RU',
                        birth_date='2000-01-01',
                        gender='M',
                        nationality='',
                        passport_series='',
                        passport_number='',
                        passport_issued_by='',
                        passport_issue_date='2000-01-01',
                        registration_address='',
                        residence_address=''
                    )
                elif role == 'TEACHER':
                    Teacher.objects.create(user=user)
                elif role == 'DEAN':
                    Dean.objects.create(user=user)
                
                messages.success(request, f'Пользователь {user.username} успешно создан. Временный пароль: password123')
                return redirect('accounts:user_management')
    else:
        user_form = UserCreateForm()
    
    return render(request, 'accounts/add_user.html', {'form': user_form})

@user_passes_test(is_dean)
def edit_user(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        user_form = UserEditForm(request.POST, request.FILES, instance=user_obj)
        
        profile_form = None
        if user_obj.role == 'STUDENT':
            profile_form = StudentForm(request.POST, instance=user_obj.student_profile)
        elif user_obj.role == 'TEACHER':
            profile_form = TeacherForm(request.POST, instance=user_obj.teacher_profile)
        elif user_obj.role == 'DEAN':
            profile_form = DeanForm(request.POST, instance=user_obj.dean_profile)
        
        if user_form.is_valid() and (profile_form is None or profile_form.is_valid()):
            user_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, 'Пользователь успешно обновлен')
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
    
    return render(request, 'accounts/edit_user.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'user_obj': user_obj
    })

@user_passes_test(is_dean)
def reset_password(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = PasswordResetByDeanForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            user_obj.set_password(new_password)
            user_obj.save()
            messages.success(request, f'Пароль для {user_obj.username} успешно сброшен')
            return redirect('accounts:user_management')
    else:
        form = PasswordResetByDeanForm()
    
    return render(request, 'accounts/reset_password.html', {
        'form': form,
        'user_obj': user_obj
    })

@user_passes_test(is_dean)
def toggle_user_active(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    user_obj.is_active = not user_obj.is_active
    user_obj.save()
    
    status = "активирован" if user_obj.is_active else "заблокирован"
    messages.success(request, f'Пользователь {user_obj.username} {status}')
    return redirect('accounts:user_management')

@user_passes_test(is_dean)
def transfer_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    
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
                
                messages.success(request, f'Студент переведен из {old_group} в {new_group}')
                return redirect('accounts:user_management')
    else:
        form = GroupTransferForm()
    
    return render(request, 'accounts/transfer_student.html', {
        'form': form,
        'student': student
    })

@login_required
def view_user_profile(request, user_id):
    
    if request.user.role != 'DEAN':
        messages.error(request, 'Доступ запрещен')
        return redirect('core:dashboard')
    
    user_obj = get_object_or_404(User, id=user_id)
    profile = None
    template = 'accounts/profile_student.html'
    
    if user_obj.role == 'STUDENT':
        profile = get_object_or_404(Student, user=user_obj)
        template = 'accounts/profile_student.html'
    elif user_obj.role == 'TEACHER':
        profile = get_object_or_404(Teacher, user=user_obj)
        template = 'accounts/profile_teacher.html'
    elif user_obj.role == 'DEAN':
        profile = get_object_or_404(Dean, user=user_obj)
        template = 'accounts/profile_dean.html'
    
    return render(request, template, {
        'user': user_obj,
        'profile': profile,
        'viewing_as_dean': True
    })

@user_passes_test(is_dean)
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

@user_passes_test(is_dean)
def add_group(request):
    
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Группа {group.name} успешно создана')
            return redirect('accounts:group_management')
    else:
        form = GroupForm()
    
    return render(request, 'accounts/add_group.html', {'form': form})

@user_passes_test(is_dean)
def edit_group(request, group_id):
    
    group = get_object_or_404(Group, id=group_id)
    
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, f'Группа {group.name} успешно обновлена')
            return redirect('accounts:group_management')
    else:
        form = GroupForm(instance=group)
    
    return render(request, 'accounts/edit_group.html', {
        'form': form,
        'group': group
    })

@user_passes_test(is_dean)
def delete_group(request, group_id):
    
    group = get_object_or_404(Group, id=group_id)
    
    students_count = Student.objects.filter(group=group).count()
    
    if request.method == 'POST':
        if students_count > 0:
            messages.error(request, f'Невозможно удалить группу {group.name}. В ней есть {students_count} студентов.')
        else:
            group_name = group.name
            group.delete()
            messages.success(request, f'Группа {group_name} успешно удалена')
        return redirect('accounts:group_management')
    
    return render(request, 'accounts/delete_group.html', {
        'group': group,
        'students_count': students_count
    })