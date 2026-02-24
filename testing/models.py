from django.db import models
from lms.models import CourseModule
from accounts.models import User

class Quiz(models.Model):
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='quiz_detail')
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(default=0, help_text="0 - без лимита")
    max_attempts = models.PositiveIntegerField(default=1)
    passing_score = models.FloatField(default=50.0, verbose_name="Проходной балл")
    shuffle_questions = models.BooleanField(default=True)
    
    time_open = models.DateTimeField(null=True, blank=True)
    time_close = models.DateTimeField(null=True, blank=True)

class Question(models.Model):
    QUESTION_TYPES = [
        ('SINGLE', 'Один правильный ответ'),
        ('MULTI', 'Несколько правильных ответов'),
        ('TEXT', 'Короткий текстовый ответ'),
        ('ESSAY', 'Эссе (Ручная проверка)'),
        ('MATCHING', 'Установление соответствия'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    q_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='SINGLE')
    text = models.TextField(verbose_name="Текст вопроса")
    default_mark = models.FloatField(default=1.0, verbose_name="Балл за вопрос")
    penalty = models.FloatField(default=0.0, verbose_name="Штраф за ошибку")

class AnswerOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.TextField(verbose_name="Вариант ответа / Текст для проверки")
    fraction = models.FloatField(default=0.0, help_text="Вес ответа: 1.0 (100%), 0.5 (50%), 0.0 (неверно)")

class QuizAttempt(models.Model):
    STATE_CHOICES = [
        ('IN_PROGRESS', 'В процессе'),
        ('FINISHED', 'Завершен'),
        ('NEEDS_GRADING', 'Требует ручной проверки (Эссе)'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='IN_PROGRESS')
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    total_score = models.FloatField(null=True, blank=True)
    is_passed = models.BooleanField(default=False)

class AttemptResponse(models.Model):
    """Ответ студента на конкретный вопрос в рамках попытки"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_options = models.ManyToManyField(AnswerOption, blank=True)
    text_answer = models.TextField(blank=True, verbose_name="Текст ответа (для TEXT/ESSAY)")
    earned_mark = models.FloatField(default=0.0)