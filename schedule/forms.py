from django import forms
from django.core.exceptions import FieldError
from django.core.validators import FileExtensionValidator
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom, AcademicPlan, PlanDiscipline, SubjectTemplate
from accounts.models import Group, Teacher, Department

class SubjectForm(forms.ModelForm):
    total_credits_calc = forms.IntegerField(
        min_value=1, max_value=20, required=False,
        label="Авто-расчет по кредитам",
        widget=forms.NumberInput(attrs={'class': 'form-control border-primary', 'id': 'id_total_credits_calc'})
    )

    assign_to_all_groups = forms.BooleanField(
        required=False,
        label="Назначить всем группам кафедры (создаст отдельные предметы)",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Subject
        fields = ['name', 'teacher', 'description'] # Убрали часы, коды и прочий шум
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
        
        instance.hours_per_semester = (
            (instance.lecture_hours or 0) +
            (instance.practice_hours or 0) +
            (instance.control_hours or 0) +
            (instance.independent_work_hours or 0)
        )
        instance.credits = round(instance.hours_per_semester / 24, 1)

        manual_groups = self.cleaned_data.get('groups')
        assign_all = self.cleaned_data.get('assign_to_all_groups')

        if assign_all:
            instance.is_stream_subject = False
        elif manual_groups and manual_groups.count() > 1:
            instance.is_stream_subject = True
        else:
            instance.is_stream_subject = False

        if commit:
            instance.save()
            self.save_m2m()  
            if assign_all and instance.department:
                dept_groups = Group.objects.filter(specialty__department=instance.department)
                instance.groups.add(*dept_groups)
                instance.is_stream_subject = False
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
    department_filter = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        label="Выбрать кафедру (для фильтрации групп)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Semester
        fields = ['name', 'academic_year', 'number', 'course', 'shift', 'start_date', 'end_date', 'groups', 'is_active']
        widgets = {
            'groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control'}),
            'number': forms.Select(attrs={'class': 'form-select'}),
            'course': forms.Select(attrs={'class': 'form-select'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role == 'DEAN' and hasattr(user, 'dean_profile'):
            faculty = user.dean_profile.faculty
            self.fields['department_filter'].queryset = Department.objects.filter(faculty=faculty)
            self.fields['groups'].queryset = Group.objects.filter(specialty__department__faculty=faculty)

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
    floor = forms.IntegerField(label="Этаж", widget=forms.NumberInput(attrs={'class': 'form-control'}))
    start_number = forms.IntegerField(label="Начальный номер", widget=forms.NumberInput(attrs={'class': 'form-control'}))
    end_number = forms.IntegerField(label="Конечный номер", widget=forms.NumberInput(attrs={'class': 'form-control'}))
    capacity = forms.IntegerField(label="Вместимость", initial=30, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    
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
    semester_start_date = forms.DateField(label="Дата начала семестра", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    current_week = forms.IntegerField(label="Текущая неделя", min_value=1, max_value=20, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class SubjectTemplateForm(forms.ModelForm):
    class Meta:
        model = SubjectTemplate
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}


class AcademicPlanForm(forms.ModelForm):
    class Meta:
        model = AcademicPlan
        fields = ['specialty', 'admission_year', 'is_active']
        widgets = {
            'specialty': forms.Select(attrs={'class': 'form-select'}),
            'admission_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '2025'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role == 'DEAN' and hasattr(user, 'dean_profile'):
            self.fields['specialty'].queryset = Specialty.objects.filter(
                department__faculty=user.dean_profile.faculty
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
            'semester_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'discipline_type': forms.Select(attrs={'class': 'form-select'}),
            'credits': forms.NumberInput(attrs={'class': 'form-control'}),
            'control_type': forms.Select(attrs={'class': 'form-select'}),
            
            'lecture_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'practice_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'lab_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'control_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'independent_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
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



class ScheduleImportForm(forms.Form):
    file = forms.FileField(
        label="Файл расписания (Excel или PDF)",
        help_text="Поддерживаются .xlsx и .pdf (табличный вид)",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx, .xls, .pdf'}),
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'pdf'])]
    )
    
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.filter(is_active=True),
        label="Семестр",
        empty_label="-- Выберите активный семестр --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    default_group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label="Группа по умолчанию",
        help_text="Выберите группу, если имя группы не удастся найти в файле автоматически.",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    