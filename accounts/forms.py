from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from .models import (
    User, Student, Teacher, Dean, Group, ProRector, HeadOfDepartment,
    Institute, Faculty, Department, Specialty
)
from datetime import datetime
from core.validators import validate_image_only

# --- НОВЫЕ ФОРМЫ СТРУКТУРЫ ---

class InstituteForm(forms.ModelForm):
    class Meta:
        model = Institute
        fields = ['name', 'abbreviation', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'abbreviation': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class FacultyForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = ['institute', 'name', 'code']
        widgets = {
            'institute': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
        }

class DepartmentCreateForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name']  
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

class DepartmentForm(forms.ModelForm):
    head_of_department = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Заведующий кафедрой",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Department
        fields = ['faculty', 'name']
        widgets = {
            'faculty': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop('faculty_context', None) 
        super().__init__(*args, **kwargs)
        
        if self.instance.pk:
            if not faculty:
                faculty = self.instance.faculty
            
            if hasattr(self.instance, 'head'):
                self.fields['head_of_department'].initial = self.instance.head.user

        queryset = User.objects.filter(
            role__in=['TEACHER', 'HEAD_OF_DEPT']
        )
        
        self.fields['head_of_department'].queryset = queryset
        self.fields['head_of_department'].label_from_instance = lambda obj: f"{obj.get_full_name()} ({obj.get_role_display()})"


class SpecialtyCreateForm(forms.ModelForm):
    class Meta:
        model = Specialty
        fields = ['department', 'name', 'code', 'qualification']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)
        if faculty:
            # Показываем только кафедры этого факультета
            self.fields['department'].queryset = Department.objects.filter(faculty=faculty)

class SpecialtyForm(forms.ModelForm):
    class Meta:
        model = Specialty
        fields = ['department', 'name', 'code', 'qualification']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control'}),
        }

# --- ФОРМЫ ДЛЯ РУКОВОДИТЕЛЕЙ ---

class HeadOfDepartmentForm(forms.ModelForm):
    class Meta:
        model = HeadOfDepartment
        fields = ['department', 'degree']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'degree': forms.TextInput(attrs={'class': 'form-control'}),
        }

class TeacherEditForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['department', 'degree', 'title', 'biography', 'contact_email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['degree'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Например: Кандидат технических наук'})
        self.fields['title'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Например: Доцент'})
        self.fields['department'].widget.attrs.update({'class': 'form-select'})
        self.fields['biography'].widget.attrs.update({'class': 'form-control'})
        self.fields['contact_email'].widget.attrs.update({'class': 'form-control'})

class ProRectorForm(forms.ModelForm):
    class Meta:
        model = ProRector
        fields = ['institute', 'title']
        widgets = {
            'institute': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Муовини директор оид ба таълим'}),
        }


class UserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(label="Роль", widget=forms.Select(attrs={'class': 'form-select'}))
    first_name = forms.CharField(max_length=150, required=True, label="Имя", widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, required=True, label="Фамилия", widget=forms.TextInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(required=False, label="Телефон", widget=forms.TextInput(attrs={'class': 'form-control'}))
    photo = forms.ImageField(required=False, label="Фото", widget=forms.FileInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['role', 'first_name', 'last_name', 'phone', 'photo']

    def __init__(self, *args, **kwargs):
        creator = kwargs.pop('creator', None)
        super().__init__(*args, **kwargs)
        if self.initial.get('role'):
            pass         
        if creator:
            if creator.role == 'DEAN' or creator.role == 'VICE_DEAN':
                allowed_roles = [
                    ('STUDENT', 'Студент'),
                    ('TEACHER', 'Преподаватель'),
                    ('HEAD_OF_DEPT', 'Зав. кафедрой'),
                    ('VICE_DEAN', 'Зам. декана'),
                ]
                self.fields['role'].choices = allowed_roles
            elif creator.is_superuser or creator.role in ['RECTOR', 'DIRECTOR']:
                self.fields['role'].choices = User.ROLE_CHOICES
            else:
                self.fields['role'].choices = []

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.generate_unique_username()
        user.set_password('password123')
        if commit:
            user.save()
        return user

    def generate_unique_username(self):
        year = datetime.now().year
        base_username = f"{year}502"
        last_user = User.objects.filter(username__startswith=base_username).order_by('-username').first()
        if last_user:
            try:
                last_number = int(last_user.username[len(base_username):])
                new_number = last_number + 1
            except ValueError:
                new_number = 1
        else:
            new_number = 1
        return f"{base_username}{new_number:03d}"

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'group', 'student_id', 'course', 'admission_year',
            'financing_type', 'status', 'education_type', 'education_language',
            'birth_date', 'gender', 'nationality',
            'passport_series', 'passport_number', 'passport_issued_by', 'passport_issue_date',
            'registration_address', 'residence_address',
        ]
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select'}),
            'student_id': forms.TextInput(attrs={'class': 'form-control'}),
            'course': forms.NumberInput(attrs={'class': 'form-control'}),
            'admission_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'financing_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'education_type': forms.Select(attrs={'class': 'form-select'}),
            'education_language': forms.Select(attrs={'class': 'form-select'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'nationality': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_series': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_issued_by': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'registration_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'residence_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class TeacherForm(forms.ModelForm):
    additional_departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.none(),
        required=False,
        label="Дополнительные кафедры (где может преподавать)",
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-multiple', 'size': '5'})
    )
    class Meta:
        model = Teacher

        fields = [
            'department', 'additional_departments', # Добавили поле сюда
            'degree', 'title', 'biography', 'research_interests',
            'consultation_hours', 'telegram', 'contact_email'
        ]
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'degree': forms.TextInput(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'biography': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'research_interests': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'consultation_hours': forms.TextInput(attrs={'class': 'form-control'}),
            'telegram': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['department'].queryset = Department.objects.all()
        self.fields['additional_departments'].queryset = Department.objects.all()
        
        if self.instance.pk and self.instance.department:
            self.fields['additional_departments'].queryset = Department.objects.exclude(id=self.instance.department.id)


class DeanForm(forms.ModelForm):
    class Meta:
        model = Dean
        fields = ['faculty', 'office_location', 'reception_hours', 'contact_email']
        widgets = {
            'faculty': forms.Select(attrs={'class': 'form-select'}),
            'office_location': forms.TextInput(attrs={'class': 'form-control'}),
            'reception_hours': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class UserEditForm(forms.ModelForm):
    photo = forms.ImageField(required=False, validators=[validate_image_only], widget=forms.FileInput(attrs={'class': 'form-control'}))
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

class CustomPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Старый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    new_password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

class PasswordResetByDeanForm(forms.Form):
    new_password = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    confirm_password = forms.CharField(
        label="Подтвердите пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('new_password')
        confirm = cleaned_data.get('confirm_password')

        if password != confirm:
            raise forms.ValidationError("Пароли не совпадают")

        return cleaned_data

class GroupForm(forms.ModelForm):
    assign_students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.all(),
        required=False,
        label="Добавить студентов в группу",
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-multiple', 'size': '10'})
    )

    class Meta:
        model = Group
        fields = ['specialty', 'name', 'course', 'academic_year', 'language', 'has_military_training']
        widgets = {
            'specialty': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'course': forms.NumberInput(attrs={'class': 'form-control'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'has_military_training': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['assign_students'].initial = self.instance.students.all()

        self.fields['assign_students'].queryset = Student.objects.select_related('user').order_by('user__last_name')

    def save(self, commit=True):
        group = super().save(commit=commit)
        if commit:
            selected_students = self.cleaned_data.get('assign_students')
            if selected_students:
                self.instance.students.exclude(id__in=selected_students.values_list('id', flat=True)).update(group=None)
                for student in selected_students:
                    student.group = group
                    student.save()
        return group


class InstituteManagementForm(forms.Form):
    director = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['DIRECTOR', 'TEACHER', 'DEAN']),
        required=False,
        label="Директор института",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    vice_director_edu = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['PRO_RECTOR', 'VICE_DEAN', 'TEACHER']),
        required=False,
        label="Зам. директора (по учебной работе)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    head_of_edu = forms.CharField(
        required=False,
        label="Сардори раёсати таълим (ФИО)",
        initial="Ҷалилов Р.Р.", # Значение по умолчанию из примера
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )






class GroupTransferForm(forms.Form):
    to_group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        label="Новая группа",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    reason = forms.CharField(
        label="Причина перевода",
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False
    )