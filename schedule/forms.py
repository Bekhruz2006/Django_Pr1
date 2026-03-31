from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import FieldError
from django.core.validators import FileExtensionValidator
from .models import Subject, ScheduleSlot, ScheduleException, Classroom, CreditType, CreditTemplate, AcademicPlan, PlanDiscipline, SubjectTemplate, TimeSlot
from accounts.models import Group, Teacher, Department, Specialty, Institute
from .models import SubjectMaterial
from .models import PlanDiscipline, AcademicPlan
from datetime import datetime
from .models import Classroom, Building, Institute, Department, Group, ROOM_TYPES
from django.db.models import Q

def get_year_choices():
    current_year = datetime.now().year
    return [(r, str(r)) for r in range(current_year - 5, current_year + 5)]

def get_academic_year_choices():
    current_year = datetime.now().year
    choices = []
    for r in range(current_year - 5, current_year + 6):
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
        fields =[
            'name', 'code', 'department', 'semester_weeks', 'type',
            'credit_type', 'credits',
            'lecture_hours', 'practice_hours', 'lab_hours', 'control_hours', 'independent_work_hours',
            'teacher', 'groups', 'description', 'is_stream_subject', 'preferred_room_type', 'required_competencies'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'credit_type': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'groups': forms.SelectMultiple(attrs={'class': 'form-select select2-multiple'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'preferred_room_type': forms.Select(attrs={'class': 'form-select'}),
            'required_competencies': forms.SelectMultiple(attrs={'class': 'form-select select2-multiple'}),
            'is_stream_subject': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


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

class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ['building', 'number', 'floor', 'capacity', 'room_type', 'is_active']
        widgets = {
            'building': forms.Select(attrs={'class': 'form-select'}),
            'number': forms.TextInput(attrs={'class': 'form-control'}),
            'floor': forms.NumberInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and user.role == 'DEAN' and hasattr(user, 'dean_profile'):
            faculty = user.dean_profile.faculty
            if faculty and faculty.institute:
                self.fields['building'].queryset = Building.objects.filter(institute=faculty.institute)


class BulkClassroomForm(forms.Form):
    building = forms.ModelChoiceField(
        queryset=Building.objects.all(),
        label=_("Учебный корпус"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    floor = forms.IntegerField(label=_("Этаж"), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    start_number = forms.IntegerField(label=_("Начальный номер"), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    end_number = forms.IntegerField(label=_("Конечный номер"), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    capacity = forms.IntegerField(label=_("Вместимость"), initial=30, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    room_type = forms.ChoiceField(
        choices= ROOM_TYPES,
        initial='PRACTICE',
        label=_("Тип кабинетов"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and hasattr(user, 'dean_profile'):
            faculty = user.dean_profile.faculty
            if faculty and faculty.institute:
                self.fields['building'].queryset = Building.objects.filter(institute=faculty.institute)

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


class SubjectTemplateForm(forms.ModelForm):
    class Meta:
        model = SubjectTemplate
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}

class AcademicPlanForm(forms.ModelForm):
    class Meta:
        model = AcademicPlan
        fields = ['group', 'admission_year', 'is_active']
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select select2'}),
            'admission_year': forms.Select(choices=[], attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['admission_year'].widget.choices = get_year_choices()
        if not self.instance.pk:
            self.fields['admission_year'].initial = datetime.now().year
        self.fields['group'].required = True
        if user and hasattr(user, 'dean_profile'):
            faculty = user.dean_profile.faculty
            qs = Group.objects.filter(specialty__department__faculty=faculty, academic_plan__isnull=True)
        else:
            qs = Group.objects.filter(academic_plan__isnull=True)
        if self.instance.pk and self.instance.group_id:
            qs = (qs | Group.objects.filter(pk=self.instance.group_id)).distinct()
        self.fields['group'].queryset = qs

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.group_id and getattr(instance.group, 'specialty_id', None):
            instance.specialty_id = instance.group.specialty_id
        if commit:
            instance.save()
        return instance

class PlanDisciplineForm(forms.ModelForm):
    class Meta:
        model = PlanDiscipline
        fields =[
            'subject_template', 'semester_number', 'cycle', 'discipline_type',
            'credit_type', 'credits', 'control_type',
            'lecture_hours', 'practice_hours', 'lab_hours', 'control_hours', 'independent_hours',
            'has_course_work', 'has_subgroups', 'preferred_room_type'
        ]
        widgets = {
            'subject_template': forms.Select(attrs={'class': 'form-select select2'}),
            'semester_number': forms.HiddenInput(),
            'cycle': forms.Select(attrs={'class': 'form-select'}),
            'discipline_type': forms.Select(attrs={'class': 'form-select'}),
            'credit_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_credit_type'}),
            'credits': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_credits'}),
            'control_type': forms.Select(attrs={'class': 'form-select'}),
            'lecture_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_lecture_hours'}),
            'practice_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_practice_hours'}),
            'lab_hours': forms.NumberInput(attrs={'class': 'form-control', 'value': 0}),
            'control_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_control_hours'}),
            'independent_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_independent_hours'}),
            'has_course_work': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_subgroups': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'preferred_room_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop('faculty', None)
        
        super().__init__(*args, **kwargs)
        
        for field in['lecture_hours', 'practice_hours', 'lab_hours', 'control_hours', 'independent_hours']:
            self.fields[field].required = False
        self.fields['lab_hours'].initial = 0
        
        if faculty:
            self.fields['credit_type'].queryset = CreditType.objects.filter(
                Q(faculty=faculty) | Q(faculty__isnull=True)
            )
        else:
            self.fields['credit_type'].queryset = CreditType.objects.filter(faculty__isnull=True)


class ScheduleImportForm(forms.Form):
    file = forms.FileField(
        label=_("Файл расписания (Excel)"),
        help_text=_("Поддерживаются только .xlsx и .xls"),
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx, .xls'}),
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
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

class TimeSlotForm(forms.ModelForm):
    class Meta:
        model = TimeSlot
        fields = ['institute', 'shift', 'number', 'start_time', 'end_time', 'duration']
        widgets = {
            'institute': forms.Select(attrs={'class': 'form-select'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'number': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    enable_two_week_mode = forms.BooleanField(
        label=_("Включить двухнедельный режим (Красная/Синяя неделя)"),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class RupImportForm(forms.Form):
    file = forms.FileField(
        label=_("Файл РУП (Excel)"),
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx, .xls'})
    )





class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ['name', 'address', 'institute']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Например: Главный корпус')}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Адрес (необязательно)')}),
            'institute': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and hasattr(user, 'dean_profile'):
            faculty = user.dean_profile.faculty
            if faculty and faculty.institute:
                self.fields['institute'].initial = faculty.institute
                self.fields['institute'].widget.attrs['readonly'] = True
                self.fields['institute'].queryset = Institute.objects.filter(id=faculty.institute.id)


class CreditTemplateForm(forms.ModelForm):
    class Meta:
        model = CreditTemplate
        fields = ['credits', 'lecture_pairs', 'practice_pairs', 'lab_pairs', 'srsp_pairs']
        widgets = {
            'credits': forms.NumberInput(attrs={'class': 'form-control fw-bold text-primary'}),
            'lecture_pairs': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'practice_pairs': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'lab_pairs': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'srsp_pairs': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
        }





