from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import datetime, date
from django.utils.translation import gettext_lazy as _
from django.db import transaction, IntegrityError
from django.utils import timezone
from datetime import datetime, date
from django.core.validators import FileExtensionValidator

def default_admission_year():
    return timezone.now().year

class Institute(models.Model):
    name = models.CharField(max_length=200, verbose_name=_("Название института"))
    abbreviation = models.CharField(max_length=20, verbose_name=_("Аббревиатура"))
    address = models.TextField(verbose_name=_("Адрес"), blank=True)
    academic_hour_duration = models.IntegerField(
        default=50, 
        verbose_name=_("Длительность академ. часа (мин)"),
        help_text=_("Обычно 45 или 50 минут. Используется для расчета кредитов.")
    )
    pair_duration = models.IntegerField(
        default=50,
        verbose_name=_("Длительность одной пары (мин)"),
        help_text=_("Физическое время занятия. Если пара 90 мин, а час 45, то 1 пара = 2 часа.")
    )

    class Meta:
        verbose_name = _("Институт")
        verbose_name_plural = _("Институты")

    def __str__(self):
        return self.name

class Faculty(models.Model):
    institute = models.ForeignKey(
        Institute, on_delete=models.CASCADE,
        related_name='faculties', verbose_name=_("Институт")
    )
    name = models.CharField(max_length=200, verbose_name=_("Название факультета"))
    short_name = models.CharField(
        max_length=50, blank=True,
        verbose_name=_("Краткое название (аббревиатура)"),
        help_text=_("Например: ФЗС, ФТР")
    )
    code = models.CharField(max_length=50, unique=True, verbose_name=_("Код факультета"))

    class Meta:
        verbose_name = _("Факультет")
        verbose_name_plural = _("Факультеты")
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.institute.abbreviation})"

class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments', verbose_name=_("Факультет"))
    name = models.CharField(max_length=200, verbose_name=_("Название кафедры"))
    
    total_wage_rate = models.FloatField(
        default=0.0, 
        blank=True, 
        null=True,  
        verbose_name=_("Штатные единицы (ставки)"),
        help_text=_("Сколько ставок выделено на кафедру")
    )
    total_hours_budget = models.IntegerField(
        default=0, 
        blank=True, 
        null=True,
        verbose_name=_("Бюджет часов (годовой)"),
        help_text=_("Общая учебная нагрузка кафедры")
    )

    class Meta:
        verbose_name = _("Кафедра")
        verbose_name_plural = _("Кафедры")
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name

    def get_occupied_hours(self):
        total = 0
        for subject in self.subjects.all():
            total += subject.total_hours
        return total

    def get_load_percentage(self):
        budget = self.total_hours_budget or 0
        if budget > 0:
            return round((self.get_occupied_hours() / budget) * 100, 1)
        return 0

class Specialty(models.Model):
    EDUCATION_LEVEL_CHOICES = [
        ('BACHELOR', _('Бакалавриат')),
        ('MASTER', _('Магистратура')),
        ('DOCTORAL', _('Докторантура')),
        ('POSTGRAD', _('Аспирантура')),
        ('SECOND_HIGHER', _('Второе высшее')),
    ]

    department = models.ForeignKey(
        Department, on_delete=models.CASCADE,
        related_name='specialties', verbose_name=_("Кафедра")
    )
    name = models.CharField(max_length=200, verbose_name=_("Название направления"))

    name_tj = models.CharField(max_length=200, blank=True, verbose_name=_("Название (TJ)"))
    name_ru = models.CharField(max_length=200, blank=True, verbose_name=_("Название (RU)"))
    name_en = models.CharField(max_length=200, blank=True, verbose_name=_("Название (EN)"))

    education_level = models.CharField(
        max_length=20,
        choices=EDUCATION_LEVEL_CHOICES,
        default='BACHELOR',
        verbose_name=_("Ступень образования")
    )
    code = models.CharField(
        max_length=50, unique=True,
        verbose_name=_("Шифр (напр. 400.101.08)")
    )
    qualification = models.CharField(
        max_length=100,
        verbose_name=_("Квалификация (напр. Инженер-программист)")
    )

    class Meta:
        verbose_name = _("Направление")
        verbose_name_plural = _("Направления")
        indexes = [
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        self.name = self.name_ru or self.name_tj or self.name_en or self.name
        super().save(*args, **kwargs)

    def get_display_name(self, lang: str = 'ru') -> str:
        mapping = {'tj': self.name_tj, 'ru': self.name_ru, 'en': self.name_en}
        return mapping.get(lang) or self.name_ru or self.name_tj or self.name_en or self.name


class User(AbstractUser):
    ROLE_CHOICES = [
        ('STUDENT', _('Студент')),
        ('TEACHER', _('Преподаватель')),
        ('HEAD_OF_DEPT', _('Зав. кафедрой')),
        ('VICE_DEAN', _('Зам. декана/директора')),
        ('DEAN', _('Декан')),
        ('PRO_RECTOR', _('Проректор/Зам. директора')),
        ('DIRECTOR', _('Директор/Ректор')),
        ('HR', _('Отдел кадров / Приемная комиссия')), 
        ('SPECIALIST', 'Специалист (УМО/Деканат)'),
        ('METHODIST', _('Методист')),
        ('INSPECTOR', _('Инспектор (Учебная часть)')),
        ('ADVISOR', _('Эдвайзер / Куратор')),
        ('GUEST', 'Гость'),
    ]
    
    CATEGORY_CHOICES = [
        ('PPS', _('ППС (Профессорско-преподавательский)')),
        ('AUP', _('АУП (Административно-управленческий)')),
        ('UVP', _('УВП (Учебно-вспомогательный)')),
        ('BOTH', _('Совместитель (ППС + АУП)')),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT', db_index=True)
    employee_category = models.CharField(
        max_length=10, 
        choices=CATEGORY_CHOICES, 
        default='PPS', 
        verbose_name=_("Категория сотрудника"),
        blank=True
    )
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    birth_date = models.DateField(null=True, blank=True, verbose_name=_("Дата рождения"))
    address = models.TextField(blank=True, verbose_name=_("Адрес проживания"))
    passport_number = models.CharField(max_length=20, blank=True, verbose_name=_("Номер паспорта"))

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_management(self):
        return hasattr(self, 'dean_profile') or hasattr(self, 'vicedean_profile') or hasattr(self, 'prorector_profile') or hasattr(self, 'director_profile') or hasattr(self, 'head_of_dept_profile') or self.is_superuser

    @property
    def is_teacher_role(self):
        return hasattr(self, 'teacher_profile')

    @property
    def is_dean_role(self):
        return hasattr(self, 'dean_profile')
        
    @property
    def is_head_role(self):
        return hasattr(self, 'head_of_dept_profile')
        
    @property
    def is_student_role(self):
        return hasattr(self, 'student_profile')

    @property
    def age(self):
        if self.birth_date:
            today = date.today()
            return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        return None

    def get_actual_category(self):
        has_teacher = hasattr(self, 'teacher_profile')
        has_admin = hasattr(self, 'dean_profile') or hasattr(self, 'vicedean_profile') or hasattr(self, 'director_profile')
        
        if has_teacher and has_admin:
            return 'BOTH'
        elif has_admin:
            return 'AUP'
        elif has_teacher:
            return 'PPS'
        return 'UVP'


class Director(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='director_profile')
    institute = models.ForeignKey('Institute', on_delete=models.SET_NULL, null=True, related_name='directors', verbose_name=_("Возглавляет"))

    class Meta:
        verbose_name = _("Директор/Ректор")
        verbose_name_plural = _("Директоры/Ректоры")

    def __str__(self):
        return f"Директор: {self.user.get_full_name()}"

class ProRector(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='prorector_profile')
    institute = models.ForeignKey(
        Institute, 
        on_delete=models.CASCADE,
        related_name='prorectors',
        verbose_name=_("Институт"),
        null=True,
        blank=True  

    )
    title = models.CharField(max_length=200, verbose_name=_("Должность (напр. Зам. по учебной работе)"))

    class Meta:
        verbose_name = _("Проректор")
        verbose_name_plural = _("Проректоры")

    def __str__(self):
        return f"{self.title}: {self.user.get_full_name()}"

class Dean(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dean_profile')
    faculty = models.OneToOneField(Faculty, on_delete=models.SET_NULL, null=True, related_name='dean_manager')
    contact_email = models.EmailField(blank=True)
    office_location = models.CharField(max_length=200, blank=True)
    reception_hours = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("Декан")
        verbose_name_plural = _("Деканы")

    def __str__(self):
        return f"Декан: {self.user.get_full_name()}"

class ViceDean(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vicedean_profile')
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, related_name='vice_deans')
    title = models.CharField(max_length=200, default="Муовини декан", verbose_name=_("Должность для подписи"))
    area_of_responsibility = models.CharField(max_length=200, blank=True, verbose_name=_("Область ответственности"))

    class Meta:
        verbose_name = _("Зам. декана")
        verbose_name_plural = _("Зам. деканы")

    def __str__(self):
        return f"Зам. декана: {self.user.get_full_name()}"

class HeadOfDepartment(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='head_of_dept_profile')
    department = models.OneToOneField(Department, on_delete=models.SET_NULL, null=True, related_name='head', verbose_name=_("Кафедра"))
    degree = models.CharField(max_length=100, blank=True, verbose_name=_("Ученая степень"))

    class Meta:
        verbose_name = _("Зав. кафедрой")
        verbose_name_plural = _("Зав. кафедрами")

    def __str__(self):
        return f"Зав. каф: {self.user.get_full_name()}"

class KnowledgeArea(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name=_("Название компетенции/специальности"))
    code = models.CharField(max_length=50, blank=True, verbose_name=_("Шифр (если есть)"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))

    class Meta:
        verbose_name = _("Область знаний (Компетенция)")
        verbose_name_plural = _("Области знаний (Компетенции)")
        ordering = ['name']

    def __str__(self):
        return f"{self.code} {self.name}" if self.code else self.name

class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='teachers', verbose_name=_("Основная кафедра"))

    additional_departments = models.ManyToManyField(
        Department,
        blank=True,
        related_name='affiliated_teachers',
        verbose_name=_("Дополнительные кафедры")
    )

    competencies = models.ManyToManyField(
        KnowledgeArea, 
        blank=True, 
        related_name='teachers',
        verbose_name=_("Компетенции (Специализация)")
    )

    degree = models.CharField(max_length=100, blank=True, verbose_name=_("Ученая степень (к.т.н, PhD)"))
    title = models.CharField(max_length=100, blank=True, verbose_name=_("Ученое звание (доцент, профессор)"))
    biography = models.TextField(blank=True)
    research_interests = models.TextField(blank=True)
    consultation_hours = models.CharField(max_length=200, blank=True)
    telegram = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)

    class Meta:
        verbose_name = _("Преподаватель")
        verbose_name_plural = _("Преподаватели")

    def __str__(self):
        return f"{self.user.get_full_name()}"

class Group(models.Model):
    specialty = models.ForeignKey(
        Specialty, 
        on_delete=models.SET_NULL, 
        null=True,                 
        blank=True,                
        related_name='groups', 
        verbose_name=_("Направление")
    )
    curator = models.ForeignKey(
        'Teacher', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='curated_groups', 
        verbose_name=_("Куратор группы")
    )

    SHIFT_CHOICES = [
        ('MORNING', _('Утренняя смена')),
        ('DAY', _('Дневная смена')),
        ('EVENING', _('Вечерняя смена')),
    ]

    name = models.CharField(max_length=50, unique=True, verbose_name=_("Название группы (напр. 400101-А)"))
    course = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(6)], verbose_name=_("Курс"))
    academic_year = models.CharField(max_length=20, verbose_name=_("Учебный год"))
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='MORNING', verbose_name=_("Смена"))
    language = models.CharField(max_length=2, choices=[('TJ', _('TJ')), ('RU', _('RU')), ('EN', _('EN'))], default='RU', verbose_name=_("Язык"))
    has_military_training = models.BooleanField(default=False, verbose_name=_("Военная кафедра"))

    class Meta:
        verbose_name = _("Группа")
        verbose_name_plural = _("Группы")
        indexes = [
            models.Index(fields=['course', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.course} курс)"

class Student(models.Model):
    GENDER_CHOICES = [
        ('M', _('Мужской')),
        ('F', _('Женский')),
    ]

    FINANCING_CHOICES = [
        ('BUDGET', _('Бюджет')),
        ('CONTRACT', _('Контракт')),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', _('Активный')),
        ('ACADEMIC_LEAVE', _('Академический отпуск')),
        ('EXPELLED', _('Отчислен')),
        ('GRADUATED', _('Выпускник')),
    ]

    EDUCATION_TYPE_CHOICES = [
        ('FULL_TIME', _('Очное')),
        ('PART_TIME', _('Заочное')),
        ('EVENING', _('Вечернее')),
    ]

    LANGUAGE_CHOICES = [
        ('TJ', _('Таджикский')),
        ('RU', _('Русский')),
        ('EN', _('Английский')),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    student_id = models.CharField(max_length=20, unique=True, verbose_name=_("Номер зачетки"), db_index=True)

    course = models.IntegerField(default=1)
    admission_year = models.IntegerField(default=default_admission_year)

    financing_type = models.CharField(max_length=20, choices=FINANCING_CHOICES, default='BUDGET')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    education_type = models.CharField(max_length=20, choices=EDUCATION_TYPE_CHOICES, default='FULL_TIME')
    education_language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='RU')
    birth_date = models.DateField(null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    nationality = models.CharField(max_length=50, default='')
    passport_series = models.CharField(max_length=10, default='')
    passport_number = models.CharField(max_length=20, default='')
    passport_issued_by = models.CharField(max_length=200, default='')
    passport_issue_date = models.DateField(null=True)
    registration_address = models.TextField(default='')
    residence_address = models.TextField(default='')
    contract_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Сумма контракта"))
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Оплачено"))

    sponsor_name = models.CharField(max_length=200, blank=True, verbose_name=_("ФИО спонсора"))
    sponsor_phone = models.CharField(max_length=20, blank=True, verbose_name=_("Телефон спонсора"))
    sponsor_relation = models.CharField(max_length=50, blank=True, verbose_name=_("Отношение спонсора"))
    specialty = models.ForeignKey('Specialty', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Специальность (Направление)"))
    specialization = models.ForeignKey('Specialization', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Специализация (Профиль)"))
    middle_name = models.CharField(max_length=150, blank=True, verbose_name=_("Отчество"))
    place_of_birth = models.CharField(max_length=255, blank=True, verbose_name=_("Место рождения"))
    
    prev_education_type = models.CharField(max_length=100, blank=True, verbose_name=_("Вид уч. заведения"))
    prev_education_institution = models.CharField(max_length=255, blank=True, verbose_name=_("Учебное заведение"))
    prev_education_year = models.IntegerField(null=True, blank=True, verbose_name=_("Год окончания"))
    doc_type = models.CharField(max_length=100, blank=True, verbose_name=_("Тип документа (Аттестат/Диплом)"))
    doc_number = models.CharField(max_length=50, blank=True, verbose_name=_("Серия/номер документа"))
    doc_date = models.DateField(null=True, blank=True, verbose_name=_("Дата получения документа"))
    
    personal_file_number = models.CharField(max_length=50, blank=True, verbose_name=_("Номер личного дела"))
    notes = models.TextField(blank=True, verbose_name=_("Примечание"))

    def get_debt(self):
        return self.contract_amount - self.paid_amount
    
    def payment_status(self):
        if self.financing_type == 'BUDGET':
            return 'Бюджет'
        debt = self.get_debt()
        if debt <= 0:
            return 'Оплачено'
        if self.paid_amount == 0:
            return 'Не оплачено'
        return 'Частично'

    class Meta:
        verbose_name = _("Студент")
        verbose_name_plural = _("Студенты")
        ordering = ['course', 'group', 'user__last_name']

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_id})"

    def get_average_grade(self):
        try:
            if hasattr(self, 'statistics'):
                return round(self.statistics.overall_gpa, 2)
            return 0.0
        except Exception:
            return 0.0

    def get_total_absent(self):
        try:
            if hasattr(self, 'statistics'):
                return self.statistics.total_absent
                
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            return stats.total_absent
        except Exception:
            return 0

    def get_absent_breakdown(self):
        try:
            if hasattr(self, 'statistics'):
                stats = self.statistics
            else:
                from journal.models import StudentStatistics
                stats, _ = StudentStatistics.objects.get_or_create(student=self)
                
            return {
                'illness': stats.absent_illness,
                'valid': stats.absent_valid,
                'invalid': stats.absent_invalid,
                'total': stats.total_absent
            }
        except Exception:
            return {'illness': 0, 'valid': 0, 'invalid': 0, 'total': 0}

    def get_attendance_percentage(self):
        try:
            if hasattr(self, 'statistics'):
                return round(self.statistics.attendance_percentage, 1)
                
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            return round(stats.attendance_percentage, 1)
        except Exception:
            return 0.0

    def get_group_rank(self):
        try:
            if hasattr(self, 'statistics'):
                return self.statistics.group_rank
                
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            return stats.group_rank
        except Exception:
            return 0



class SpecialistProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='specialist_profile')
    faculty = models.ForeignKey('Faculty', on_delete=models.CASCADE, related_name='specialists', verbose_name="Факультет")
    
    class Meta:
        verbose_name = "Специалист"
        verbose_name_plural = "Специалисты"

    def __str__(self):
        return f"Специалист: {self.user.get_full_name()} ({self.faculty.name})"




class GroupTransferHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='transfer_history')
    from_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, related_name='transfers_from')
    to_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, related_name='transfers_to')
    transfer_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)
    transferred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = _("История переводов")
        verbose_name_plural = _("История переводов")
        ordering = ['-transfer_date']

    def __str__(self):
        return f"{self.student}: {self.from_group} → {self.to_group}"

class StructureChangeLog(models.Model):
    OBJECT_TYPES = [
        ('INSTITUTE', _('Институт')),
        ('FACULTY', _('Факультет')),
        ('DEPARTMENT', _('Кафедра')),
    ]
    
    object_type = models.CharField(max_length=20, choices=OBJECT_TYPES)
    object_id = models.IntegerField()
    object_name = models.CharField(max_length=200, verbose_name=_("Текущее название"))
    
    field_changed = models.CharField(max_length=50, verbose_name=_("Поле"))
    old_value = models.TextField(verbose_name=_("Старое значение"))
    new_value = models.TextField(verbose_name=_("Новое значение"))
    
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = _("История структуры")
        verbose_name_plural = _("История структуры")
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.object_type} {self.object_name}: {self.old_value} -> {self.new_value}"





class Order(models.Model):
    ORDER_TYPES = [
        ('ENROLL', _('Зачисление')),
        ('EXPEL', _('Отчисление')),
        ('ACADEMIC_LEAVE', _('Академический отпуск')),
        ('RESTORE', _('Восстановление')),
        ('GRADUATE', _('Выпуск')),
        ('TRANSFER', _('Перевод в другую группу/вуз')), 
    ]

    STATUS_CHOICES = [
        ('DRAFT', _('Проект (На подписи)')),
        ('APPROVED', _('Подписан (Утвержден)')),
        ('REJECTED', _('Отклонен')),
    ]

    number = models.CharField(max_length=50, unique=True, verbose_name=_('Номер приказа'), blank=True)
    date = models.DateField(default=timezone.now, verbose_name=_("Дата приказа"))
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES, verbose_name=_("Тип приказа"))
    title = models.CharField(max_length=255, verbose_name=_("Заголовок (например: О переводе студентов 2 курса)"))
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name=_("Статус"))
    file = models.FileField(upload_to='orders/', blank=True, null=True, verbose_name=_("Скан приказа"))

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_orders')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_orders')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Приказ (Массовый)")
        verbose_name_plural = _("Приказы (Фармонҳо)")
        ordering = ['-date']

    def __str__(self):
        return f"Приказ №{self.number} от {self.date.strftime('%d.%m.%Y')} ({self.get_order_type_display()})"

    def save(self, *args, **kwargs):
        if not self.number:
            year = timezone.now().year
            prefix = f"{year}-"
            for attempt in range(3):
                try:
                    with transaction.atomic():
                        last_order = Order.objects.select_for_update().filter(
                            number__startswith=prefix
                        ).order_by('-number').first()
                        if last_order and last_order.number:
                            try:
                                last_num = int(last_order.number.split('-')[-1])
                                new_num = last_num + 1
                            except (ValueError, IndexError):
                                new_num = 1
                        else:
                            new_num = 1
                        self.number = f"{year}-{new_num:04d}"
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    if attempt == 2:
                        raise
                    continue
            return
        super().save(*args, **kwargs)

    def apply_effect(self, approver_user):
            if self.status == 'APPROVED':
                return

            with transaction.atomic():
                groups_to_recalc = set() 

                for item in self.items.all():
                    student = item.student
                    old_group = student.group
                    if old_group:
                        groups_to_recalc.add(old_group)

                    if self.order_type == 'EXPEL':
                        if old_group:
                            GroupTransferHistory.objects.create(
                                student=student,
                                from_group=old_group,
                                to_group=None,
                                reason=f'Отчисление по приказу №{self.number} от {self.date.strftime("%d.%m.%Y")}',
                                transferred_by=approver_user
                            )
                        student.status = 'EXPELLED'
                        student.group = None
                    elif self.order_type == 'ACADEMIC_LEAVE':
                        student.status = 'ACADEMIC_LEAVE'
                    elif self.order_type == 'GRADUATE':
                        if old_group:
                            GroupTransferHistory.objects.create(
                                student=student,
                                from_group=old_group,
                                to_group=None,
                                reason=f'Выпуск по приказу №{self.number} от {self.date.strftime("%d.%m.%Y")}',
                                transferred_by=approver_user
                            )
                        student.status = 'GRADUATED'
                        student.group = None
                    elif self.order_type == 'ENROLL':
                        student.status = 'ACTIVE'
                        if item.target_group:
                            student.group = item.target_group
                            groups_to_recalc.add(item.target_group)
                    elif self.order_type == 'RESTORE':
                        student.status = 'ACTIVE'
                    elif self.order_type == 'TRANSFER':
                        if item.target_group:
                            GroupTransferHistory.objects.create(
                                student=student,
                                from_group=old_group,
                                to_group=item.target_group,
                                reason=item.reason,
                                transferred_by=approver_user
                            )
                            student.group = item.target_group
                            groups_to_recalc.add(item.target_group)
                    student.save()

                self.status = 'APPROVED'
                self.approved_by = approver_user
                self.save()

                from journal.models import StudentStatistics
                for g in groups_to_recalc:
                    StudentStatistics.recalculate_group(g)




class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='order_items')
    target_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Новая группа (для перевода)"))
    reason = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Основание (заявление, документ)")
    )

    def __str__(self):
        return f"{self.student.user.get_full_name()} -> {self.order.number}"



class HRProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='hr_profile')
    department_name = models.CharField(max_length=200, default="Отдел кадров", verbose_name=_("Название отдела"))
    
    class Meta:
        verbose_name = _("Сотрудник отдела кадров")
        verbose_name_plural = _("Сотрудники отдела кадров")
        
    def __str__(self):
        return f"{self.department_name}: {self.user.get_full_name()}"


class DocumentTemplate(models.Model):
    CONTEXT_TYPES = [
        ('STUDENT_CERT', _('Справка с места учебы (Студент)')),
        ('STUDENT_ORDER', _('Приказ по студенту (Отчисление/Перевод)')),
        ('EXAM_SHEET', _('Экзаменационная ведомость (Группа + Предмет)')), 
    ]
    
    name = models.CharField(max_length=200, verbose_name=_("Название шаблона (например: Справка в военкомат)"))
    context_type = models.CharField(max_length=50, choices=CONTEXT_TYPES, verbose_name=_("Тип данных"))
    
    file = models.FileField(
        upload_to='document_templates/', 
        validators=[FileExtensionValidator(allowed_extensions=['docx'])],
        verbose_name=_("Файл шаблона (.docx)")
    )
    
    is_active = models.BooleanField(default=True, verbose_name=_("Активен"))
    created_at = models.DateTimeField(auto_now_add=True)
    
    institute = models.ForeignKey('Institute', on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("Институт"))

    class Meta:
        verbose_name = _("Шаблон документа")
        verbose_name_plural = _("Шаблоны документов")

    def __str__(self):
        return f"{self.name} ({self.get_context_type_display()})"

class Specialization(models.Model):
    specialty = models.ForeignKey(Specialty, on_delete=models.CASCADE, related_name='specializations', verbose_name=_("Специальность"))
    name = models.CharField(max_length=200, verbose_name=_("Название специализации (профиля)"))
    code = models.CharField(max_length=50, blank=True, verbose_name=_("Шифр профиля"))

    class Meta:
        verbose_name = _("Специализация")
        verbose_name_plural = _("Специализации")

    def __str__(self):
        return f"{self.name} ({self.specialty.code})"

class Diploma(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='diploma', verbose_name=_("Студент"))
    number = models.CharField(max_length=50, unique=True, verbose_name=_("Номер диплома"))
    issue_date = models.DateField(default=timezone.now, verbose_name=_("Дата выдачи"))
    file = models.FileField(upload_to='diplomas/', blank=True, null=True, verbose_name=_("Скан диплома"))

    class Meta:
        verbose_name = _("Диплом")
        verbose_name_plural = _("Дипломы")

    def __str__(self):
        return f"Диплом №{self.number} - {self.student.user.get_full_name()}"






class AdmissionPlan(models.Model):
    """
    План приёма студентов на специальность.
    Количество фактически зачисленных считается ТОЛЬКО на лету (enrolled_count),
    никакого денормализованного поля — исключаем рассинхронизацию.
    """
    STUDY_FORM_CHOICES = [
        ('FULL_TIME', _('Очная')),
        ('PART_TIME', _('Заочная')),
        ('DISTANCE', _('Дистанционная')),
    ]
    FINANCING_TYPE_CHOICES = [
        ('BUDGET', _('Бюджет')),
        ('CONTRACT', _('Контракт')),
        ('QUOTA', _('Квота')),
        ('GRANT', _('Грант')),
    ]
    LANGUAGE_CHOICES = [
        ('TJ', 'TJ'),
        ('RU', 'RU'),
        ('EN', 'EN'),
    ]

    specialty = models.ForeignKey(
        'Specialty', on_delete=models.CASCADE,
        related_name='admission_plans',
        verbose_name=_("Специальность")
    )
    academic_year = models.CharField(
        max_length=20, verbose_name=_("Учебный год"),
        help_text=_("Формат: 2024-2025")
    )
    study_form = models.CharField(
        max_length=20, choices=STUDY_FORM_CHOICES,
        default='FULL_TIME', verbose_name=_("Форма обучения")
    )
    financing_type = models.CharField(
        max_length=20, choices=FINANCING_TYPE_CHOICES,
        default='BUDGET', verbose_name=_("Источник финансирования")
    )
    education_language = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES,
        default='TJ', verbose_name=_("Язык обучения")
    )
    target_quota = models.IntegerField(
        default=0, verbose_name=_("Плановое число мест"),
        help_text=_("Количество мест по плану набора")
    )
    foreign_tuition_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_("Стоимость обучения (иностр. валюта)"),
        help_text=_("Для иностранных студентов, в USD")
    )

    class Meta:
        verbose_name = _("План приёма")
        verbose_name_plural = _("Планы приёма")
        ordering = ['-academic_year', 'specialty__code']
        unique_together = [
            ['specialty', 'academic_year', 'study_form', 'financing_type', 'education_language']
        ]
        indexes = [
            models.Index(fields=['academic_year']),
            models.Index(fields=['specialty', 'academic_year']),
        ]

    def __str__(self):
        return (
            f"{self.specialty.code} | {self.academic_year} | "
            f"{self.get_study_form_display()} | {self.get_financing_type_display()} | "
            f"{self.education_language}"
        )

    
    
    _STUDY_FORM_MAP = {
        'FULL_TIME': 'FULL_TIME',
        'PART_TIME': 'PART_TIME',
        'DISTANCE': 'EVENING',
    }
    
    
    _FINANCING_MAP = {
        'BUDGET': 'BUDGET',
        'CONTRACT': 'CONTRACT',
        'QUOTA': 'BUDGET',
        'GRANT': 'BUDGET',
    }

    def get_enrolled_count(self) -> int:
        from .models import Student  
        return Student.objects.filter(
            specialty=self.specialty,
            status='ACTIVE',
            education_type=self._STUDY_FORM_MAP.get(self.study_form, 'FULL_TIME'),
            education_language=self.education_language,
            financing_type=self._FINANCING_MAP.get(self.financing_type, 'BUDGET'),
        ).count()

    def get_fulfillment_percent(self) -> float:
        if not self.target_quota:
            return 0.0
        return round(self.get_enrolled_count() / self.target_quota * 100, 1)





