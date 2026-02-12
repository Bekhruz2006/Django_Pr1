from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import JournalEntry, JournalChangeLog
from accounts.models import Group
from schedule.models import Subject

class JournalEntryForm(forms.ModelForm):

    class Meta:
        model = JournalEntry
        fields = ['grade', 'attendance_status']
        widgets = {
            'grade': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': 1,
                'max': 12,
                'placeholder': _('1-12')
            }),
            'attendance_status': forms.Select(attrs={
                'class': 'form-select form-select-sm'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        grade = cleaned_data.get('grade')
        attendance_status = cleaned_data.get('attendance_status')

        if grade is not None and grade > 0 and attendance_status != 'PRESENT':
            raise ValidationError(
                _("Нельзя одновременно установить балл и статус отсутствия. "
                "Балл автоматически означает присутствие.")
            )
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            if self.instance.is_locked():
                
                for field in self.fields.values():
                    field.disabled = True
                    field.widget.attrs['class'] += ' bg-secondary bg-opacity-25'
                    field.widget.attrs['title'] = _('🔒 Заблокировано (прошло 24 часа)')

class BulkGradeForm(forms.Form):

    students = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("Выберите студентов")
    )
    
    grade = forms.IntegerField(
        min_value=1,
        max_value=12,
        required=False,
        label=_("Балл"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': _('1-12')
        })
    )
    
    attendance_status = forms.ChoiceField(
        choices=[('', _('---'))] + JournalEntry.ATTENDANCE_CHOICES,
        required=False,
        label=_("Статус посещения"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        students_queryset = kwargs.pop('students_queryset', None)
        super().__init__(*args, **kwargs)
        
        if students_queryset:
            self.fields['students'].choices = [
                (s.id, s.user.get_full_name()) 
                for s in students_queryset
            ]
    
    def clean(self):
        cleaned_data = super().clean()
        grade = cleaned_data.get('grade')
        attendance_status = cleaned_data.get('attendance_status')
        
        if not grade and not attendance_status:
            raise ValidationError(_("Выберите либо балл, либо статус посещения"))
        
        if grade and attendance_status and attendance_status != 'PRESENT':
            raise ValidationError(_("Нельзя одновременно установить балл и статус отсутствия"))
        
        return cleaned_data

class JournalFilterForm(forms.Form):

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        empty_label=_("-- Выберите группу --"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(),
        required=True,
        empty_label=_("-- Выберите предмет --"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    week = forms.IntegerField(
        min_value=1,
        max_value=20,
        required=False,
        label=_("Учебная неделя"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': _('I-XX')
        })
    )
    
    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop('teacher', None)
        super().__init__(*args, **kwargs)

        if teacher:
            
            self.fields['subject'].queryset = Subject.objects.filter(teacher=teacher)

            from schedule.models import ScheduleSlot
            group_ids = ScheduleSlot.objects.filter(
                teacher=teacher,
                is_active=True
            ).values_list('group_id', flat=True).distinct()
            self.fields['group'].queryset = Group.objects.filter(id__in=group_ids)

class ChangeLogFilterForm(forms.Form):

    date_from = forms.DateField(
        required=False,
        label=_("С даты"),
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        label=_("По дату"),
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    student = forms.ChoiceField(
        required=False,
        choices=[('', _('Все студенты'))],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    teacher = forms.ChoiceField(
        required=False,
        choices=[('', _('Все преподаватели'))],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        group = kwargs.pop('group', None)
        subject = kwargs.pop('subject', None)
        super().__init__(*args, **kwargs)
        
        if group:
            from accounts.models import Student
            students = Student.objects.filter(group=group)
            self.fields['student'].choices = [('', _('Все студенты'))] + [
                (s.id, s.user.get_full_name()) for s in students
            ]
        
        if subject:
            from accounts.models import Teacher
            teachers = Teacher.objects.filter(subjects=subject)
            self.fields['teacher'].choices = [('', _('Все преподаватели'))] + [
                (t.id, t.user.get_full_name()) for t in teachers
            ]