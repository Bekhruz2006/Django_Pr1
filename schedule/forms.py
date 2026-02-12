from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import FieldError
from django.core.validators import FileExtensionValidator
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom, AcademicPlan, PlanDiscipline, SubjectTemplate
from accounts.models import Group, Teacher, Department, Specialty, Institute
from .models import SubjectMaterial
from .models import PlanDiscipline, AcademicPlan
from datetime import datetime
from .models import Classroom, Building


def get_year_choices():
    current_year = datetime.now().year
    return [(r, str(r)) for r in range(current_year - 5, current_year + 5)]

def get_academic_year_choices():
    current_year = datetime.now().year
    choices = []
    for r in range(current_year - 4, current_year + 4):
        val = f"{r}-{r+1}"
        choices.append((val, val))
    return choices




class SubjectForm(forms.ModelForm):
    total_credits_calc = forms.IntegerField(
        min_value=1, max_value=20, required=False,
        label=_("Авто-расчет по кредитам"),
        widget=forms.NumberInput(attrs={'class': 'form-control border-primary', 'id': 'id_total_credits_calc'})
    )

    assign_to_all_groups = forms.BooleanField(
        required=False,
        label=_("Назначить всем группам кафедры (создаст отдельные предметы)"),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Subject
        fields = ['name', 'teacher', 'description'] 
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

        try:
            if 'is_stream_subject' in Subject._meta.fields_map or \
               any(f.name == 'is_stream_subject' for f in Subject._meta.get_fields()):
                fields.append('is_stream_subject')
                widgets['is_stream_subject'] = forms.CheckboxInput(attrs={'class': 'form-check-input'})
        except Exception:
            pass 

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user and self.user.role == 'DEAN' and hasattr(self.user, 'dean_profile'):
            instance.faculty = self.user.dean_profile.faculty
        if commit:
            instance.save()
        return instance

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
            'room': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Номер кабинета')}),
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
            raise forms.ValidationError(_("Семестр не указан"))
        return cleaned_data

class SemesterForm(forms.ModelForm):
    department_filter = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        label=_("Выбрать кафедру (для фильтрации групп)"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    institute_filter = forms.ModelChoiceField(
        queryset=Institute.objects.all(),
        required=False,
        label=_("Фильтр по Институту"),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'institute_select'})
    )

    class Meta:
        model = Semester
        fields = ['academic_year', 'name', 'number', 'course', 'shift', 'start_date', 'end_date', 'is_active']
        widgets = {
            'academic_year': forms.Select(choices=[], attrs={'class': 'form-select'}),
            'groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Например: Осенний')}),
            'number': forms.Select(attrs={'class': 'form-select'}),
            'course': forms.Select(attrs={'class': 'form-select'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)
        
        if self.user and self.user.role == 'DEAN':
            self.fields.pop('institute_filter')
            if hasattr(self.user, 'dean_profile'):
                faculty = self.user.dean_profile.faculty
                self.fields['department_filter'].queryset = Department.objects.filter(faculty=faculty)
                self.fields['groups'].queryset = Group.objects.filter(specialty__department__faculty=faculty)
        
        else:
            pass

class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ['building', 'number', 'floor', 'capacity', 'is_active']
        widgets = {
            'building': forms.Select(attrs={'class': 'form-select'}),
            'number': forms.TextInput(attrs={'class': 'form-control'}),
            'floor': forms.NumberInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class BulkClassroomForm(forms.Form):
    floor = forms.IntegerField(label=_("Этаж"), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    start_number = forms.IntegerField(label=_("Начальный номер"), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    end_number = forms.IntegerField(label=_("Конечный номер"), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    capacity = forms.IntegerField(label=_("Вместимость"), initial=30, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_number')
        end = cleaned_data.get('end_number')
        if start and end and start >= end:
            raise forms.ValidationError(_('Конечный номер должен быть больше начального'))
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
    semester_start_date = forms.DateField(label=_("Дата начала семестра"), widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    current_week = forms.IntegerField(label=_("Текущая неделя"), min_value=1, max_value=20, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class SubjectTemplateForm(forms.ModelForm):
    class Meta:
        model = SubjectTemplate
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}


class AcademicPlanForm(forms.ModelForm):
    class Meta:
        model = AcademicPlan
        fields = ['specialty', 'group', 'admission_year', 'is_active']
        widgets = {
            'specialty': forms.Select(attrs={'class': 'form-select'}),
            'admission_year': forms.Select(choices=[], attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', *None)
        super().__init__(*args, *kwargs)
        
        self.fields['admission_year'].widget.choices = get_year_choices()
        if not self.instance.pk:
            self.fields['admission_year'].initial = datetime.now().year

        self.fields['group'].required = False
        self.fields['group'].empty_label = _("-- Общий план для всей специальности --")

        if user and user.role == 'DEAN' and hasattr(user, 'dean_profile'):
            faculty = user.dean_profile.faculty
            self.fields['specialty'].queryset = self.fields['specialty'].queryset.filter(
                department__faculty=faculty
            )
            self.fields['group'].queryset = self.fields['group'].queryset.filter(
                specialty__department__faculty=faculty
            )


class PlanDisciplineForm(forms.ModelForm):
    class Meta:
        model = PlanDiscipline
        fields = [
            'subject_template', 'semester_number', 'discipline_type',
            'credits', 'control_type',
            'lecture_hours', 'practice_hours', 'lab_hours', 'control_hours', 'independent_hours'
        ]
        widgets = {
            'subject_template': forms.Select(attrs={'class': 'form-select select2'}),
            'semester_number': forms.HiddenInput(), 
            'discipline_type': forms.Select(attrs={'class': 'form-select'}),
            'credits': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_credits'}),
            'control_type': forms.Select(attrs={'class': 'form-select'}),
            
            'lecture_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_lecture_hours'}),
            'practice_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_practice_hours'}),
            'lab_hours': forms.NumberInput(attrs={'class': 'form-control', 'value': 0}),
            'control_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_control_hours'}),
            'independent_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_independent_hours'}),
            'has_course_work': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lecture_hours'].required = False
        self.fields['practice_hours'].required = False
        self.fields['lab_hours'].required = False  
        self.fields['control_hours'].required = False
        self.fields['independent_hours'].required = False
        
        self.fields['lab_hours'].initial = 0
        super().__init__(*args, **kwargs)
        for field in ['lecture_hours', 'practice_hours', 'lab_hours', 'control_hours', 'independent_hours']:
            self.fields[field].required = False




class ScheduleImportForm(forms.Form):
    file = forms.FileField(
        label=_("Файл расписания (Excel или PDF)"),
        help_text=_("Поддерживаются .xlsx и .pdf (табличный вид)"),
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx, .xls, .pdf'}),
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'pdf'])]
    )
    
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.filter(is_active=True),
        label=_("Семестр"),
        empty_label=_("-- Выберите активный семестр --"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    default_group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label=_("Группа по умолчанию"),
        help_text=_("Выберите группу, если имя группы не удастся найти в файле автоматически."),
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class MaterialUploadForm(forms.ModelForm):
    class Meta:
        model = SubjectMaterial
        fields = ['title', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Например: Лекция 1. Введение')}),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }