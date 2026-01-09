# schedule/forms.py - АВТОМАТИЧЕСКИЙ РАСЧЕТ ПО ФОРМУЛЕ

from django import forms
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom
from accounts.models import Group, Teacher

class SubjectForm(forms.ModelForm):
    """Форма для создания предмета - ТОЛЬКО общие кредиты, всё остальное автоматически"""
    
    class Meta:
        model = Subject
        fields = ['name', 'code', 'teacher', 'groups', 'credits', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Менеджменти экологї'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: MEN301'
            }),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'groups': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5'
            }),
            'credits': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: 6',
                'min': 1
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
            'credits': 'Общее количество кредитов *',
            'description': 'Описание',
        }
        help_texts = {
            'groups': 'Удерживайте Ctrl (Cmd на Mac) для выбора нескольких групп',
            'credits': 'Система автоматически рассчитает все часы по формуле: 1 кредит = 24 часа',
        }
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # ✅ АВТОМАТИЧЕСКИЙ РАСЧЕТ ПО ФОРМУЛЕ (как в таблице)
        total_credits = self.cleaned_data.get('total_credits', 0)
        
        # 1 кредит = 24 часа
        total_hours = total_credits * 24
        
        # КМД (самостоятельная работа) = 1/3 от общей трудоемкости
        kmd_hours = total_hours // 3
        
        # Аудиторные часы = 2/3 от общей трудоемкости
        auditory_hours = total_hours - kmd_hours
        
        # Аудиторные часы делятся поровну между Л, А, КМРО
        lecture_hours = auditory_hours // 3
        practice_hours = auditory_hours // 3
        control_hours = auditory_hours - lecture_hours - practice_hours  # остаток
        
        # Кредиты с преподавателем
        teacher_credits = auditory_hours // 24
        
        # Сохраняем в модель
        instance.credits = total_credits
        instance.hours_per_semester = total_hours
        instance.lecture_hours = lecture_hours
        instance.practice_hours = practice_hours
        instance.control_hours = control_hours
        instance.independent_work_hours = kmd_hours
        instance.semester_weeks = 16  # стандартно
        
        # Устанавливаем тип (основной - лекция)
        instance.type = 'LECTURE'
        
        if commit:
            instance.save()
            if self.cleaned_data.get('groups'):
                instance.groups.set(self.cleaned_data['groups'])
        
        return instance


# ========== ОСТАЛЬНЫЕ ФОРМЫ БЕЗ ИЗМЕНЕНИЙ ==========

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