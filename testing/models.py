from django.db import models
from lms.models import CourseWorkspace
from accounts.models import Student

class Quiz(models.Model):
    workspace = models.ForeignKey(CourseWorkspace, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=255, verbose_name="Название теста")
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(default=0, help_text="0 - без лимита")
    max_attempts = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=False)
    
    def __str__(self):
        return self.title

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(verbose_name="Текст вопроса")
    score = models.FloatField(default=1.0, verbose_name="Балл за вопрос")

    def __str__(self):
        return self.text[:50]

class AnswerOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255, verbose_name="Вариант ответа")
    is_correct = models.BooleanField(default=False)

class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)