from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db import models
from django.http import HttpResponseForbidden
from .models import (
    User, Student, Teacher, Dean, Group, GroupTransferHistory,
    Department, Specialty, Institute, Faculty, HeadOfDepartment, Director, ProRector
)
from .forms import (
    UserCreateForm, StudentForm, TeacherForm, DeanForm,
    UserEditForm, CustomPasswordChangeForm, PasswordResetByDeanForm,
    GroupForm, GroupTransferForm, DepartmentCreateForm, SpecialtyCreateForm,
    InstituteForm, FacultyForm, DepartmentForm, SpecialtyForm, HeadOfDepartmentForm
)
from django.core.exceptions import ObjectDoesNotExist
from .forms import InstituteManagementForm




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
    context = {'profile': profile}
    
    if user.role == 'STUDENT':
        profile = get_object_or_404(Student, user=user)
        from journal.models import StudentStatistics
        stats, _ = StudentStatistics.objects.get_or_create(student=profile)
        stats.recalculate()
        profile.statistics = stats
        context['profile'] = profile
        
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
                    stats, _ = StudentStatistics.objects.get_or_create(student=student)
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
            messages.success(request, 'Пароль успешно изменен')
            return redirect('accounts:profile')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@user_passes_test(is_management)
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
        except ObjectDoesNotExist:
            user_data['has_profile'] = False
        
        users_with_profiles.append(user_data)
    
    return render(request, 'accounts/user_management.html', {
        'users': users,
        'users_with_profiles': users_with_profiles,
        'role_filter': role_filter,
        'search': search
    })

@user_passes_test(is_management)
def add_user(request):
    # Поддержка добавления преподавателя сразу в кафедру
    department_id = request.GET.get('department')
    initial_data = {}
    
    # Если передана роль в URL (например, ?role=TEACHER)
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
                    messages.error(request, "У вас нет прав создавать руководство института.")
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
                                
                    
                    messages.success(request, f'Пользователь {user.username} ({user.get_role_display()}) успешно создан.')
                    
                    if department_id:
                        return redirect('accounts:manage_structure')
                        
                    return redirect('accounts:user_management')
                    
                except Exception as e:
                    messages.error(request, f'Ошибка при настройке профиля: {str(e)}')
                    print(e)
    else:
        user_form = UserCreateForm(creator=request.user, initial=initial_data)
    
    return render(request, 'accounts/add_user.html', {'form': user_form})

@user_passes_test(is_management)
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
        elif user_obj.role == 'HEAD_OF_DEPT':
            profile_form = HeadOfDepartmentForm(request.POST, instance=user_obj.head_of_dept_profile)
        
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

@user_passes_test(is_management)
def toggle_user_active(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    
    if user_obj.id == request.user.id:
        messages.error(request, '❌ Вы не можете заблокировать сам себя!')
        return redirect('accounts:user_management')
    
    if user_obj.is_superuser and not request.user.is_superuser:
        messages.error(request, '❌ Вы не можете заблокировать суперпользователя!')
        return redirect('accounts:user_management')
    
    user_obj.is_active = not user_obj.is_active
    user_obj.save()
    
    status = "активирован" if user_obj.is_active else "заблокирован"
    messages.success(request, f'Пользователь {user_obj.username} {status}')
    return redirect('accounts:user_management')

@user_passes_test(is_management)
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
    if not is_management(request.user) and request.user.role != 'TEACHER':
         messages.error(request, 'Доступ запрещен')
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
        stats, _ = StudentStatistics.objects.get_or_create(student=profile)
        stats.recalculate()
        profile.statistics = stats
        context['profile'] = profile
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
    # Проверка прав
    if not (request.user.is_superuser or request.user.role in ['DEAN', 'VICE_DEAN']):
        messages.error(request, "Нет доступа")
        return redirect('core:dashboard')

    # Получаем параметры из URL
    specialty_id = request.GET.get('specialty')
    
    # Инициализация данных формы
    initial_data = {}
    if specialty_id:
        try:
            specialty = Specialty.objects.get(id=specialty_id)
            # Проверка прав декана на эту специальность
            if is_dean(request.user) and hasattr(request.user, 'dean_profile'):
                if specialty.department.faculty != request.user.dean_profile.faculty:
                    messages.error(request, "Это специальность чужого факультета")
                    return redirect('accounts:manage_structure')
            initial_data['specialty'] = specialty
        except Specialty.DoesNotExist:
            pass

    # Функция фильтрации (DRY - Don't Repeat Yourself)
    def configure_form(form):
        if request.user.role == 'DEAN' and hasattr(request.user, 'dean_profile'):
            faculty = request.user.dean_profile.faculty
            if faculty:
                form.fields['specialty'].queryset = Specialty.objects.filter(department__faculty=faculty)

    if request.method == 'POST':
        form = GroupForm(request.POST, initial=initial_data) # Передаем initial даже в POST для корректной работы виджетов
        configure_form(form) # Фильтруем выбор ДО валидации

        if form.is_valid():
            try:
                # Дополнительная проверка безопасности
                if is_dean(request.user):
                    spec = form.cleaned_data['specialty']
                    if spec.department.faculty != request.user.dean_profile.faculty:
                        raise Exception("Попытка создания группы на чужом факультете")

                group = form.save()
                messages.success(request, f'Группа {group.name} успешно создана')
                
                # Если пришли из структуры - возвращаемся в структуру
                if specialty_id:
                    return redirect('accounts:manage_structure')
                return redirect('accounts:group_management')
            except Exception as e:
                messages.error(request, f"Ошибка сохранения: {str(e)}")
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме.")
    else:
        form = GroupForm(initial=initial_data)
        configure_form(form)

    return render(request, 'accounts/add_group.html', {'form': form})

@user_passes_test(is_management)
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
    return render(request, 'accounts/edit_group.html', {'form': form, 'group': group})

@user_passes_test(is_management)
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    students_count = Student.objects.filter(group=group).count()
    if request.method == 'POST':
        if students_count > 0:
            messages.error(request, f'Невозможно удалить группу {group.name}. В ней есть {students_count} студентов.')
        else:
            group.delete()
            messages.success(request, f'Группа {group.name} успешно удалена')
        return redirect('accounts:group_management')
    return render(request, 'accounts/delete_group.html', {'group': group, 'students_count': students_count})

# --- УПРАВЛЕНИЕ СТРУКТУРОЙ ---

@login_required
def manage_structure(request):
    """Страница управления структурой. Адаптируется под роль."""
    if not is_management(request.user):
        return redirect('core:dashboard')
        
    context = {}
    
    # 1. СУПЕРЮЗЕР / РЕКТОР: Видят всё
    if request.user.is_superuser or request.user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        # !!! ИСПРАВЛЕНИЕ ЗДЕСЬ !!!
        institutes = Institute.objects.prefetch_related(
            'faculties__departments__specialties',
            'faculties__dean_manager__user', # Чтобы получить имя декана
            'directors__user' # Исправлено: director_profile -> directors (related_name)
        ).all()
        context['institutes'] = institutes
        context['is_admin'] = True
        return render(request, 'accounts/structure_manage.html', context)
        
    # 2. ДЕКАН: Видит свой факультет
    elif request.user.role in ['DEAN', 'VICE_DEAN']:
        user_faculty = None
        if hasattr(request.user, 'dean_profile'):
            user_faculty = request.user.dean_profile.faculty
        elif hasattr(request.user, 'vicedean_profile'):
            user_faculty = request.user.vicedean_profile.faculty
            
        if user_faculty:
            # Показываем только этот факультет
            context['faculty'] = user_faculty
            context['departments'] = Department.objects.filter(faculty=user_faculty).prefetch_related('specialties', 'head__user')
            context['is_dean'] = True
            return render(request, 'accounts/structure_manage.html', context)
        else:
            messages.error(request, "Ваш профиль не привязан к факультету")
            return redirect('core:dashboard')
            
    return redirect('core:dashboard')

# --- CRUD ДЛЯ ИНСТИТУТА (Только Админ) ---
@user_passes_test(is_admin_or_rector)
def add_institute(request):
    if request.method == 'POST':
        form = InstituteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Институт добавлен")
            return redirect('accounts:manage_structure')
    else:
        form = InstituteForm()
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Добавить Институт'})

@user_passes_test(is_admin_or_rector)
def edit_institute(request, pk):
    institute = get_object_or_404(Institute, pk=pk)
    
    # Получаем текущих руководителей
    current_director = institute.directors.first()
    current_vice = institute.prorectors.filter(title__icontains='таълим').first()
    
    initial_data = {
        'name': institute.name,
        'abbreviation': institute.abbreviation,
        'address': institute.address,
        'director': current_director.user if current_director else None,
        'vice_director_edu': current_vice.user if current_vice else None,
    }

    if request.method == 'POST':
        form = InstituteForm(request.POST, instance=institute)
        mgmt_form = InstituteManagementForm(request.POST)
        
        if form.is_valid() and mgmt_form.is_valid():
            with transaction.atomic():
                form.save()
                
                # Обновление Директора
                new_director_user = mgmt_form.cleaned_data['director']
                if new_director_user:
                    Director.objects.update_or_create(
                        institute=institute,
                        defaults={'user': new_director_user}
                    )
                
                # Обновление Зам. директора
                new_vice_user = mgmt_form.cleaned_data['vice_director_edu']
                if new_vice_user:
                    ProRector.objects.update_or_create(
                        institute=institute,
                        title="Муовини директор оид ба таълим", # Стандартное название
                        defaults={'user': new_vice_user}
                    )
                
            messages.success(request, "Институт и руководство обновлены")
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
        messages.success(request, "Институт удален")
        return redirect('accounts:manage_structure')
    return render(request, 'accounts/confirm_delete.html', {'obj': institute, 'title': 'Удалить Институт'})

# --- CRUD ДЛЯ ФАКУЛЬТЕТА (Только Админ) ---
@user_passes_test(is_admin_or_rector)
def add_faculty(request):
    # Поддержка предзаполнения института из GET-параметра
    initial_data = {}
    institute_id = request.GET.get('institute')
    if institute_id:
        initial_data['institute'] = get_object_or_404(Institute, pk=institute_id)

    if request.method == 'POST':
        form = FacultyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Факультет добавлен")
            return redirect('accounts:manage_structure')
    else:
        form = FacultyForm(initial=initial_data)
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Добавить Факультет'})

@user_passes_test(is_admin_or_rector)
def edit_faculty(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if request.method == 'POST':
        form = FacultyForm(request.POST, instance=faculty)
        if form.is_valid():
            form.save()
            messages.success(request, "Факультет обновлен")
            return redirect('accounts:manage_structure')
    else:
        form = FacultyForm(instance=faculty)
    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Редактировать Факультет'})

@user_passes_test(is_admin_or_rector)
def delete_faculty(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if request.method == 'POST':
        faculty.delete()
        messages.success(request, "Факультет удален")
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
                    messages.error(request, "Вы можете добавлять кафедры только в свой факультет")
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

            messages.success(request, f"Кафедра {dept.name} создана")
            return redirect('accounts:manage_structure')
    else:
        form = DepartmentForm(initial=initial, faculty_context=faculty_context)
        if is_dean(request.user):
             # Блокируем выбор факультета для декана (он видит только свой)
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
            return HttpResponseForbidden("Это не ваша кафедра")

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

            messages.success(request, "Кафедра обновлена")
            return redirect('accounts:manage_structure')
    else:
        form = DepartmentForm(instance=dept, faculty_context=dept.faculty)
        if is_dean(request.user):
             faculty = request.user.dean_profile.faculty
             form.fields['faculty'].queryset = Faculty.objects.filter(id=faculty.id)

    return render(request, 'accounts/form_generic.html', {'form': form, 'title': 'Редактировать кафедру'})



@login_required
def delete_department(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if not is_management(request.user):
        return HttpResponseForbidden()
    if is_dean(request.user) and dept.faculty != request.user.dean_profile.faculty:
        return HttpResponseForbidden()

    if request.method == 'POST':
        dept.delete()
        messages.success(request, "Кафедра удалена")
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
                    messages.error(request, "Ошибка доступа к кафедре")
                    return redirect('accounts:manage_structure')
            form.save()
            messages.success(request, "Специальность добавлена")
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
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = SpecialtyForm(request.POST, instance=spec)
        if form.is_valid():
            form.save()
            messages.success(request, "Специальность обновлена")
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
        return HttpResponseForbidden()

    if request.method == 'POST':
        spec.delete()
        messages.success(request, "Специальность удалена")
        return redirect('accounts:manage_structure')
    return render(request, 'accounts/confirm_delete.html', {'obj': spec, 'title': 'Удалить специальность'})