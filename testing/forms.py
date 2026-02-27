from django import forms
from django.forms import inlineformset_factory
from .models import Quiz, Question, AnswerOption

class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields =['description', 'time_limit_minutes', 'max_attempts', 'passing_score', 'shuffle_questions']
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'time_limit_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_attempts': forms.NumberInput(attrs={'class': 'form-control'}),
            'passing_score': forms.NumberInput(attrs={'class': 'form-control'}),
            'shuffle_questions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields =['text', 'q_type', 'default_mark']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Текст вопроса'}),
            'q_type': forms.Select(attrs={'class': 'form-select'}),
            'default_mark': forms.NumberInput(attrs={'class': 'form-control'}),
        }

AnswerOptionFormSet = inlineformset_factory(
    Question, AnswerOption,
    fields=['text', 'fraction'],
    extra=4, can_delete=True,
    widgets={
        'text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Вариант ответа'}),
        'fraction': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'placeholder': '1.0 (верно) / 0.0 (неверно)'}),
    }
)