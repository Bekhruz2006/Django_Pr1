from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from accounts.models import User, Group, Teacher
# â ÐÐ¡ÐÐ ÐÐÐÐÐÐ: Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½ Ð¿ÑÐ°Ð²Ð¸Ð»ÑÐ½ÑÐ¹ Ð¸Ð¼Ð¿Ð¾ÑÑ datetime
from datetime import datetime, timedelta

class Subject(models.Model):
    """ÐÑÐµÐ´Ð¼ÐµÑ/Ð´Ð¸ÑÑÐ¸Ð¿Ð»Ð¸Ð½Ð°"""
    
    TYPE_CHOICES = [
        ('LECTURE', 'ÐÐµÐºÑÐ¸Ñ'),
        ('PRACTICE', 'ÐÑÐ°ÐºÑÐ¸ÐºÐ°'),
        ('SRSP', 'Ð¡Ð Ð¡Ð'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="ÐÐ°Ð·Ð²Ð°Ð½Ð¸Ðµ Ð¿ÑÐµÐ´Ð¼ÐµÑÐ°")
    code = models.CharField(max_length=20, unique=True, verbose_name="ÐÐ¾Ð´ Ð¿ÑÐµÐ´Ð¼ÐµÑÐ°")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Ð¢Ð¸Ð¿ Ð·Ð°Ð½ÑÑÐ¸Ñ")
    hours_per_semester = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Ð§Ð°ÑÐ¾Ð² Ð² ÑÐµÐ¼ÐµÑÑÑ"
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subjects',
        verbose_name="ÐÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»Ñ"
    )
    description = models.TextField(blank=True, verbose_name="ÐÐ¿Ð¸ÑÐ°Ð½Ð¸Ðµ")
    
    class Meta:
        verbose_name = "ÐÑÐµÐ´Ð¼ÐµÑ"
        verbose_name_plural = "ÐÑÐµÐ´Ð¼ÐµÑÑ"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class AcademicWeek(models.Model):
    """Ð£Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÑÐµÐ±Ð½ÑÐ¼Ð¸ Ð½ÐµÐ´ÐµÐ»ÑÐ¼Ð¸"""
    
    semester_start_date = models.DateField(verbose_name="ÐÐ°ÑÐ° Ð½Ð°ÑÐ°Ð»Ð° ÑÐµÐ¼ÐµÑÑÑÐ°")
    current_week = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        verbose_name="Ð¢ÐµÐºÑÑÐ°Ñ ÑÑÐµÐ±Ð½Ð°Ñ Ð½ÐµÐ´ÐµÐ»Ñ"
    )
    is_active = models.BooleanField(default=True, verbose_name="ÐÐºÑÐ¸Ð²Ð½ÑÐ¹ ÑÐµÐ¼ÐµÑÑÑ")
    
    class Meta:
        verbose_name = "Ð£ÑÐµÐ±Ð½Ð°Ñ Ð½ÐµÐ´ÐµÐ»Ñ"
        verbose_name_plural = "Ð£ÑÐµÐ±Ð½ÑÐµ Ð½ÐµÐ´ÐµÐ»Ð¸"
        ordering = ['-semester_start_date']
    
    def __str__(self):
        return f"ÐÐµÐ´ÐµÐ»Ñ {self.current_week} (Ñ {self.semester_start_date})"
    
    def calculate_current_week(self):
        """ÐÐ²ÑÐ¾Ð¼Ð°ÑÐ¸ÑÐµÑÐºÐ¸Ð¹ ÑÐ°ÑÑÐµÑ ÑÐµÐºÑÑÐµÐ¹ Ð½ÐµÐ´ÐµÐ»Ð¸"""
        # â ÐÐ¡ÐÐ ÐÐÐÐÐÐ: Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐµÐ¼ timezone.now() Ð´Ð»Ñ ÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ð¹ ÑÐ°Ð±Ð¾ÑÑ Ñ timezone-aware datetime
        today = timezone.now().date()
        delta = today - self.semester_start_date
        week = (delta.days // 7) + 1
        return max(1, min(week, 20))
    
    def save(self, *args, **kwargs):
        # ÐÐµÐ°ÐºÑÐ¸Ð²Ð¸ÑÐ¾Ð²Ð°ÑÑ Ð´ÑÑÐ³Ð¸Ðµ Ð°ÐºÑÐ¸Ð²Ð½ÑÐµ ÑÐµÐ¼ÐµÑÑÑÑ
        if self.is_active:
            AcademicWeek.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_current(cls):
        """ÐÐ¾Ð»ÑÑÐ¸ÑÑ ÑÐµÐºÑÑÐ¸Ð¹ Ð°ÐºÑÐ¸Ð²Ð½ÑÐ¹ ÑÐµÐ¼ÐµÑÑÑ"""
        return cls.objects.filter(is_active=True).first()


class ScheduleSlot(models.Model):
    """Ð¡Ð»Ð¾Ñ ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ñ (Ð¿Ð¾Ð²ÑÐ¾ÑÑÑÑÐµÐµÑÑ Ð·Ð°Ð½ÑÑÐ¸Ðµ)"""
    
    DAY_CHOICES = [
        (0, 'ÐÐ¾Ð½ÐµÐ´ÐµÐ»ÑÐ½Ð¸Ðº'),
        (1, 'ÐÑÐ¾ÑÐ½Ð¸Ðº'),
        (2, 'Ð¡ÑÐµÐ´Ð°'),
        (3, 'Ð§ÐµÑÐ²ÐµÑÐ³'),
        (4, 'ÐÑÑÐ½Ð¸ÑÐ°'),
        (5, 'Ð¡ÑÐ±Ð±Ð¾ÑÐ°'),
    ]
    
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='schedule_slots',
        verbose_name="ÐÑÑÐ¿Ð¿Ð°"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='schedule_slots',
        verbose_name="ÐÑÐµÐ´Ð¼ÐµÑ"
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='schedule_slots',
        verbose_name="ÐÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»Ñ"
    )
    
    day_of_week = models.IntegerField(choices=DAY_CHOICES, verbose_name="ÐÐµÐ½Ñ Ð½ÐµÐ´ÐµÐ»Ð¸")
    start_time = models.TimeField(verbose_name="ÐÑÐµÐ¼Ñ Ð½Ð°ÑÐ°Ð»Ð°")
    end_time = models.TimeField(verbose_name="ÐÑÐµÐ¼Ñ Ð¾ÐºÐ¾Ð½ÑÐ°Ð½Ð¸Ñ")
    
    classroom = models.CharField(max_length=50, verbose_name="ÐÑÐ´Ð¸ÑÐ¾ÑÐ¸Ñ")
    
    is_active = models.BooleanField(default=True, verbose_name="ÐÐºÑÐ¸Ð²Ð½Ð¾")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Ð¡Ð»Ð¾Ñ ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ñ"
        verbose_name_plural = "Ð¡Ð»Ð¾ÑÑ ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ñ"
        ordering = ['day_of_week', 'start_time']
    
    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.start_time}-{self.end_time}: {self.subject.name} ({self.group.name})"
    
    def get_color_class(self):
        """Ð¦Ð²ÐµÑ Ð´Ð»Ñ ÑÐ¸Ð¿Ð° Ð·Ð°Ð½ÑÑÐ¸Ñ"""
        colors = {
            'LECTURE': 'primary',
            'PRACTICE': 'success',
            'SRSP': 'warning'
        }
        return colors.get(self.subject.type, 'secondary')


class ScheduleException(models.Model):
    """ÐÑÐºÐ»ÑÑÐµÐ½Ð¸Ðµ Ð² ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ð¸ (Ð¾ÑÐ¼ÐµÐ½Ð°/Ð¿ÐµÑÐµÐ½Ð¾Ñ)"""
    
    TYPE_CHOICES = [
        ('CANCEL', 'ÐÑÐ¼ÐµÐ½Ð°'),
        ('RESCHEDULE', 'ÐÐµÑÐµÐ½Ð¾Ñ'),
    ]
    
    schedule_slot = models.ForeignKey(
        ScheduleSlot,
        on_delete=models.CASCADE,
        related_name='exceptions',
        verbose_name="Ð¡Ð»Ð¾Ñ ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ñ"
    )
    
    exception_date = models.DateField(verbose_name="ÐÐ°ÑÐ° Ð¸ÑÐºÐ»ÑÑÐµÐ½Ð¸Ñ")
    exception_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Ð¢Ð¸Ð¿ Ð¸ÑÐºÐ»ÑÑÐµÐ½Ð¸Ñ"
    )
    reason = models.TextField(verbose_name="ÐÑÐ¸ÑÐ¸Ð½Ð°")
    
    # ÐÐ¾Ð»Ñ Ð´Ð»Ñ Ð¿ÐµÑÐµÐ½Ð¾ÑÐ°
    new_date = models.DateField(null=True, blank=True, verbose_name="ÐÐ¾Ð²Ð°Ñ Ð´Ð°ÑÐ°")
    new_start_time = models.TimeField(null=True, blank=True, verbose_name="ÐÐ¾Ð²Ð¾Ðµ Ð²ÑÐµÐ¼Ñ Ð½Ð°ÑÐ°Ð»Ð°")
    new_end_time = models.TimeField(null=True, blank=True, verbose_name="ÐÐ¾Ð²Ð¾Ðµ Ð²ÑÐµÐ¼Ñ Ð¾ÐºÐ¾Ð½ÑÐ°Ð½Ð¸Ñ")
    new_classroom = models.CharField(max_length=50, blank=True, verbose_name="ÐÐ¾Ð²Ð°Ñ Ð°ÑÐ´Ð¸ÑÐ¾ÑÐ¸Ñ")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Ð¡Ð¾Ð·Ð´Ð°Ð»"
    )
    
    class Meta:
        verbose_name = "ÐÑÐºÐ»ÑÑÐµÐ½Ð¸Ðµ Ð² ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ð¸"
        verbose_name_plural = "ÐÑÐºÐ»ÑÑÐµÐ½Ð¸Ñ Ð² ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ð¸"
        ordering = ['-exception_date']
        unique_together = ['schedule_slot', 'exception_date']
    
    def __str__(self):
        return f"{self.get_exception_type_display()}: {self.schedule_slot} Ð½Ð° {self.exception_date}"