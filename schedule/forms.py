from django import forms
from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom
from accounts.models import Group, Teacher


class SubjectForm(forms.ModelForm):
    total_credits_calc = forms.IntegerField(
        min_value=1, max_value=20, required=False,
        label="Авто-расчет по кредитам",
        help_text="Введите количество кредитов (напр. 6), чтобы заполнить часы автоматически",
        widget=forms.NumberInput(attrs={'class': 'form-control border-primary', 'id': 'id_total_credits_calc'})
    )

    assign_to_all_groups = forms.BooleanField(
        required=False,
        label="Назначить всем группам кафедры",
        help_text="Автоматически привяжет предмет ко всем группам, относящимся к кафедре преподавателя или выбранной кафедре.",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Subject
        fields = [
            'name', 'code', 'department', 'teacher', 'groups',
            'lecture_hours', 'practice_hours', 'control_hours',
            'independent_work_hours', 'semester_weeks'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8'}),
            'lecture_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_lecture_hours'}),
            'practice_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_practice_hours'}),
            'control_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_control_hours'}),
            'independent_work_hours': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_independent_work_hours'}),
            'semester_weeks': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_semester_weeks'}),
        }

    def clean_groups(self):
        groups = self.cleaned_data.get('groups')
        if groups and len(groups) > 3:
            raise forms.ValidationError("Максимальное количество групп для одного предмета (потока) — 3.")
        return groups

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.hours_per_semester = (
            (instance.lecture_hours or 0) +
            (instance.practice_hours or 0) +
            (instance.control_hours or 0) +
            (instance.independent_work_hours or 0)
        )
        instance.credits = round(instance.hours_per_semester / 24, 1)

        if commit:
            instance.save()
            self.save_m2m()

            if self.cleaned_data.get('assign_to_all_groups') and instance.department:
                dept_groups = Group.objects.filter(specialty__department=instance.department)
                instance.groups.add(*dept_groups)

        return instance


# Остальные формы оставляем без изменений, они рабочие
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
        fields = ['name', 'academic_year', 'number', 'course', 'shift', 'start_date', 'end_date', 'groups', 'is_active']
        widgets = {
            'groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'course' in self.data:
            try:
                course_val = int(self.data.get('course'))
                self.fields['groups'].queryset = Group.objects.filter(course=course_val)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk:
            self.fields['groups'].queryset = Group.objects.filter(course=self.instance.course)

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