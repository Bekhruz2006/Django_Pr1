from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Group, Teacher, Department, Faculty
from datetime import timedelta, date
import uuid
import math
from django.utils.translation import gettext_lazy as _
from accounts.models import Institute
import math

from django.db import models
import math

class Building(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Название корпуса"), help_text="Например: Главный корпус, Блок А")
    address = models.CharField(max_length=255, blank=True, verbose_name=_("Адрес"))
    institute = models.ForeignKey(
        Institute,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='buildings',
        verbose_name=_("Принадлежность Институту")
    )

    class Meta:
        verbose_name = _("Учебный корпус")
        verbose_name_plural = _("Учебные корпуса")

    def __str__(self):
        return self.name

class Subject(models.Model):
    TYPE_CHOICES = [
        ('LECTURE', _('Лекция')),
        ('PRACTICE', _('Практика')),
        ('SRSP', _('СРСП (КМРО)')),
    ]
    name = models.CharField(max_length=200, verbose_name=_("Название"))
    code = models.CharField(max_length=20, unique=True, verbose_name=_("Код"))

    department = models.ForeignKey('accounts.Department', on_delete=models.CASCADE, related_name='subjects', verbose_name=_("Кафедра"))

    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='LECTURE',
        verbose_name=_("Основной тип")
    )

    lecture_hours = models.IntegerField(default=0, verbose_name=_("Лекции (Л) часов за семестр"))
    practice_hours = models.IntegerField(default=0, verbose_name=_("Практика (А) часов за семестр"))
    control_hours = models.IntegerField(default=0, verbose_name=_("Контроль (КМРО) часов за семестр"))
    independent_work_hours = models.IntegerField(default=0, verbose_name=_("КМД часов за семестр"))

    semester_weeks = models.IntegerField(default=16, verbose_name=_("Недель в семестре"))

    is_stream_subject = models.BooleanField(
        default=False,
        verbose_name=_("Это поток (совместное занятие)")
    )

    teacher = models.ForeignKey(
        'accounts.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Преподаватель")
    )
    groups = models.ManyToManyField('accounts.Group', related_name='subjects', blank=True, verbose_name=_("Группы"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    syllabus_file = models.FileField(
        upload_to='syllabus/',
        blank=True,
        null=True,
        verbose_name=_("Силлабус (PDF/Word)")
    )

    credits = models.IntegerField(default=0, verbose_name=_("Кредиты (устарело)"))
    hours_per_semester = models.IntegerField(default=0, verbose_name=_("Часов (устарело)"))

    plan_discipline = models.ForeignKey(
        'PlanDiscipline',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Основание (из плана)")
    )

    class Meta:
        verbose_name = _("Предмет")
        verbose_name_plural = _("Предметы")
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

    def get_hours_in_pairs(self, hours_count):
        try:
            institute = self.department.faculty.institute
            acad_duration = institute.academic_hour_duration
            pair_duration = institute.pair_duration
            ratio = pair_duration / acad_duration

            if ratio <= 0: return 0

            import math
            return math.ceil(hours_count / ratio)
        except AttributeError:
            return hours_count

    def get_weekly_slots_needed(self):
        if self.semester_weeks <= 0: return {'LECTURE': 0, 'PRACTICE': 0, 'SRSP': 0}

        total_lec_pairs = self.get_hours_in_pairs(self.lecture_hours)
        total_prac_pairs = self.get_hours_in_pairs(self.practice_hours)
        total_srsp_pairs = self.get_hours_in_pairs(self.control_hours)

        return {
            'LECTURE': math.ceil(total_lec_pairs / self.semester_weeks),
            'PRACTICE': math.ceil(total_prac_pairs / self.semester_weeks),
            'SRSP': math.ceil(total_srsp_pairs / self.semester_weeks),
        }

class TimeSlot(models.Model):
    SHIFT_CHOICES = [
        ('MORNING', _('Утренняя смена (1-я)')),
        ('DAY', _('Дневная смена (2-я)')),
        ('EVENING', _('Вечерняя смена (3-я)')),
    ]

    institute = models.ForeignKey(
        Institute,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name=_("Институт"),
        null=True, blank=True
    )

    number = models.IntegerField(verbose_name=_("Номер пары"))
    start_time = models.TimeField(verbose_name=_("Начало"))
    end_time = models.TimeField(verbose_name=_("Конец"))
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='MORNING')

    duration = models.IntegerField(verbose_name=_("Длительность (мин)"), default=50)

    class Meta:
        verbose_name = _("Временной слот")
        verbose_name_plural = _("Временные слоты")
        ordering = ['institute', 'shift', 'start_time']
        unique_together = ['institute', 'start_time']

    def __str__(self):
        inst = self.institute.abbreviation if self.institute else "Global"
        return f"[{inst}] {self.number}-пара ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"

class Semester(models.Model):
    def get_week_type_for_date(self, target_date):
        if not self.start_date:
            return 'EVERY'

        if target_date < self.start_date:
            return 'RED'

        delta = target_date - self.start_date
        week_number = (delta.days // 7) + 1

        return 'RED' if week_number % 2 != 0 else 'BLUE'

    def get_current_week_number(self):
        if not self.start_date:
            return 1
        today = date.today()
        if today < self.start_date:
            return 1
        delta = today - self.start_date
        return (delta.days // 7) + 1

    NUMBER_CHOICES = [
        (1, _('Первый')),
        (2, _('Второй')),
    ]

    SHIFT_CHOICES = [
        ('MORNING', _('Утренняя смена')),
        ('DAY', _('Дневная смена')),
    ]

    COURSE_CHOICES = [
        (1, _('1 курс')),
        (2, _('2 курс')),
        (3, _('3 курс')),
        (4, _('4 курс')),
        (5, _('5 курс')),
    ]
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='semesters',
        verbose_name=_("Факультет"),
        null=True,
        blank=True
    )
    name = models.CharField(max_length=200, verbose_name=_("Название (напр. Осенний)"))
    academic_year = models.CharField(max_length=20, verbose_name=_("Учебный год"), help_text=_("Формат: 2024-2025"))
    number = models.IntegerField(choices=NUMBER_CHOICES, verbose_name=_("Номер семестра"))
    course = models.IntegerField(choices=COURSE_CHOICES, verbose_name=_("Курс"))
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, verbose_name=_("Смена"))

    start_date = models.DateField(verbose_name=_("Дата начала"))
    end_date = models.DateField(verbose_name=_("Дата окончания"))
    is_active = models.BooleanField(default=False, verbose_name=_("Активный"))

    class Meta:
        verbose_name = _("Семестр")
        verbose_name_plural = _("Семестры")
        unique_together = ['faculty', 'academic_year', 'number', 'course']
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
    ROOM_TYPES = [
        ('LECTURE', _('Лекционная (Обычная)')),
        ('COMPUTER', _('Компьютерный класс')),
        ('LAB', _('Лаборатория')),
        ('LINGUISTIC', _('Лингафонный кабинет')),
        ('SPORT', _('Спортивный зал')),
    ]

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name='classrooms',
        verbose_name=_("Корпус/Блок"),
        null=True
    )
    number = models.CharField(max_length=20, verbose_name=_("Номер"))
    floor = models.IntegerField(verbose_name=_("Этаж"))
    capacity = models.IntegerField(default=30, verbose_name=_("Вместимость"))

    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='LECTURE', verbose_name=_("Тип кабинета"))

    is_active = models.BooleanField(default=True, verbose_name=_("Активен"))

    class Meta:
        verbose_name = _("Кабинет")
        verbose_name_plural = _("Кабинеты")
        ordering = ['building', 'floor', 'number']
        unique_together = ['building', 'number']

    def __str__(self):
        if self.building:
            return f"{self.building.name} — {self.number}"
        return f"Каб. {self.number}"

class ScheduleSlot(models.Model):
    DAYS_OF_WEEK = [
        (0, _('Понедельник')),
        (1, _('Вторник')),
        (2, _('Среда')),
        (3, _('Четверг')),
        (4, _('Пятница')),
        (5, _('Суббота')),
    ]

    LESSON_TYPE_CHOICES = [
        ('LECTURE', _('Лекция')),
        ('PRACTICE', _('Практика')),
        ('SRSP', _('СРСП (КМРО)')),
    ]

    WEEK_TYPE_CHOICES = [
        ('EVERY', _('Каждую неделю')),
        ('RED', _('Красная неделя (Числитель)')),
        ('BLUE', _('Синяя неделя (Знаменатель)')),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name=_("Группа"))
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name=_("Предмет"))
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Преподаватель"))

    lesson_type = models.CharField(
        max_length=10,
        choices=LESSON_TYPE_CHOICES,
        default='LECTURE',
        verbose_name=_("Тип занятия")
    )

    week_type = models.CharField(
        max_length=10,
        choices=WEEK_TYPE_CHOICES,
        default='EVERY',
        verbose_name=_("Тип недели")
    )

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, verbose_name=_("Семестр"))
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name=_("День недели"))
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, verbose_name=_("Время"))
    start_time = models.TimeField(verbose_name=_("Начало"))
    end_time = models.TimeField(verbose_name=_("Конец"))
    classroom = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Кабинет"))
    room = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Номер кабинета (текст)"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активно"))

    stream_id = models.UUIDField(null=True, blank=True, verbose_name=_("ID Потока"))

    is_military = models.BooleanField(default=False, verbose_name=_("Военная кафедра"))

    class Meta:
        verbose_name = _("Занятие")
        verbose_name_plural = _("Занятия")
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
        week_type_mark = " (Красная неделя)" if self.week_type == 'RED' else " (Синяя неделя)" if self.week_type == 'BLUE' else ""
        return f"{self.group.name} - {self.subject.name} ({self.get_lesson_type_display()}){stream_mark}{week_type_mark}"

class ScheduleException(models.Model):
    EXCEPTION_TYPES = [
        ('CANCEL', _('Отменено')),
        ('RESCHEDULE', _('Перенесено')),
    ]

    schedule_slot = models.ForeignKey(ScheduleSlot, on_delete=models.CASCADE, verbose_name=_("Занятие"))
    exception_type = models.CharField(max_length=20, choices=EXCEPTION_TYPES, verbose_name=_("Тип"))
    exception_date = models.DateField(verbose_name=_("Дата исключения"))
    reason = models.TextField(verbose_name=_("Причина"))

    new_date = models.DateField(null=True, blank=True, verbose_name=_("Новая дата"))
    new_start_time = models.TimeField(null=True, blank=True, verbose_name=_("Новое время начала"))
    new_end_time = models.TimeField(null=True, blank=True, verbose_name=_("Новое время окончания"))
    new_classroom = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Новый кабинет"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Исключение в расписании")
        verbose_name_plural = _("Исключения в расписании")

    def __str__(self):
        return f"{self.schedule_slot} - {self.get_exception_type_display()} ({self.exception_date})"

class SubjectTemplate(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name=_("Название дисциплины"))

    class Meta:
        verbose_name = _("Шаблон дисциплины")
        verbose_name_plural = _("Справочник дисциплин")
        ordering = ['name']

    def __str__(self):
        return self.name

class AcademicPlan(models.Model):
    specialty = models.ForeignKey(
        'accounts.Specialty', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        verbose_name=_("Специальность")
    )
    admission_year = models.IntegerField(verbose_name=_("Год набора (поступления)"))
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name=_("Актуальный"))

    group = models.ForeignKey(
        'accounts.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='academic_plans',
        verbose_name=_("Группа (для индивидуального плана)")
    )

    class Meta:
        verbose_name = _("Учебный план (РУП)")
        verbose_name_plural = _("Учебные планы")
        unique_together = ['specialty', 'admission_year', 'group']
    def __str__(self):
        if self.group:
            return f"РУП Группы: {self.group.name} ({self.admission_year})"
        return f"РУП Специальности: {self.specialty.name} ({self.admission_year})"

class PlanDiscipline(models.Model):
    CONTROL_CHOICES = [
        ('EXAM', _('Экзамен')),
        ('CREDIT', _('Зачет')),
        ('DIFF_CREDIT', _('Дифф. зачет')),
        ('COURSE_WORK', _('Курсовая работа')),
    ]

    TYPE_CHOICES = [
        ('REQUIRED', _('Обязательная')),
        ('ELECTIVE', _('Элективная (по выбору)')),
        ('PRACTICE', _('Практика')),
    ]

    CYCLE_CHOICES = [
        ('OD', _('ОД (Умумитаълимӣ)')),
        ('BD', _('БД (Появӣ)')),
        ('PD', _('ПД (Ихтисосӣ)')),
        ('OTHER', _('Дигар (Другое)')),
    ]

    plan = models.ForeignKey(AcademicPlan, on_delete=models.CASCADE, related_name='disciplines')
    subject_template = models.ForeignKey(SubjectTemplate, on_delete=models.PROTECT, verbose_name=_("Дисциплина"))

    semester_number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name=_("Номер семестра (1-8)")
    )

    cycle = models.CharField(max_length=10, choices=CYCLE_CHOICES, default='OTHER', verbose_name=_("Цикл (ОД, БД, ПД)"))
    has_subgroups = models.BooleanField(default=False, verbose_name=_("Делится на подгруппы (Англ/Лабы)"))

    discipline_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='REQUIRED', verbose_name=_("Тип блока"))
    credits = models.IntegerField(verbose_name=_("Кредиты (ECTS)"))

    lecture_hours = models.IntegerField(default=0, verbose_name=_("Лекции (Л)"))
    practice_hours = models.IntegerField(default=0, verbose_name=_("Практика (А)"))
    lab_hours = models.IntegerField(default=0, verbose_name=_("Лабораторные"))
    control_hours = models.IntegerField(default=0, verbose_name=_("СРСП (КМРО)"))
    independent_hours = models.IntegerField(default=0, verbose_name=_("СРС (КМД)"))

    control_type = models.CharField(max_length=20, choices=CONTROL_CHOICES, default='EXAM', verbose_name=_("Форма контроля"))
    has_course_work = models.BooleanField(default=False, verbose_name=_("Есть курсовая работа (КР)"))

    class Meta:
        verbose_name = _("Дисциплина плана")
        verbose_name_plural = _("Дисциплины плана")
        ordering = ['semester_number', 'discipline_type', 'subject_template__name']
        unique_together = ['plan', 'subject_template', 'semester_number']

    def __str__(self):
        return f"{self.subject_template.name} ({self.semester_number} сем.)"

    @property
    def total_auditory_hours(self):
        return self.lecture_hours + self.practice_hours + self.lab_hours + self.control_hours

class SubjectMaterial(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='materials', verbose_name=_("Предмет"))
    title = models.CharField(max_length=255, verbose_name=_("Название материала"))
    file = models.FileField(upload_to='materials/%Y/%m/', verbose_name=_("Файл"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата загрузки"))

    class Meta:
        verbose_name = _("Учебный материал")
        verbose_name_plural = _("Учебные материалы")

    def __str__(self):
        return self.title
