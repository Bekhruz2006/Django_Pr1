from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Course, CourseCategory, CourseSection, CourseModule,
    Assignment, AssignmentSubmission, Forum, ForumThread, ForumPost,
    GlossaryEntry, CourseEnrolment, GradeEntry, GradeItem,
    PageContent, FileResource, FolderFile, UrlResource, VideoResource,
)
from accounts.models import Group, User
from schedule.models import Subject


class CourseCategoryForm(forms.ModelForm):
    class Meta:
        model  = CourseCategory
        fields = ['name', 'description', 'parent', 'institute', 'faculty', 'department', 'sort_order']
        widgets = {f: forms.TextInput(attrs={'class': 'form-control'}) for f in ['name', 'sort_order']}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if not f.widget.attrs.get('class'):
                if isinstance(f.widget, forms.Textarea):
                    f.widget.attrs.update({'class': 'form-control', 'rows': 2})
                else:
                    f.widget.attrs['class'] = 'form-select'


class CourseForm(forms.ModelForm):
    class Meta:
        model  = Course
        fields = [
            'category', 'full_name', 'short_name', 'id_number', 'summary', 'image',
            'visibility', 'format', 'is_visible', 'start_date', 'end_date',
            'allow_self_enrol', 'enrol_key',
            'allowed_faculty', 'allowed_department', 'allowed_group',
        ]
        widgets = {
            'full_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'short_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'id_number':   forms.TextInput(attrs={'class': 'form-control'}),
            'summary':     forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'image':       forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'visibility':  forms.Select(attrs={'class': 'form-select'}),
            'format':      forms.Select(attrs={'class': 'form-select'}),
            'start_date':  forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date':    forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'enrol_key':   forms.TextInput(attrs={'class': 'form-control'}),
            'category':           forms.Select(attrs={'class': 'form-select'}),
            'allowed_faculty':    forms.Select(attrs={'class': 'form-select'}),
            'allowed_department': forms.Select(attrs={'class': 'form-select'}),
            'allowed_group':      forms.Select(attrs={'class': 'form-select'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if not f.widget.attrs.get('class'):
                if isinstance(f.widget, forms.Textarea):
                    f.widget.attrs.update({'class': 'form-control', 'rows': 2})
                elif isinstance(f.widget, forms.CheckboxInput):
                    f.widget.attrs.update({'class': 'form-check-input'}) 
                elif isinstance(f.widget, (forms.Select, forms.SelectMultiple)):
                    f.widget.attrs.update({'class': 'form-select'})
                else:
                    f.widget.attrs.update({'class': 'form-control'})

        subjects = Subject.objects.select_related('department').all().order_by('name')
        choices =[('', '--- Не привязан к расписанию (Самостоятельный курс) ---')]
        for sub in subjects:
            choices.append((sub.code, f"{sub.name} ({sub.get_type_display()}) - {sub.department.name}"))

        self.fields['id_number'].widget = forms.Select(choices=choices, attrs={'class': 'form-select border-primary'})
        self.fields['id_number'].label = "Связь с предметом расписания"
        self.fields['id_number'].help_text = "Выберите предмет, чтобы кнопка 'Сгенерировать структуру из расписания' работала без ошибок."


class CourseSectionForm(forms.ModelForm):
    class Meta:
        model  = CourseSection
        fields = ['name', 'summary', 'sequence', 'is_visible']
        widgets = {
            'name':     forms.TextInput(attrs={'class': 'form-control'}),
            'summary':  forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'sequence': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class CourseModuleForm(forms.ModelForm):
    class Meta:
        model  = CourseModule
        fields = ['title', 'description', 'module_type', 'sequence', 'is_visible',
                  'completion_required', 'available_from', 'available_until', 'depends_on']
        widgets = {
            'title':           forms.TextInput(attrs={'class': 'form-control'}),
            'description':     forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'module_type':     forms.Select(attrs={'class': 'form-select'}),
            'sequence':        forms.NumberInput(attrs={'class': 'form-control'}),
            'available_from':  forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'available_until': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'depends_on':      forms.Select(attrs={'class': 'form-select'}),
        }


class PageContentForm(forms.ModelForm):
    class Meta:
        model  = PageContent
        fields = ['content']
        widgets = {'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 20, 'id': 'richtext'})}


class FileResourceForm(forms.ModelForm):
    class Meta:
        model  = FileResource
        fields = ['file', 'display_type']
        widgets = {
            'file':         forms.FileInput(attrs={'class': 'form-control'}),
            'display_type': forms.Select(attrs={'class': 'form-select'}),
        }


class FolderFileForm(forms.ModelForm):
    class Meta:
        model  = FolderFile
        fields = ['name', 'file', 'sort_order']
        widgets = {
            'name':       forms.TextInput(attrs={'class': 'form-control'}),
            'file':       forms.FileInput(attrs={'class': 'form-control'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class UrlResourceForm(forms.ModelForm):
    class Meta:
        model  = UrlResource
        fields = ['external_url', 'open_in_new_tab']
        widgets = {'external_url': forms.URLInput(attrs={'class': 'form-control'})}


class VideoResourceForm(forms.ModelForm):
    class Meta:
        model  = VideoResource
        fields = ['embed_url', 'file']
        widgets = {
            'embed_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.youtube.com/embed/...'}),
            'file':      forms.FileInput(attrs={'class': 'form-control'}),
        }


class AssignmentForm(forms.ModelForm):
    class Meta:
        model  = Assignment
        fields = ['description', 'due_date', 'max_score', 'submission_type',
                  'max_file_size_mb', 'allowed_file_types', 'allow_late_submission']
        widgets = {
            'description':      forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'due_date':         forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'max_score':        forms.NumberInput(attrs={'class': 'form-control'}),
            'submission_type':  forms.Select(attrs={'class': 'form-select'}),
            'max_file_size_mb': forms.NumberInput(attrs={'class': 'form-control'}),
            'allowed_file_types': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'pdf,doc,docx'}),
        }


class SubmissionForm(forms.ModelForm):
    class Meta:
        model  = AssignmentSubmission
        fields = ['file', 'text_answer']
        widgets = {
            'file':        forms.FileInput(attrs={'class': 'form-control'}),
            'text_answer': forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
        }


class GradeSubmissionForm(forms.Form):
    score    = forms.FloatField(label=_('Оценка'), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    feedback = forms.CharField(label=_('Комментарий'), required=False,
                               widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    action   = forms.ChoiceField(
        choices=[('GRADED', _('Принять')), ('RETURNED', _('Вернуть на доработку'))],
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ForumThreadForm(forms.ModelForm):
    class Meta:
        model  = ForumThread
        fields = ['title']
        widgets = {'title': forms.TextInput(attrs={'class': 'form-control'})}


class ForumPostForm(forms.ModelForm):
    class Meta:
        model  = ForumPost
        fields = ['body']
        widgets = {'body': forms.Textarea(attrs={'class': 'form-control', 'rows': 5})}


class GlossaryEntryForm(forms.ModelForm):
    class Meta:
        model  = GlossaryEntry
        fields = ['concept', 'definition']
        widgets = {
            'concept':    forms.TextInput(attrs={'class': 'form-control'}),
            'definition': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class EnrolUsersForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label=_('Выберите группы (Студенты)'),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-multiple', 'size': '5'})
    )
    teachers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(role='TEACHER'),
        required=False,
        label=_('Выберите преподавателей'),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-multiple', 'size': '5'})
    )



class GradeItemForm(forms.ModelForm):
    class Meta:
        model  = GradeItem
        fields = ['name', 'item_type', 'max_score', 'weight', 'sort_order']
        widgets = {
            'name':       forms.TextInput(attrs={'class': 'form-control'}),
            'item_type':  forms.Select(attrs={'class': 'form-select'}),
            'max_score':  forms.NumberInput(attrs={'class': 'form-control'}),
            'weight':     forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class GradeEntryForm(forms.ModelForm):
    class Meta:
        model  = GradeEntry
        fields = ['score', 'feedback', 'is_excluded']
        widgets = {
            'score':    forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }