# schedule/models.py - ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Group, Teacher
from datetime import timedelta

# schedule/models.py - ИСПРАВЛЕННАЯ МОДЕЛЬ Subject

class Subject(models.Model):
    """Учебный предмет"""
    
    TYPE_CHOICES = [
        ('LECTURE', 'Лекция'),
        ('PRACTICE', 'Практика'),
        ('SRSP', 'СРСП (КМРО)'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название")
    code = models.CharField(max_length=20, unique=True, verbose_name="Код")
    
    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='LECTURE',
        verbose_name="Тип занятия"
    )
    
    credits = models.IntegerField(verbose_name="Кредиты")
    hours_per_semester = models.IntegerField(default=0, verbose_name="Часов в семестр")
    teacher = models.ForeignKey(
        'accounts.Teacher', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Преподаватель"
    )
    
    # ✅ ДОБАВЬТЕ ЭТО ПОЛЕ
    description = models.TextField(
        blank=True, 
        verbose_name="Описание"
    )
    
    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"
    
    def get_credits_distribution(self):
        """Распределение кредитов по типам занятий (поровну)"""
        per_type = self.credits // 3
        return {
            'LECTURE': per_type,
            'PRACTICE': per_type,
            'SRSP': per_type
        }
    
    def get_hours_distribution(self):
        """Распределение часов по типам занятий (поровну)"""
        per_type = self.hours_per_semester // 3
        return {
            'LECTURE': per_type,
            'PRACTICE': per_type,
            'SRSP': per_type
        }
    
    def get_color_class(self):
        """Цвет для отображения в расписании"""
        return {
            'LECTURE': 'primary',
            'PRACTICE': 'success',
            'SRSP': 'warning'
        }.get(self.type, 'secondary')

# ✅ ДОБАВЛЕНО: Модель TimeSlot для временных слотов
class TimeSlot(models.Model):
    """Временной слот (время пары)"""
    start_time = models.TimeField(verbose_name="Начало")
    end_time = models.TimeField(verbose_name="Конец")
    name = models.CharField(max_length=50, blank=True, verbose_name="Название")
    
    class Meta:
        verbose_name = "Временной слот"
        verbose_name_plural = "Временные слоты"
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class Semester(models.Model):
    """Учебный семестр"""
    NUMBER_CHOICES = [
        (1, 'Первый'),
        (2, 'Второй'),
    ]
    
    SHIFT_CHOICES = [
        ('MORNING', 'Утренняя смена'),
        ('DAY', 'Дневная смена'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название")
    number = models.IntegerField(choices=NUMBER_CHOICES, verbose_name="Номер семестра")
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, verbose_name="Смена")
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата окончания")
    is_active = models.BooleanField(default=False, verbose_name="Активный")
    
    class Meta:
        verbose_name = "Семестр"
        verbose_name_plural = "Семестры"
        ordering = ['-start_date']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self.is_active:
            Semester.objects.exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()
    
    def get_time_slots(self):
        """Возвращает временные слоты для данной смены"""
        if self.shift == 'MORNING':
            return [
                ('08:00:00', '08:50:00'),
                ('09:00:00', '09:50:00'),
                ('10:00:00', '10:50:00'),
                ('11:00:00', '11:50:00'),
                ('12:00:00', '12:50:00'),
                ('13:00:00', '13:50:00'),
            ]
        else:  # DAY
            return [
                ('13:00:00', '13:50:00'),
                ('14:00:00', '14:50:00'),
                ('15:00:00', '15:50:00'),
                ('16:00:00', '16:50:00'),
                ('17:00:00', '17:50:00'),
                ('18:00:00', '18:50:00'),
            ]


class Classroom(models.Model):
    """Учебный кабинет"""
    number = models.CharField(max_length=20, unique=True, verbose_name="Номер")
    floor = models.IntegerField(verbose_name="Этаж")
    capacity = models.IntegerField(default=30, verbose_name="Вместимость")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    
    class Meta:
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"
        ordering = ['floor', 'number']
    
    def __str__(self):
        return f"Каб. {self.number}"


class ScheduleSlot(models.Model):
    """Занятие в расписании"""
    DAYS_OF_WEEK = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
    ]
    
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Группа")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name="Предмет")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Преподаватель")
    
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, verbose_name="Семестр")
    
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name="День недели")
    
    # ✅ ИСПРАВЛЕНО: Используем ForeignKey к TimeSlot
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, verbose_name="Время")
    
    # Дублируем время для удобства (заполняется автоматически)
    start_time = models.TimeField(verbose_name="Начало")
    end_time = models.TimeField(verbose_name="Конец")
    
    classroom = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Кабинет")
    room = models.CharField(max_length=20, blank=True, null=True, verbose_name="Номер кабинета (текст)")
    
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    
    class Meta:
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        ordering = ['day_of_week', 'start_time']
    
    def __str__(self):
        return f"{self.group.name} - {self.subject.name} ({self.get_day_of_week_display()}, {self.start_time})"
    
    def save(self, *args, **kwargs):
        # Автоматически заполняем start_time и end_time из time_slot
        if self.time_slot:
            self.start_time = self.time_slot.start_time
            self.end_time = self.time_slot.end_time
        super().save(*args, **kwargs)
    
    def get_color_class(self):
        """Цвет для отображения"""
        return self.subject.get_color_class()
    
    def check_conflicts(self):
        """Проверка конфликтов расписания"""
        conflicts = []
        
        # Конфликт: та же группа в это же время
        group_conflict = ScheduleSlot.objects.filter(
            group=self.group,
            day_of_week=self.day_of_week,
            time_slot=self.time_slot,
            is_active=True
        ).exclude(id=self.id)
        
        if group_conflict.exists():
            conflicts.append(f"У группы {self.group.name} уже есть занятие в это время")
        
        # Конфликт: тот же преподаватель в это же время
        if self.teacher:
            teacher_conflict = ScheduleSlot.objects.filter(
                teacher=self.teacher,
                day_of_week=self.day_of_week,
                time_slot=self.time_slot,
                is_active=True
            ).exclude(id=self.id)
            
            if teacher_conflict.exists():
                conflicts.append(f"Преподаватель {self.teacher.user.get_full_name()} занят в это время")
        
        # Конфликт: та же аудитория в это же время
        if self.classroom:
            classroom_conflict = ScheduleSlot.objects.filter(
                classroom=self.classroom,
                day_of_week=self.day_of_week,
                time_slot=self.time_slot,
                is_active=True
            ).exclude(id=self.id)
            
            if classroom_conflict.exists():
                conflicts.append(f"Кабинет {self.classroom.number} занят в это время")
        
        return conflicts


class ScheduleException(models.Model):
    """Исключение в расписании (отмена, перенос)"""
    EXCEPTION_TYPES = [
        ('CANCEL', 'Отменено'),
        ('RESCHEDULE', 'Перенесено'),
    ]
    
    schedule_slot = models.ForeignKey(ScheduleSlot, on_delete=models.CASCADE, verbose_name="Занятие")
    exception_type = models.CharField(max_length=20, choices=EXCEPTION_TYPES, verbose_name="Тип")
    exception_date = models.DateField(verbose_name="Дата исключения")
    reason = models.TextField(verbose_name="Причина")
    
    # Для переноса
    new_date = models.DateField(null=True, blank=True, verbose_name="Новая дата")
    new_start_time = models.TimeField(null=True, blank=True, verbose_name="Новое время начала")
    new_end_time = models.TimeField(null=True, blank=True, verbose_name="Новое время окончания")
    new_classroom = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Новый кабинет")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Исключение в расписании"
        verbose_name_plural = "Исключения в расписании"
    
    def __str__(self):
        return f"{self.schedule_slot} - {self.get_exception_type_display()} ({self.exception_date})"


class AcademicWeek(models.Model):
    """Текущая учебная неделя"""
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, verbose_name="Семестр")
    week_number = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(20)], verbose_name="Номер недели")
    start_date = models.DateField(verbose_name="Начало недели")
    end_date = models.DateField(verbose_name="Конец недели")
    is_current = models.BooleanField(default=True, verbose_name="Текущая неделя")
    
    class Meta:
        verbose_name = "Учебная неделя"
        verbose_name_plural = "Учебные недели"
    
    def __str__(self):
        return f"Неделя {self.week_number} ({self.start_date})"
    
    @classmethod
    def get_current(cls):
        return cls.objects.filter(is_current=True).first()
    
    @property
    def semester_start_date(self):
        """Дата начала семестра для обратной совместимости"""
        return self.semester.start_date if self.semester else self.start_date
    
    @property
    def current_week(self):
        """Номер текущей недели для обратной совместимости"""
        return self.week_number
    
    def calculate_current_week(self):
        """Рассчитать текущую неделю на основе даты"""
        from datetime import date
        today = date.today()
        delta = today - self.semester.start_date
        return (delta.days // 7) + 1