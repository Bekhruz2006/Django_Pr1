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
                    Student.objects.create(
                        user=user,
                        student_id='',
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