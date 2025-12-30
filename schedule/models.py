from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Group, Teacher
from datetime import datetime, timedelta

class Subject(models.Model):

    TYPE_CHOICES = [
        ('LECTURE', 'Лекция'),
        ('PRACTICE', 'Практика'),
        ('SRSP', 'СРСП'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название предмета")
    code = models.CharField(max_length=20, unique=True, verbose_name="Код предмета")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Тип занятия")
    hours_per_semester = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Часов в семестр"
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subjects',
        verbose_name="Преподаватель"
    )
    description = models.TextField(blank=True, verbose_name="Описание")
    
    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

class AcademicWeek(models.Model):

    semester_start_date = models.DateField(verbose_name="Дата начала семестра")
    current_week = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        verbose_name="Текущая учебная неделя"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активный семестр")
    
    class Meta:
        verbose_name = "Учебная неделя"
        verbose_name_plural = "Учебные недели"
        ordering = ['-semester_start_date']
    
    def __str__(self):
        return f"Неделя {self.current_week} (с {self.semester_start_date})"
    
    def calculate_current_week(self):
        
        today = datetime.now().date()
        delta = today - self.semester_start_date
        week = (delta.days // 7) + 1
        return max(1, min(week, 20))
    
    def save(self, *args, **kwargs):
        
        if self.is_active:
            AcademicWeek.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_current(cls):
        
        return cls.objects.filter(is_active=True).first()

class ScheduleSlot(models.Model):

    DAY_CHOICES = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
    ]
    
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='schedule_slots',
        verbose_name="Группа"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='schedule_slots',
        verbose_name="Предмет"
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='schedule_slots',
        verbose_name="Преподаватель"
    )
    
    day_of_week = models.IntegerField(choices=DAY_CHOICES, verbose_name="День недели")
    start_time = models.TimeField(verbose_name="Время начала")
    end_time = models.TimeField(verbose_name="Время окончания")
    
    classroom = models.CharField(max_length=50, verbose_name="Аудитория")
    
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Слот расписания"
        verbose_name_plural = "Слоты расписания"
        ordering = ['day_of_week', 'start_time']
    
    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.start_time}-{self.end_time}: {self.subject.name} ({self.group.name})"
    
    def get_color_class(self):
        
        colors = {
            'LECTURE': 'primary',
            'PRACTICE': 'success',
            'SRSP': 'warning'
        }
        return colors.get(self.subject.type, 'secondary')

class ScheduleException(models.Model):

    TYPE_CHOICES = [
        ('CANCEL', 'Отмена'),
        ('RESCHEDULE', 'Перенос'),
    ]
    
    schedule_slot = models.ForeignKey(
        ScheduleSlot,
        on_delete=models.CASCADE,
        related_name='exceptions',
        verbose_name="Слот расписания"
    )
    
    exception_date = models.DateField(verbose_name="Дата исключения")
    exception_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Тип исключения"
    )
    reason = models.TextField(verbose_name="Причина")

    new_date = models.DateField(null=True, blank=True, verbose_name="Новая дата")
    new_start_time = models.TimeField(null=True, blank=True, verbose_name="Новое время начала")
    new_end_time = models.TimeField(null=True, blank=True, verbose_name="Новое время окончания")
    new_classroom = models.CharField(max_length=50, blank=True, verbose_name="Новая аудитория")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Создал"
    )
    
    class Meta:
        verbose_name = "Исключение в расписании"
        verbose_name_plural = "Исключения в расписании"
        ordering = ['-exception_date']
        unique_together = ['schedule_slot', 'exception_date']
    
    def __str__(self):
        return f"{self.get_exception_type_display()}: {self.schedule_slot} на {self.exception_date}"