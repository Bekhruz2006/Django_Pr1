# schedule/models.py - ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Group, Teacher
from datetime import timedelta

# schedule/models.py - ИСПРАВЛЕННАЯ МОДЕЛЬ Subject

# schedule/models.py - ОБНОВЛЕННАЯ МОДЕЛЬ Subject

class Subject(models.Model):
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
        verbose_name="Основной тип"
    )
    
    # ✅ НОВЫЕ ПОЛЯ: Распределение часов по типам (за семестр)
    lecture_hours = models.IntegerField(default=0, verbose_name="Лекции (Л) часов за семестр")
    practice_hours = models.IntegerField(default=0, verbose_name="Практика (А) часов за семестр")
    control_hours = models.IntegerField(default=0, verbose_name="Контроль (КМРО) часов за семестр")
    independent_work_hours = models.IntegerField(default=0, verbose_name="КМД часов за семестр")
    
    semester_weeks = models.IntegerField(default=16, verbose_name="Недель в семестре")
    
    teacher = models.ForeignKey(
        'accounts.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Преподаватель"
    )
    
    # ✅ НОВОЕ: Связь с группами (предмет может быть назначен нескольким группам)
    groups = models.ManyToManyField(
        'accounts.Group',
        related_name='assigned_subjects',
        blank=True,
        verbose_name="Группы"
    )
    
    description = models.TextField(blank=True, verbose_name="Описание")
    
    # СТАРЫЕ ПОЛЯ (оставляем для совместимости, но не используем)
    credits = models.IntegerField(default=0, verbose_name="Кредиты (устарело)")
    hours_per_semester = models.IntegerField(default=0, verbose_name="Часов (устарело)")
    
    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    # ========== РАСЧЕТНЫЕ СВОЙСТВА ПО ФОРМУЛЕ 1 КРЕДИТ = 24 ЧАСА ==========
    
    @property
    def total_auditory_hours(self):
        """Всего аудиторных часов = Л + А + КМРО"""
        return self.lecture_hours + self.practice_hours + self.control_hours
    
    @property
    def total_hours(self):
        """Общая трудоемкость = Аудиторные + КМД"""
        return self.total_auditory_hours + self.independent_work_hours
    
    @property
    def total_credits(self):
        """Общие кредиты = Общие часы / 24"""
        return round(self.total_hours / 24, 1) if self.total_hours > 0 else 0
    
    @property
    def teacher_credits(self):
        """Кредиты с преподавателем = Аудиторные часы / 24"""
        return round(self.total_auditory_hours / 24, 1) if self.total_auditory_hours > 0 else 0
    
    # ========== ЧАСЫ В НЕДЕЛЮ (для конструктора расписания) ==========
    
    @property
    def lecture_hours_per_week(self):
        """Лекций часов в неделю"""
        return round(self.lecture_hours / self.semester_weeks, 1) if self.semester_weeks > 0 else 0
    
    @property
    def practice_hours_per_week(self):
        """Практик часов в неделю"""
        return round(self.practice_hours / self.semester_weeks, 1) if self.semester_weeks > 0 else 0
    
    @property
    def control_hours_per_week(self):
        """Контроля часов в неделю"""
        return round(self.control_hours / self.semester_weeks, 1) if self.semester_weeks > 0 else 0
    
    @property
    def total_hours_per_week(self):
        """Всего аудиторных часов в неделю"""
        return self.lecture_hours_per_week + self.practice_hours_per_week + self.control_hours_per_week
    
    # ========== ДЛЯ КОНСТРУКТОРА: Сколько раз нужно добавить в расписание ==========
    
    def get_weekly_slots_needed(self, slot_duration=1):
        import math
        return {
            # Используем ceil, чтобы если есть часы (например 0.7), 
            # они превращались в 1 слот, а не исчезали
            'LECTURE': math.ceil(self.lecture_hours_per_week / slot_duration),
            'PRACTICE': math.ceil(self.practice_hours_per_week / slot_duration),
            'SRSP': math.ceil(self.control_hours_per_week / slot_duration),
        }
        
    def get_remaining_slots(self, group, lesson_type):
        """
        Сколько еще раз можно добавить предмет в расписание для группы
        lesson_type: 'LECTURE', 'PRACTICE', или 'SRSP'
        """
        needed = self.get_weekly_slots_needed()
        needed_count = needed.get(lesson_type, 0)
        
        # Считаем, сколько уже добавлено
        from schedule.models import ScheduleSlot
        existing_count = ScheduleSlot.objects.filter(
            subject=self,
            group=group,
            is_active=True
        ).count()
        
        return max(0, needed_count - existing_count)
    
    def can_add_to_schedule(self, group, lesson_type):
        """Можно ли еще добавить предмет в расписание"""
        return self.get_remaining_slots(group, lesson_type) > 0
    
    def get_color_class(self):
        """Цвет для отображения"""
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
    
    # ✅ НОВОЕ ПОЛЕ: Курс
    COURSE_CHOICES = [
        (1, '1 курс'),
        (2, '2 курс'),
        (3, '3 курс'),
        (4, '4 курс'),
        (5, '5 курс'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название")
    number = models.IntegerField(choices=NUMBER_CHOICES, verbose_name="Номер семестра")
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, verbose_name="Смена")
    
    # ✅ НОВОЕ ПОЛЕ
    course = models.IntegerField(
        choices=COURSE_CHOICES,
        verbose_name="Курс",
        help_text="Для какого курса этот семестр"
    )
    
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата окончания")
    is_active = models.BooleanField(default=False, verbose_name="Активный")
    
    class Meta:
        verbose_name = "Семестр"
        verbose_name_plural = "Семестры"
        ordering = ['-start_date']
        # ✅ НОВОЕ ОГРАНИЧЕНИЕ: Уникальность семестра по курсу+номеру+году
        unique_together = [['course', 'number', 'start_date']]
    
    def __str__(self):
        return f"{self.name} ({self.course} курс)"
    
    def save(self, *args, **kwargs):
        if self.is_active:
            # ✅ Деактивируем другие семестры ТОЛЬКО для этого курса
            Semester.objects.filter(course=self.course).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls, course=None):
        """Получить активный семестр (опционально для конкретного курса)"""
        if course:
            return cls.objects.filter(is_active=True, course=course).first()
        return cls.objects.filter(is_active=True).first()


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
    
    # ✅ ДОБАВЬТЕ ЭТО ПОЛЕ (используем те же типы, что в Subject)
    LESSON_TYPE_CHOICES = [
        ('LECTURE', 'Лекция'),
        ('PRACTICE', 'Практика'),
        ('SRSP', 'СРСП (КМРО)'),
    ]
    
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Группа")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name="Предмет")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Преподаватель")
    
    # ✅ НОВОЕ ПОЛЕ
    lesson_type = models.CharField(
        max_length=10,
        choices=LESSON_TYPE_CHOICES,
        default='LECTURE',
        verbose_name="Тип занятия"
    )
    
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, verbose_name="Семестр")
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name="День недели")
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, verbose_name="Время")
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
        return f"{self.group.name} - {self.subject.name} ({self.get_lesson_type_display()}, {self.get_day_of_week_display()}, {self.start_time})"


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