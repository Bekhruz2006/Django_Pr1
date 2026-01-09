# schedule/forms.py - ИСПРАВЛЕННАЯ ВЕРСИЯ SubjectForm

from django import forms
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom
from accounts.models import Group, Teacher

class SubjectForm(forms.ModelForm):
    """Форма для создания/редактирования предмета с распределением часов"""
    
    class Meta:
        model = Subject
        fields = [
            'name', 'code', 'teacher', 'groups',
            'lecture_hours', 'practice_hours', 'control_hours', 
            'independent_work_hours', 'semester_weeks',
            'description'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Математический анализ'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: MATH101'
            }),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'groups': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'lecture_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов лекций за семестр'
            }),
            'practice_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов практики за семестр'
            }),
            'control_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов КМРО за семестр'
            }),
            'independent_work_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Часов КМД'
            }),
            'semester_weeks': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 16,
                'min': 1,
                'max': 20
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'Дополнительная информация о предмете'
            }),
        }
        labels = {
            'name': 'Название предмета *',
            'code': 'Код предмета *',
            'teacher': 'Преподаватель',
            'groups': 'Группы (можно выбрать несколько)',
            'lecture_hours': 'Лекции (Л) - часов за семестр *',
            'practice_hours': 'Практика (А) - часов за семестр *',
            'control_hours': 'Контроль (КМРО) - часов за семестр *',
            'independent_work_hours': 'КМД (самостоятельная работа) - часов *',
            'semester_weeks': 'Недель в семестре',
            'description': 'Описание',
        }
        help_texts = {
            'lecture_hours': 'Аудиторные часы с преподавателем (Л)',
            'practice_hours': 'Практические/лабораторные занятия (А)',
            'control_hours': 'Контроль в аудитории (КМРО)',
            'independent_work_hours': 'Самостоятельная работа студента (КМД)',
            'semester_weeks': 'Обычно 16 недель',
            'groups': 'Удерживайте Ctrl (Cmd на Mac) для выбора нескольких групп',
        }
    
    def clean(self):
        cleaned_data = super().clean()
        
        lecture = cleaned_data.get('lecture_hours', 0)
        practice = cleaned_data.get('practice_hours', 0)
        control = cleaned_data.get('control_hours', 0)
        kmd = cleaned_data.get('independent_work_hours', 0)
        
        # Проверяем, что хотя бы один тип часов указан
        if lecture == 0 and practice == 0 and control == 0:
            raise forms.ValidationError(
                'Укажите хотя бы один тип аудиторных занятий (Лекции, Практика или КМРО)'
            )
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Автоматически рассчитываем общие кредиты по формуле: 1 кредит = 24 часа
        total_auditory = instance.lecture_hours + instance.practice_hours + instance.control_hours
        total_hours = total_auditory + instance.independent_work_hours
        
        # Обновляем старые поля для обратной совместимости
        instance.credits = round(total_hours / 24, 1) if total_hours > 0 else 0
        instance.hours_per_semester = total_hours
        
        # Устанавливаем основной тип на основе преобладающего типа занятий
        if instance.lecture_hours >= instance.practice_hours and instance.lecture_hours >= instance.control_hours:
            instance.type = 'LECTURE'
        elif instance.practice_hours >= instance.control_hours:
            instance.type = 'PRACTICE'
        else:
            instance.type = 'SRSP'
        
        if commit:
            instance.save()
            if self.cleaned_data.get('groups'):
                instance.groups.set(self.cleaned_data['groups'])
        
        return instance


# Остальные формы без изменений...

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