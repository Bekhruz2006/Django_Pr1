from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Group, Teacher, Department, Faculty
from datetime import timedelta, date
from django.utils import timezone
import uuid
import math
from django.utils.translation import gettext_lazy as _
from accounts.models import Institute, Student
import math
from django.db.models.signals import post_delete
from django.dispatch import receiver
import os
from django.db import models
import math
ROOM_TYPES =[
    ('LECTURE', _('Лекционная (Поточная)')),
    ('PRACTICE', _('Практическая (Обычная)')),
    ('COMPUTER', _('Компьютерный класс')),
    ('LAB', _('Лаборатория')),
    ('LINGUISTIC', _('Лингафонный кабинет')),
    ('SPORT', _('Спортивный зал')),
]
class CreditType(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Название системы (напр. ECTS)"))
    hours_per_credit = models.IntegerField(default=24, verbose_name=_("Часов в 1 кредите"))
    faculty = models.ForeignKey('accounts.Faculty', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = _("Тип кредита")
        verbose_name_plural = _("Типы кредитов")

    def __str__(self):
        return f"{self.name} ({self.hours_per_credit} ч.)"


class CreditTemplate(models.Model):
    credits = models.IntegerField(verbose_name=_("Количество кредитов"))
    lecture_pairs = models.FloatField(default=0, verbose_name=_("Лекции (пар в неделю)"))
    practice_pairs = models.FloatField(default=0, verbose_name=_("Практика (пар в неделю)"))
    lab_pairs = models.FloatField(default=0, verbose_name=_("Лабораторные (пар в неделю)"))
    srsp_pairs = models.FloatField(default=0, verbose_name=_("СРСП (пар в неделю)"))
    
    faculty = models.ForeignKey('accounts.Faculty', on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("Факультет"))

    class Meta:
        verbose_name = _("Шаблон распределения кредитов")
        verbose_name_plural = _("Шаблоны распределения кредитов")
        ordering = ['credits', 'lecture_pairs']

    def __str__(self):
        return f"{self.credits} кр. (Л:{self.lecture_pairs}, П:{self.practice_pairs}, Лаб:{self.lab_pairs}, СРСП:{self.srsp_pairs})"


class Subgroup(models.Model):
    subject = models.ForeignKey('schedule.Subject', on_delete=models.CASCADE, related_name='subgroups', verbose_name="Предмет")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='subgroups', verbose_name="Основная группа")
    name = models.CharField(max_length=50, verbose_name="Название подгруппы (напр. Подгруппа 1)")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Преподаватель подгруппы")
    students = models.ManyToManyField(Student, related_name='assigned_subgroups', blank=True, verbose_name="Студенты подгруппы")

    class Meta:
        verbose_name = "Подгруппа"
        verbose_name_plural = "Подгруппы"
        unique_together = ['subject', 'group', 'name']

    def __str__(self):
        return f"{self.group.name} - {self.name} ({self.subject.name})"




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
    TYPE_CHOICES =[
        ('LECTURE', _('Лекция')),
        ('PRACTICE', _('Практика')),
        ('LAB', _('Лабораторная')),
        ('SRSP', _('СРСП (КМРО)')),
    ]
    name = models.CharField(max_length=200, verbose_name=_("Название"))
    code = models.CharField(max_length=100, unique=True, verbose_name=_("Код"))

    department = models.ForeignKey('accounts.Department', on_delete=models.CASCADE, related_name='subjects', verbose_name=_("Кафедра"))

    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='LECTURE',
        verbose_name=_("Основной тип")
    )

    lecture_hours = models.IntegerField(default=0, verbose_name=_("Лекции (Л) часов за семестр"))
    practice_hours = models.IntegerField(default=0, verbose_name=_("Практика (А) часов за семестр"))
    lab_hours = models.IntegerField(default=0, verbose_name=_("Лабораторные часов за семестр"))
    control_hours = models.IntegerField(default=0, verbose_name=_("Контроль (КМРО) часов за семестр"))
    independent_work_hours = models.IntegerField(default=0, verbose_name=_("КМД часов за семестр"))

    semester_weeks = models.IntegerField(default=16, verbose_name=_("Недель в семестре"))

    is_stream_subject = models.BooleanField(
        default=False,
        verbose_name=_("Это поток (совместное занятие)")
    )
    preferred_room_type = models.CharField(
        max_length=20, choices=ROOM_TYPES, blank=True, null=True,
        verbose_name=_("Рекомендуемый тип аудитории")
    )

    teacher = models.ForeignKey(
        'accounts.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Преподаватель")
    )

    required_competencies = models.ManyToManyField(
        'accounts.KnowledgeArea',
        blank=True,
        related_name='subjects',
        verbose_name=_("Требуемые компетенции (Для ИИ)")
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

    credit_type = models.ForeignKey(CreditType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Система кредитов"))

    plan_discipline = models.ForeignKey(
        'PlanDiscipline',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Основание (из плана)")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Активен (учитывается в нагрузке)"))

    class Meta:
        verbose_name = _("Предмет")
        verbose_name_plural = _("Предметы")
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.department.name})"

    @property
    def total_auditory_hours(self):
        return self.lecture_hours + self.practice_hours + self.lab_hours + self.control_hours

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
        import math
        return math.ceil(hours_count / 2)

    def get_actual_semester_weeks(self):
            from schedule.models import Semester
            import math
            
            faculty = self.department.faculty
            active_sem = Semester.objects.filter(faculty=faculty, is_active=True).first()
            if not active_sem:
                active_sem = Semester.objects.filter(is_active=True).first()
                
            if active_sem and active_sem.start_date and active_sem.end_date:
                delta = active_sem.end_date - active_sem.start_date
                weeks = delta.days / 7.0
                
                if active_sem.vacation_weeks:
                    vacs = len([w for w in active_sem.vacation_weeks.split(',') if w.strip().isdigit()])
                    weeks -= vacs
                    
                return max(1, int(math.ceil(weeks)))
                
            return self.semester_weeks

    def get_weekly_slots_needed(self):
            actual_weeks = self.get_actual_semester_weeks()
            if actual_weeks <= 0: return {'LECTURE': 0, 'PRACTICE': 0, 'LAB': 0, 'SRSP': 0}

            lec_h = self.lecture_hours
            prac_h = self.practice_hours
            lab_h = self.lab_hours
            srsp_h = self.control_hours

            if lec_h == 0 and prac_h == 0 and lab_h == 0 and srsp_h == 0 and self.credits > 0:
                total_auditory = (self.credits * 24) * 2 // 3
                lec_h = total_auditory // 3
                prac_h = total_auditory // 3
                srsp_h = total_auditory - lec_h - prac_h

            total_lec_pairs = self.get_hours_in_pairs(lec_h)
            total_prac_pairs = self.get_hours_in_pairs(prac_h)
            total_lab_pairs = self.get_hours_in_pairs(lab_h)
            total_srsp_pairs = self.get_hours_in_pairs(srsp_h)

            return {
                'LECTURE': math.ceil(total_lec_pairs / actual_weeks),
                'PRACTICE': math.ceil(total_prac_pairs / actual_weeks),
                'LAB': math.ceil(total_lab_pairs / actual_weeks),
                'SRSP': math.ceil(total_srsp_pairs / actual_weeks),
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
        unique_together = ['institute', 'shift', 'start_time']

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

    def get_week_start_date(self, academic_week_num):
        if not self.start_date:
            return timezone.now().date()
        
        vacations = []
        if self.vacation_weeks:
            vacations = sorted([int(w.strip()) for w in self.vacation_weeks.split(',') if w.strip().isdigit()])
        
        chrono_week = 1
        academic_week = 1
        
        while academic_week < academic_week_num:
            chrono_week += 1
            if chrono_week not in vacations:
                academic_week += 1
                
        while chrono_week in vacations:
            chrono_week += 1
            
        return self.start_date + timedelta(weeks=chrono_week - 1)

    def get_current_week_number(self):
        if not self.start_date:
            return 1
        today = date.today()
        if today < self.start_date:
            return 1
        delta = today - self.start_date
        chrono_week = (delta.days // 7) + 1
        
        vacations = []
        if self.vacation_weeks:
            vacations = [int(w.strip()) for w in self.vacation_weeks.split(',') if w.strip().isdigit()]
            
        if chrono_week in vacations:
            return -1
            
        academic_week = chrono_week
        for v in vacations:
            if v < chrono_week:
                academic_week -= 1
                
        return academic_week

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
    vacation_weeks = models.CharField(
        max_length=50, 
        blank=True, 
        verbose_name=_("Каникулярные недели"), 
        help_text=_("Номера хронологических недель от начала семестра через запятую (напр. 8,9)")
    )
    is_active = models.BooleanField(default=False, verbose_name=_("Активный"))

    class Meta:
        verbose_name = _("Семестр")
        verbose_name_plural = _("Семестры")
        unique_together = ['faculty', 'academic_year', 'number', 'course']
        ordering = ['-academic_year', 'course', 'number']

    def __str__(self):
        return f"{self.name} ({self.course} курс)"

    def save(self, *args, **kwargs):
        if self.is_active and self.faculty and self.course:
            Semester.objects.filter(
                faculty=self.faculty,
                course=self.course,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls, course=None):
        if course:
            return cls.objects.filter(is_active=True, course=course).first()
        return cls.objects.filter(is_active=True).first()

class Classroom(models.Model):


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

    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='PRACTICE', verbose_name=_("Тип кабинета"))
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
        ('LAB', _('Лабораторная')),
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
    subgroup = models.ForeignKey(Subgroup, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("Подгруппа (если есть)"))

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
        constraints = [
            models.UniqueConstraint(
                fields=['classroom', 'day_of_week', 'time_slot', 'semester', 'week_type'],
                condition=Q(classroom__isnull=False, is_active=True, stream_id__isnull=True),
                name='scheduleslot_unique_room_slot_active',
            ),
        ]

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
        constraints = [
            models.UniqueConstraint(
                fields=['specialty', 'admission_year'], 
                condition=models.Q(group__isnull=True), 
                name='unique_specialty_year_no_group'
            ),
            models.UniqueConstraint(
                fields=['specialty', 'admission_year', 'group'], 
                condition=models.Q(group__isnull=False), 
                name='unique_specialty_year_group'
            )
        ]


        
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
    preferred_room_type = models.CharField(
        max_length=20, choices=ROOM_TYPES, blank=True, null=True,
        verbose_name=_("Рекомендуемый тип аудитории")
    )
    credit_type = models.ForeignKey(CreditType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Система кредитов"))

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
    credits = models.IntegerField(default=0, verbose_name=_("Кредиты (устарело)"))
    credit_type = models.ForeignKey(CreditType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Система кредитов"))

    class Meta:
        verbose_name = _("Учебный материал")
        verbose_name_plural = _("Учебные материалы")

    def __str__(self):
        return self.title

@receiver(post_delete, sender=SubjectMaterial)
def auto_delete_material_file(sender, instance, **kwargs):
    if instance.file and os.path.isfile(instance.file.path):
        os.remove(instance.file.path)

@receiver(post_delete, sender=Subject)
def auto_delete_syllabus_file(sender, instance, **kwargs):
    if getattr(instance, 'syllabus_file', None) and os.path.isfile(instance.syllabus_file.path):
        os.remove(instance.syllabus_file.path)

class TeacherUnavailableSlot(models.Model):
    teacher = models.ForeignKey(
        'accounts.Teacher', 
        on_delete=models.CASCADE, 
        related_name='unavailable_slots', 
        verbose_name=_("Преподаватель")
    )
    day_of_week = models.IntegerField(
        choices=ScheduleSlot.DAYS_OF_WEEK, 
        verbose_name=_("День недели")
    )
    time_slot = models.ForeignKey(
        TimeSlot, 
        on_delete=models.CASCADE, 
        verbose_name=_("Время")
    )

    class Meta:
        verbose_name = _("Недоступное время преподавателя")
        verbose_name_plural = _("Недоступное время преподавателей")
        unique_together =['teacher', 'day_of_week', 'time_slot']

    def __str__(self):
        return f"{self.teacher} - {self.get_day_of_week_display()} {self.time_slot}"
