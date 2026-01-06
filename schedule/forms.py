from django import forms
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom
from accounts.models import Group, Teacher

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'credits', 'teacher', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'credits': forms.NumberInput(attrs={'class': 'form-control', 'min': 3, 'step': 3}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'credits': 'Кредиты должны быть кратны 3 (делятся поровну между Лекцией, Практикой и СРСП)'
        }
    
    def clean_credits(self):
        credits = self.cleaned_data['credits']
        if credits % 3 != 0:
            raise forms.ValidationError('Кредиты должны быть кратны 3 (например: 3, 6, 9, 12)')
        return credits

class ScheduleSlotForm(forms.ModelForm):
    class Meta:
        model = ScheduleSlot
        fields = ['group', 'subject', 'lesson_type', 'teacher', 'day_of_week', 'start_time', 'end_time', 'classroom']
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'lesson_type': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'classroom': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester', None)
        super().__init__(*args, **kwargs)
        
        if semester:
            self.instance.semester = semester
        
        if 'subject' in self.data:
            try:
                subject_id = int(self.data.get('subject'))
                subject = Subject.objects.get(id=subject_id)
                if subject.teacher:
                    self.fields['teacher'].initial = subject.teacher
            except (ValueError, Subject.DoesNotExist):
                pass
        
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