from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from .models import User, Student, Teacher, Dean, Group
from datetime import datetime

class UserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, label="Роль")
    first_name = forms.CharField(max_length=150, required=True, label="Имя")
    last_name = forms.CharField(max_length=150, required=True, label="Фамилия")
    
    class Meta:
        model = User
        fields = ['role', 'first_name', 'last_name', 'phone', 'photo']
    
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
            'group', 'student_id', 'course', 'specialty', 'admission_year',
            'financing_type', 'status', 'education_type', 'education_language',
            'birth_date', 'gender', 'nationality',
            'passport_series', 'passport_number', 'passport_issued_by', 'passport_issue_date',
            'registration_address', 'residence_address',
            'sponsor_name', 'sponsor_phone', 'sponsor_relation'
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'passport_issue_date': forms.DateInput(attrs={'type': 'date'}),
            'registration_address': forms.Textarea(attrs={'rows': 3}),
            'residence_address': forms.Textarea(attrs={'rows': 3}),
        }

class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = [
            'degree', 'title', 'biography', 'research_interests',
            'consultation_hours', 'telegram', 'contact_email'
        ]
        widgets = {
            'biography': forms.Textarea(attrs={'rows': 4}),
            'research_interests': forms.Textarea(attrs={'rows': 4}),
        }

class DeanForm(forms.ModelForm):
    class Meta:
        model = Dean
        fields = ['office_location', 'reception_hours', 'contact_email']

class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'photo']

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
    class Meta:
        model = Group
        fields = ['name', 'course', 'academic_year', 'specialty']

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