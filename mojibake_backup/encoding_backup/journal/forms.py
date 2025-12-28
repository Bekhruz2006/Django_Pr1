from django import forms
from django.core.exceptions import ValidationError
from .models import JournalEntry, JournalChangeLog
from accounts.models import Group
from schedule.models import Subject

class JournalEntryForm(forms.ModelForm):
    """Ð¤Ð¾ÑÐ¼Ð° Ð´Ð»Ñ ÑÐµÐ´Ð°ÐºÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ñ Ð¾Ð´Ð½Ð¾Ð¹ ÑÑÐµÐ¹ÐºÐ¸ Ð¶ÑÑÐ½Ð°Ð»Ð°"""
    
    class Meta:
        model = JournalEntry
        fields = ['grade', 'attendance_status']
        widgets = {
            'grade': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': 1,
                'max': 12,
                'placeholder': '1-12'
            }),
            'attendance_status': forms.Select(attrs={
                'class': 'form-select form-select-sm'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        grade = cleaned_data.get('grade')
        attendance_status = cleaned_data.get('attendance_status')
        
        # ÐÐ°Ð»Ð¸Ð´Ð°ÑÐ¸Ñ: Ð½ÐµÐ»ÑÐ·Ñ Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾ ÑÑÑÐ°Ð½Ð¾Ð²Ð¸ÑÑ Ð±Ð°Ð»Ð» Ð¸ ÑÑÐ°ÑÑÑ ÐÐ
        if grade is not None and grade > 0 and attendance_status != 'PRESENT':
            raise ValidationError(
                "ÐÐµÐ»ÑÐ·Ñ Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾ ÑÑÑÐ°Ð½Ð¾Ð²Ð¸ÑÑ Ð±Ð°Ð»Ð» Ð¸ ÑÑÐ°ÑÑÑ Ð¾ÑÑÑÑÑÑÐ²Ð¸Ñ. "
                "ÐÐ°Ð»Ð» Ð°Ð²ÑÐ¾Ð¼Ð°ÑÐ¸ÑÐµÑÐºÐ¸ Ð¾Ð·Ð½Ð°ÑÐ°ÐµÑ Ð¿ÑÐ¸ÑÑÑÑÑÐ²Ð¸Ðµ."
            )
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # ÐÑÐ¾Ð²ÐµÑÐºÐ° Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²ÐºÐ¸
        if self.instance and self.instance.pk:
            if self.instance.is_locked():
                # ÐÐ°Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²Ð°Ð½Ð½ÑÐµ ÑÑÐµÐ¹ÐºÐ¸ - Ð²ÑÐµ Ð¿Ð¾Ð»Ñ readonly
                for field in self.fields.values():
                    field.disabled = True
                    field.widget.attrs['class'] += ' bg-secondary bg-opacity-25'
                    field.widget.attrs['title'] = 'ð ÐÐ°Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²Ð°Ð½Ð¾ (Ð¿ÑÐ¾ÑÐ»Ð¾ 24 ÑÐ°ÑÐ°)'


class BulkGradeForm(forms.Form):
    """Ð¤Ð¾ÑÐ¼Ð° Ð´Ð»Ñ Ð¼Ð°ÑÑÐ¾Ð²Ð¾Ð³Ð¾ Ð·Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ð¾ÑÐµÐ½Ð¾Ðº"""
    
    students = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="ÐÑÐ±ÐµÑÐ¸ÑÐµ ÑÑÑÐ´ÐµÐ½ÑÐ¾Ð²"
    )
    
    grade = forms.IntegerField(
        min_value=1,
        max_value=12,
        required=False,
        label="ÐÐ°Ð»Ð»",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '1-12'
        })
    )
    
    attendance_status = forms.ChoiceField(
        choices=[('', '---')] + JournalEntry.ATTENDANCE_CHOICES,
        required=False,
        label="Ð¡ÑÐ°ÑÑÑ Ð¿Ð¾ÑÐµÑÐµÐ½Ð¸Ñ",
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
            raise ValidationError("ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð»Ð¸Ð±Ð¾ Ð±Ð°Ð»Ð», Ð»Ð¸Ð±Ð¾ ÑÑÐ°ÑÑÑ Ð¿Ð¾ÑÐµÑÐµÐ½Ð¸Ñ")
        
        if grade and attendance_status and attendance_status != 'PRESENT':
            raise ValidationError("ÐÐµÐ»ÑÐ·Ñ Ð¾Ð´Ð½Ð¾Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾ ÑÑÑÐ°Ð½Ð¾Ð²Ð¸ÑÑ Ð±Ð°Ð»Ð» Ð¸ ÑÑÐ°ÑÑÑ Ð¾ÑÑÑÑÑÑÐ²Ð¸Ñ")
        
        return cleaned_data


class JournalFilterForm(forms.Form):
    """Ð¤Ð¾ÑÐ¼Ð° ÑÐ¸Ð»ÑÑÑÐ°ÑÐ¸Ð¸ Ð¶ÑÑÐ½Ð°Ð»Ð°"""
    
    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        empty_label="-- ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð³ÑÑÐ¿Ð¿Ñ --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(),
        required=True,
        empty_label="-- ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð¿ÑÐµÐ´Ð¼ÐµÑ --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    week = forms.IntegerField(
        min_value=1,
        max_value=20,
        required=False,
        label="Ð£ÑÐµÐ±Ð½Ð°Ñ Ð½ÐµÐ´ÐµÐ»Ñ",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'I-XX'
        })
    )
    
    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop('teacher', None)
        super().__init__(*args, **kwargs)
        
        # ÐÐ³ÑÐ°Ð½Ð¸ÑÐµÐ½Ð¸Ðµ Ð¿ÑÐµÐ´Ð¼ÐµÑÐ¾Ð² Ð´Ð»Ñ Ð¿ÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»Ñ
        if teacher:
            self.fields['subject'].queryset = Subject.objects.filter(teacher=teacher)


class ChangeLogFilterForm(forms.Form):
    """Ð¤Ð¾ÑÐ¼Ð° ÑÐ¸Ð»ÑÑÑÐ°ÑÐ¸Ð¸ Ð¸ÑÑÐ¾ÑÐ¸Ð¸ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹"""
    
    date_from = forms.DateField(
        required=False,
        label="Ð¡ Ð´Ð°ÑÑ",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        label="ÐÐ¾ Ð´Ð°ÑÑ",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    student = forms.ChoiceField(
        required=False,
        choices=[('', 'ÐÑÐµ ÑÑÑÐ´ÐµÐ½ÑÑ')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    teacher = forms.ChoiceField(
        required=False,
        choices=[('', 'ÐÑÐµ Ð¿ÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»Ð¸')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        group = kwargs.pop('group', None)
        subject = kwargs.pop('subject', None)
        super().__init__(*args, **kwargs)
        
        if group:
            from accounts.models import Student
            students = Student.objects.filter(group=group)
            self.fields['student'].choices = [('', 'ÐÑÐµ ÑÑÑÐ´ÐµÐ½ÑÑ')] + [
                (s.id, s.user.get_full_name()) for s in students
            ]
        
        if subject:
            from accounts.models import Teacher
            # â ÐÐ¡ÐÐ ÐÐÐÐÐÐ: Ð£ Teacher Ð½ÐµÑ Ð¿Ð¾Ð»Ñ subjects!
            # ÐÑÐ°Ð²Ð¸Ð»ÑÐ½Ð°Ñ Ð»Ð¾Ð³Ð¸ÐºÐ°: Subject.teacher - ÑÑÐ¾ ForeignKey
            # ÐÐ½Ð°ÑÐ¸Ñ, Ð½Ð°ÑÐ¾Ð´Ð¸Ð¼ Ð²ÑÐµÑ Ð¿ÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»ÐµÐ¹, Ñ ÐºÐ¾ÑÐ¾ÑÑÑ ÐµÑÑÑ ÑÐ¾ÑÑ Ð±Ñ Ð¾Ð´Ð¸Ð½ Ð¿ÑÐµÐ´Ð¼ÐµÑ = subject
            teachers = Teacher.objects.filter(subjects__id=subject.id).distinct()
            
            # ÐÐ»ÑÑÐµÑÐ½Ð°ÑÐ¸Ð²Ð½ÑÐ¹ Ð¿ÑÐ°Ð²Ð¸Ð»ÑÐ½ÑÐ¹ Ð²Ð°ÑÐ¸Ð°Ð½Ñ:
            # teachers = [subject.teacher] if subject.teacher else []
            
            self.fields['teacher'].choices = [('', 'ÐÑÐµ Ð¿ÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»Ð¸')] + [
                (t.id, t.user.get_full_name()) for t in teachers
            ]