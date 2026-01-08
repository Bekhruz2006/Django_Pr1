from django import forms
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom
from accounts.models import Group, Teacher

# schedule/forms.py - ОБНОВЛЕННАЯ ФОРМА SubjectForm

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = [
            'name', 'code', 'teacher', 'groups',
            'lecture_hours', 'practice_hours', 'control_hours', 
            'independent_work_hours', 'semester_weeks',
            'description'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'groups': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'lecture_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов за семестр'
            }),
            'practice_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов за семестр'
            }),
            'control_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов за семестр'
            }),
            'independent_work_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'КМД часов'
            }),
            'semester_weeks': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 16
            }),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'lecture_hours': 'Лекции (Л) - количество часов за семестр',
            'practice_hours': 'Практика (А) - количество часов за семестр',
            'control_hours': 'Контроль (КМРО) - количество часов за семестр',
            'independent_work_hours': 'КМД - самостоятельная работа студента',
            'semester_weeks': 'Обычно 16 недель',
        }

# ✅ ИСПРАВЛЕНО: Убрано несуществующее поле lesson_type
class ScheduleSlotForm(forms.ModelForm):
    class Meta:
        model = ScheduleSlot
        fields = ['group', 'subject', 'teacher', 'day_of_week', 'time_slot', 'classroom', 'room']
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'time_slot': forms.Select(attrs={'class': 'form-select'}),
            'classroom': forms.Select(attrs={'class': 'form-select'}),
            'room': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Номер кабинета'}),
        }
    
    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester', None)
        super().__init__(*args, **kwargs)
        
        if semester:
            self.instance.semester = semester
        
        self.fields['classroom'].queryset = Classroom.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.semester:
            raise forms.ValidationError("Семестр не указан")
        return cleaned_data

class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ['name', 'number', 'shift', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'number': forms.Select(attrs={'class': 'form-select'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError('Дата окончания должна быть позже даты начала')
        
        return cleaned_data

class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ['number', 'floor', 'capacity', 'is_active']
        widgets = {
            'number': forms.TextInput(attrs={'class': 'form-control'}),
            'floor': forms.NumberInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class BulkClassroomForm(forms.Form):
    floor = forms.IntegerField(
        label="Этаж",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    start_number = forms.IntegerField(
        label="Начальный номер",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    end_number = forms.IntegerField(
        label="Конечный номер",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    capacity = forms.IntegerField(
        label="Вместимость",
        initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_number')
        end = cleaned_data.get('end_number')
        
        if start and end and start >= end:
            raise forms.ValidationError('Конечный номер должен быть больше начального')
        
        return cleaned_data

class ScheduleExceptionForm(forms.ModelForm):
    class Meta:
        model = ScheduleException
        fields = ['exception_type', 'exception_date', 'reason', 'new_date', 'new_start_time', 'new_end_time', 'new_classroom']
        widgets = {
            'exception_type': forms.Select(attrs={'class': 'form-select'}),
            'exception_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'new_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'new_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'new_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'new_classroom': forms.Select(attrs={'class': 'form-select'}),
        }

class AcademicWeekForm(forms.Form):
    semester_start_date = forms.DateField(
        label="Дата начала семестра",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    current_week = forms.IntegerField(
        label="Текущая неделя",
        min_value=1,
        max_value=20,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )