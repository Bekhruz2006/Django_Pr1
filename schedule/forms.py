from django import forms
from .models import Subject, ScheduleSlot, ScheduleException, AcademicWeek
from accounts.models import Group, Teacher

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'type', 'hours_per_semester', 'teacher', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'hours_per_semester': forms.NumberInput(attrs={'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ScheduleSlotForm(forms.ModelForm):
    class Meta:
        model = ScheduleSlot
        fields = ['group', 'subject', 'teacher', 'day_of_week', 'start_time', 'end_time', 'classroom']
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'classroom': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Автоподстановка преподавателя при выборе предмета
        if 'subject' in self.data:
            try:
                subject_id = int(self.data.get('subject'))
                subject = Subject.objects.get(id=subject_id)
                if subject.teacher:
                    self.fields['teacher'].initial = subject.teacher
            except (ValueError, Subject.DoesNotExist):
                pass

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
            'new_classroom': forms.TextInput(attrs={'class': 'form-control'}),
        }

class AcademicWeekForm(forms.ModelForm):
    class Meta:
        model = AcademicWeek
        fields = ['semester_start_date', 'current_week']
        widgets = {
            'semester_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'current_week': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 20}),
        }