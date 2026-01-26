from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Group, Teacher, Department
from datetime import timedelta, date
import uuid
import math

from django.db import models
import math

class Subject(models.Model):
    TYPE_CHOICES = [
        ('LECTURE', 'Лекция'),
        ('PRACTICE', 'Практика'),
        ('SRSP', 'СРСП (КМРО)'),
    ]
    name = models.CharField(max_length=200, verbose_name="Название")
    code = models.CharField(max_length=20, unique=True, verbose_name="Код")

    department = models.ForeignKey('accounts.Department', on_delete=models.CASCADE, related_name='subjects', verbose_name="Кафедра")

    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='LECTURE',
        verbose_name="Основной тип"
    )

    lecture_hours = models.IntegerField(default=0, verbose_name="Лекции (Л) часов за семестр")
    practice_hours = models.IntegerField(default=0, verbose_name="Практика (А) часов за семестр")
    control_hours = models.IntegerField(default=0, verbose_name="Контроль (КМРО) часов за семестр")
    independent_work_hours = models.IntegerField(default=0, verbose_name="КМД часов за семестр")

    semester_weeks = models.IntegerField(default=16, verbose_name="Недель в семестре")
    
    is_stream_subject = models.BooleanField(
        default=False, 
        verbose_name="Это поток (совместное занятие)"
    )
    
    teacher = models.ForeignKey(
        'accounts.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Преподаватель"
    )

    groups = models.ManyToManyField(
        'accounts.Group',
        related_name='assigned_subjects',
        blank=True,
        verbose_name="Группы"
    )

    description = models.TextField(blank=True, verbose_name="Описание")

    credits = models.IntegerField(default=0, verbose_name="Кредиты (устарело)")
    hours_per_semester = models.IntegerField(default=0, verbose_name="Часов (устарело)")
    
    plan_discipline = models.ForeignKey(
        'PlanDiscipline',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Основание (из плана)"
    )

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.department.name})"

    @property
    def total_auditory_hours(self):
        return self.lecture_hours + self.practice_hours + self.control_hours

    @property
    def total_hours(self):
        return self.total_auditory_hours + self.independent_work_hours

    @property
    def total_credits(self):
        return round(self.total_hours / 24, 1) if self.total_hours > 0 else 0

    @property
    def teacher_credits(self):
        return round(self.total_auditory_hours / 24, 1) if self.total_auditory_hours > 0 else 0

    @property
    def lecture_hours_per_week(self):
        return round(self.lecture_hours / self.semester_weeks, 1) if self.semester_weeks > 0 else 0

    @property
    def practice_hours_per_week(self):
        return round(self.practice_hours / self.semester_weeks, 1) if self.semester_weeks > 0 else 0

    @property
    def control_hours_per_week(self):
        return round(self.control_hours / self.semester_weeks, 1) if self.semester_weeks > 0 else 0

    @property
    def total_hours_per_week(self):
        return self.lecture_hours_per_week + self.practice_hours_per_week + self.control_hours_per_week

    def get_weekly_slots_needed(self, slot_duration=1):
        return {
            'LECTURE': math.ceil(self.lecture_hours / self.semester_weeks),
            'PRACTICE': math.ceil(self.practice_hours / self.semester_weeks),
            'SRSP': math.ceil(self.control_hours / self.semester_weeks),
        }

    def get_remaining_slots(self, group, lesson_type):
        needed = self.get_weekly_slots_needed()
        needed_count = needed.get(lesson_type, 0)

        from schedule.models import ScheduleSlot
        existing_count = ScheduleSlot.objects.filter(
            subject=self,
            group=group,
            is_active=True
        ).count()

        return max(0, needed_count - existing_count)

    def can_add_to_schedule(self, group, lesson_type):
        return self.get_remaining_slots(group, lesson_type) > 0

    def get_color_class(self):
        return {
            'LECTURE': 'primary',
            'PRACTICE': 'success',
            'SRSP': 'warning'
        }.get(self.type, 'secondary')

    def get_stream_groups(self):
        return self.groups.all()

    def check_is_multiple_groups(self):
        return self.groups.count() > 1
    

class TimeSlot(models.Model):
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
    NUMBER_CHOICES = [
        (1, 'Первый'),
        (2, 'Второй'),
    ]

    SHIFT_CHOICES = [
        ('MORNING', 'Утренняя смена'),
        ('DAY', 'Дневная смена'),
    ]

    COURSE_CHOICES = [
        (1, '1 курс'),
        (2, '2 курс'),
        (3, '3 курс'),
        (4, '4 курс'),
        (5, '5 курс'),
    ]

    name = models.CharField(max_length=200, verbose_name="Название (напр. Осенний)")
    academic_year = models.CharField(max_length=20, verbose_name="Учебный год", help_text="Формат: 2024-2025")
    number = models.IntegerField(choices=NUMBER_CHOICES, verbose_name="Номер семестра")
    course = models.IntegerField(choices=COURSE_CHOICES, verbose_name="Курс")
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, verbose_name="Смена")

    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата окончания")
    is_active = models.BooleanField(default=False, verbose_name="Активный")

    groups = models.ManyToManyField(
        'accounts.Group',
        blank=True,
        related_name='assigned_semesters',
        verbose_name="Применен к группам"
    )

    class Meta:
        verbose_name = "Семестр"
        verbose_name_plural = "Семестры"
        unique_together = ['academic_year', 'number', 'course']
        ordering = ['-academic_year', 'course', 'number']

    def __str__(self):
        return f"{self.name} ({self.course} курс)"

    def save(self, *args, **kwargs):
        if self.is_active:
            Semester.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls, course=None):
        if course:
            return cls.objects.filter(is_active=True, course=course).first()
        return cls.objects.filter(is_active=True).first()

class Classroom(models.Model):
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
    DAYS_OF_WEEK = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
    ]

    LESSON_TYPE_CHOICES = [
        ('LECTURE', 'Лекция'),
        ('PRACTICE', 'Практика'),
        ('SRSP', 'СРСП (КМРО)'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Группа")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name="Предмет")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Преподаватель")

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

    stream_id = models.UUIDField(null=True, blank=True, verbose_name="ID Потока")

    is_military = models.BooleanField(default=False, verbose_name="Военная кафедра")

    class Meta:
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        ordering = ['day_of_week', 'start_time']

    def get_color_class(self):
        if self.is_military:
            return 'dark text-white'
        if self.stream_id:
            return 'indigo'
        return {
            'LECTURE': 'primary',
            'PRACTICE': 'success',
            'SRSP': 'warning'
        }.get(self.lesson_type, 'secondary')

    def __str__(self):
        if self.is_military:
            return f"{self.group.name} - Военная кафедра"
        stream_mark = " [STREAM]" if self.stream_id else ""
        return f"{self.group.name} - {self.subject.name} ({self.get_lesson_type_display()}){stream_mark}"

class ScheduleException(models.Model):
    EXCEPTION_TYPES = [
        ('CANCEL', 'Отменено'),
        ('RESCHEDULE', 'Перенесено'),
    ]

    schedule_slot = models.ForeignKey(ScheduleSlot, on_delete=models.CASCADE, verbose_name="Занятие")
    exception_type = models.CharField(max_length=20, choices=EXCEPTION_TYPES, verbose_name="Тип")
    exception_date = models.DateField(verbose_name="Дата исключения")
    reason = models.TextField(verbose_name="Причина")

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
        return self.semester.start_date if self.semester else self.start_date

    @property
    def current_week(self):
        return self.week_number

    def calculate_current_week(self):
        today = date.today()
        delta = today - self.semester.start_date
        return (delta.days // 7) + 1



class SubjectTemplate(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name="Название дисциплины")
    
    class Meta:
        verbose_name = "Шаблон дисциплины"
        verbose_name_plural = "Справочник дисциплин"
        ordering = ['name']

    def __str__(self):
        return self.name


class AcademicPlan(models.Model):
    specialty = models.ForeignKey('accounts.Specialty', on_delete=models.CASCADE, verbose_name="Специальность")
    admission_year = models.IntegerField(verbose_name="Год набора (поступления)")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name="Актуальный")

    class Meta:
        verbose_name = "Учебный план (РУП)"
        verbose_name_plural = "Учебные планы"
        unique_together = ['specialty', 'admission_year']

    def __str__(self):
        return f"РУП: {self.specialty.name} ({self.admission_year})"


class PlanDiscipline(models.Model):
    plan = models.ForeignKey(AcademicPlan, on_delete=models.CASCADE, related_name='disciplines')
    subject_template = models.ForeignKey(SubjectTemplate, on_delete=models.PROTECT, verbose_name="Дисциплина")
    
    semester_number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        verbose_name="Номер семестра (1-8)"
    )
    
    credits = models.IntegerField(verbose_name="Кредиты")
    lecture_hours = models.IntegerField(default=0, verbose_name="Лекции")
    practice_hours = models.IntegerField(default=0, verbose_name="Практика")
    control_hours = models.IntegerField(default=0, verbose_name="СРСП")
    independent_hours = models.IntegerField(default=0, verbose_name="СРС")
    
    control_type = models.CharField(
        max_length=20, 
        choices=[('EXAM', 'Экзамен'), ('CREDIT', 'Зачет')],
        default='EXAM'
    )

    class Meta:
        verbose_name = "Дисциплина плана"
        verbose_name_plural = "Дисциплины плана"
        ordering = ['semester_number', 'subject_template__name']
        unique_together = ['plan', 'subject_template', 'semester_number']

    def __str__(self):
        return f"{self.subject_template.name} ({self.semester_number} сем.)"
