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
    credits = models.IntegerField(
        validators=[MinValueValidator(3)],
        verbose_name="Кредиты (часы в неделю)"
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
        return f"{self.name}"
    
    def get_credits_distribution(self):
        credits_per_type = self.credits // 3
        return {
            'LECTURE': credits_per_type,
            'PRACTICE': credits_per_type,
            'SRSP': credits_per_type
        }

class Classroom(models.Model):
    number = models.CharField(max_length=10, unique=True, verbose_name="Номер кабинета")
    floor = models.IntegerField(verbose_name="Этаж")
    capacity = models.IntegerField(default=30, verbose_name="Вместимость")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    
    class Meta:
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"
        ordering = ['floor', 'number']
    
    def __str__(self):
        return f"{self.number} ({self.floor} этаж)"

class Semester(models.Model):
    SHIFT_CHOICES = [
        ('MORNING', 'Утреннее (08:00-12:50)'),
        ('AFTERNOON', 'Дневное (13:00-18:50)'),
    ]
    
    name = models.CharField(max_length=50, verbose_name="Название семестра")
    number = models.IntegerField(
        choices=[(1, '1 семестр'), (2, '2 семестр')],
        verbose_name="Номер семестра"
    )
    shift = models.CharField(
        max_length=10,
        choices=SHIFT_CHOICES,
        default='AFTERNOON',
        verbose_name="Смена"
    )
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата окончания")
    is_active = models.BooleanField(default=False, verbose_name="Активный семестр")
    
    class Meta:
        verbose_name = "Семестр"
        verbose_name_plural = "Семестры"
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.name} ({self.get_shift_display()})"
    
    def save(self, *args, **kwargs):
        if self.is_active:
            Semester.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()
    
    def get_time_slots(self):
        if self.shift == 'MORNING':
            return [
                ('08:00', '08:50'),
                ('09:00', '09:50'),
                ('10:00', '10:50'),
                ('11:00', '11:50'),
                ('12:00', '12:50'),
            ]
        else:
            return [
                ('13:00', '13:50'),
                ('14:00', '14:50'),
                ('15:00', '15:50'),
                ('16:00', '16:50'),
                ('17:00', '17:50'),
                ('18:00', '18:50'),
            ]

class AcademicWeek(models.Model):
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name='weeks',
        verbose_name="Семестр"
    )
    week_number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        verbose_name="Номер недели"
    )
    start_date = models.DateField(verbose_name="Начало недели")
    end_date = models.DateField(verbose_name="Конец недели")
    is_current = models.BooleanField(default=False, verbose_name="Текущая неделя")
    
    class Meta:
        verbose_name = "Учебная неделя"
        verbose_name_plural = "Учебные недели"
        ordering = ['semester', 'week_number']
        unique_together = ['semester', 'week_number']
    
    def __str__(self):
        return f"{self.semester.name} - Неделя {self.week_number}"
    
    @classmethod
    def get_current(cls):
        return cls.objects.filter(is_current=True).first()

class ScheduleSlot(models.Model):
    DAY_CHOICES = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
    ]
    
    TYPE_CHOICES = [
        ('LECTURE', 'Лекция'),
        ('PRACTICE', 'Практика'),
        ('SRSP', 'СРСП'),
    ]
    
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name='schedule_slots',
        verbose_name="Семестр"
    )
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
    lesson_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        verbose_name="Тип занятия"
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
    
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        related_name='schedule_slots',
        verbose_name="Аудитория"
    )
    
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
        return colors.get(self.lesson_type, 'secondary')
    
    def check_conflicts(self):
        conflicts = []
        
        same_time_slots = ScheduleSlot.objects.filter(
            semester=self.semester,
            day_of_week=self.day_of_week,
            start_time=self.start_time,
            is_active=True
        ).exclude(id=self.id)
        
        for slot in same_time_slots:
            if slot.teacher and self.teacher and slot.teacher == self.teacher:
                conflicts.append(f"Преподаватель {self.teacher.user.get_full_name()} занят в это время с группой {slot.group.name}")
            
            if slot.classroom and self.classroom and slot.classroom == self.classroom:
                conflicts.append(f"Кабинет {self.classroom.number} занят группой {slot.group.name}")
            
            if slot.group == self.group:
                conflicts.append(f"У группы {self.group.name} уже есть занятие в это время: {slot.subject.name}")
        
        return conflicts

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
    new_classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Новая аудитория"
    )
    
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