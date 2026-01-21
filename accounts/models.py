from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import datetime, date

class Institute(models.Model):
    name = models.CharField(max_length=200, verbose_name="Название института")
    abbreviation = models.CharField(max_length=20, verbose_name="Аббревиатура")
    address = models.TextField(verbose_name="Адрес", blank=True)

    class Meta:
        verbose_name = "Институт"
        verbose_name_plural = "Институты"

    def __str__(self):
        return self.name

class Faculty(models.Model):
    institute = models.ForeignKey(Institute, on_delete=models.CASCADE, related_name='faculties', verbose_name="Институт")
    name = models.CharField(max_length=200, verbose_name="Название факультета")
    code = models.CharField(max_length=50, unique=True, verbose_name="Код факультета")

    class Meta:
        verbose_name = "Факультет"
        verbose_name_plural = "Факультеты"
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.institute.abbreviation})"

class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments', verbose_name="Факультет")
    name = models.CharField(max_length=200, verbose_name="Название кафедры")
    
    total_wage_rate = models.FloatField(
        default=0.0, 
        blank=True, 
        null=True,  
        verbose_name="Штатные единицы (ставки)",
        help_text="Сколько ставок выделено на кафедру"
    )
    total_hours_budget = models.IntegerField(
        default=0, 
        blank=True, 
        null=True,
        verbose_name="Бюджет часов (годовой)",
        help_text="Общая учебная нагрузка кафедры"
    )

    class Meta:
        verbose_name = "Кафедра"
        verbose_name_plural = "Кафедры"
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
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='specialties', verbose_name="Кафедра")
    name = models.CharField(max_length=200, verbose_name="Название направления")
    code = models.CharField(max_length=50, unique=True, verbose_name="Шифр (напр. 400.101.08)")
    qualification = models.CharField(max_length=100, verbose_name="Квалификация (напр. Инженер-программист)")

    class Meta:
        verbose_name = "Направление"
        verbose_name_plural = "Направления"
        indexes = [
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class User(AbstractUser):
    ROLE_CHOICES = [
        ('STUDENT', 'Студент'),
        ('TEACHER', 'Преподаватель'),
        ('HEAD_OF_DEPT', 'Зав. кафедрой'),
        ('VICE_DEAN', 'Зам. декана/директора'),
        ('DEAN', 'Декан'),
        ('PRO_RECTOR', 'Проректор/Зам. директора'),
        ('DIRECTOR', 'Директор/Ректор'),
    ]
    
    CATEGORY_CHOICES = [
        ('PPS', 'ППС (Профессорско-преподавательский)'),
        ('AUP', 'АУП (Административно-управленческий)'),
        ('UVP', 'УВП (Учебно-вспомогательный)'),
        ('BOTH', 'Совместитель (ППС + АУП)'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT', db_index=True)
    employee_category = models.CharField(
        max_length=10, 
        choices=CATEGORY_CHOICES, 
        default='PPS', 
        verbose_name="Категория сотрудника",
        blank=True
    )
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    birth_date = models.DateField(null=True, blank=True, verbose_name="Дата рождения")
    address = models.TextField(blank=True, verbose_name="Адрес проживания")
    passport_number = models.CharField(max_length=20, blank=True, verbose_name="Номер паспорта")

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_management(self):
        return self.role in ['DEAN', 'VICE_DEAN', 'PRO_RECTOR', 'DIRECTOR', 'HEAD_OF_DEPT'] or self.is_superuser

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
    institute = models.ForeignKey('Institute', on_delete=models.SET_NULL, null=True, related_name='directors', verbose_name="Возглавляет")

    def __str__(self):
        return f"Директор: {self.user.get_full_name()}"

class ProRector(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='prorector_profile')
    institute = models.ForeignKey(Institute, on_delete=models.SET_NULL, null=True, related_name='prorectors')
    title = models.CharField(max_length=200, verbose_name="Должность (напр. Зам. по учебной работе)")

    def __str__(self):
        return f"{self.title}: {self.user.get_full_name()}"

class Dean(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dean_profile')
    faculty = models.OneToOneField(Faculty, on_delete=models.SET_NULL, null=True, related_name='dean_manager')
    contact_email = models.EmailField(blank=True)
    office_location = models.CharField(max_length=200, blank=True)
    reception_hours = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Декан: {self.user.get_full_name()}"

class ViceDean(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vicedean_profile')
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, related_name='vice_deans')
    title = models.CharField(max_length=200, default="Муовини декан", verbose_name="Должность для подписи")
    area_of_responsibility = models.CharField(max_length=200, blank=True, verbose_name="Область ответственности")

    def __str__(self):
        return f"Зам. декана: {self.user.get_full_name()}"

class HeadOfDepartment(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='head_of_dept_profile')
    department = models.OneToOneField(Department, on_delete=models.SET_NULL, null=True, related_name='head', verbose_name="Кафедра")
    degree = models.CharField(max_length=100, blank=True, verbose_name="Ученая степень")

    def __str__(self):
        return f"Зав. каф: {self.user.get_full_name()}"

class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='teachers', verbose_name="Основная кафедра")

    additional_departments = models.ManyToManyField(
        Department,
        blank=True,
        related_name='affiliated_teachers',
        verbose_name="Дополнительные кафедры"
    )

    degree = models.CharField(max_length=100, blank=True, verbose_name="Ученая степень (к.т.н, PhD)")
    title = models.CharField(max_length=100, blank=True, verbose_name="Ученое звание (доцент, профессор)")
    biography = models.TextField(blank=True)
    research_interests = models.TextField(blank=True)
    consultation_hours = models.CharField(max_length=200, blank=True)
    telegram = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()}"

class Group(models.Model):
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT, related_name='groups', verbose_name="Направление")
    name = models.CharField(max_length=50, unique=True, verbose_name="Название группы (напр. 400101-А)")
    course = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(6)], verbose_name="Курс")
    academic_year = models.CharField(max_length=20, verbose_name="Учебный год")
    language = models.CharField(max_length=2, choices=[('TJ', 'TJ'), ('RU', 'RU'), ('EN', 'EN')], default='RU', verbose_name="Язык")
    has_military_training = models.BooleanField(default=False, verbose_name="Военная кафедра")

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        indexes = [
            models.Index(fields=['course', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.course} курс)"

class Student(models.Model):
    GENDER_CHOICES = [
        ('M', 'Мужской'),
        ('F', 'Женский'),
    ]

    FINANCING_CHOICES = [
        ('BUDGET', 'Бюджет'),
        ('CONTRACT', 'Контракт'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Активный'),
        ('ACADEMIC_LEAVE', 'Академический отпуск'),
        ('EXPELLED', 'Отчислен'),
    ]

    EDUCATION_TYPE_CHOICES = [
        ('FULL_TIME', 'Очное'),
        ('PART_TIME', 'Заочное'),
        ('EVENING', 'Вечернее'),
    ]

    LANGUAGE_CHOICES = [
        ('TJ', 'Таджикский'),
        ('RU', 'Русский'),
        ('EN', 'Английский'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    student_id = models.CharField(max_length=20, unique=True, verbose_name="Номер зачетки", db_index=True)

    course = models.IntegerField(default=1)
    admission_year = models.IntegerField(default=2025)

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

    sponsor_name = models.CharField(max_length=200, blank=True, verbose_name="ФИО спонсора")
    sponsor_phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон спонсора")
    sponsor_relation = models.CharField(max_length=50, blank=True, verbose_name="Отношение спонсора")

    class Meta:
        verbose_name = "Студент"
        verbose_name_plural = "Студенты"
        ordering = ['course', 'group', 'user__last_name']

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_id})"

    def get_average_grade(self):
        try:
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            stats.recalculate()
            return round(stats.overall_gpa, 2)
        except Exception:
            return 0.0

    def get_total_absent(self):
        try:
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            stats.recalculate()
            return stats.total_absent
        except Exception:
            return 0

    def get_absent_breakdown(self):
        try:
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            stats.recalculate()
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
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            stats.recalculate()
            return round(stats.attendance_percentage, 1)
        except Exception:
            return 0.0

    def get_group_rank(self):
        try:
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            stats.recalculate()
            return stats.group_rank
        except Exception:
            return 0

class GroupTransferHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='transfer_history')
    from_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, related_name='transfers_from')
    to_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, related_name='transfers_to')
    transfer_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)
    transferred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "История переводов"
        verbose_name_plural = "История переводов"
        ordering = ['-transfer_date']

    def __str__(self):
        return f"{self.student}: {self.from_group} → {self.to_group}"


class StructureChangeLog(models.Model):
    """Лог изменений названий и структуры"""
    OBJECT_TYPES = [
        ('INSTITUTE', 'Институт'),
        ('FACULTY', 'Факультет'),
        ('DEPARTMENT', 'Кафедра'),
    ]
    
    object_type = models.CharField(max_length=20, choices=OBJECT_TYPES)
    object_id = models.IntegerField()
    object_name = models.CharField(max_length=200, verbose_name="Текущее название")
    
    field_changed = models.CharField(max_length=50, verbose_name="Поле")
    old_value = models.TextField(verbose_name="Старое значение")
    new_value = models.TextField(verbose_name="Новое значение")
    
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "История структуры"
        verbose_name_plural = "История структуры"
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.object_type} {self.object_name}: {self.old_value} -> {self.new_value}"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == 'STUDENT':
            year = datetime.now().year
            Student.objects.create(user=instance, student_id=f"{year}S{instance.id:05d}")
        elif instance.role == 'TEACHER':
            Teacher.objects.create(user=instance)
        elif instance.role == 'DEAN':
            Dean.objects.create(user=instance)
        elif instance.role == 'VICE_DEAN':
            ViceDean.objects.create(user=instance)
        elif instance.role == 'DIRECTOR':
            Director.objects.create(user=instance)
        elif instance.role == 'PRO_RECTOR':
            ProRector.objects.create(user=instance, title="Заместитель директора")
        elif instance.role == 'HEAD_OF_DEPT':
            HeadOfDepartment.objects.create(user=instance)


@receiver(pre_save, sender=Faculty)
def log_faculty_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Faculty.objects.get(pk=instance.pk)
            if old_instance.name != instance.name:
                StructureChangeLog.objects.create(
                    object_type='FACULTY',
                    object_id=instance.pk,
                    object_name=instance.name,
                    field_changed='name',
                    old_value=old_instance.name,
                    new_value=instance.name
                )
        except Faculty.DoesNotExist:
            pass


@receiver(pre_save, sender=Department)
def log_department_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Department.objects.get(pk=instance.pk)
            if old_instance.name != instance.name:
                StructureChangeLog.objects.create(
                    object_type='DEPARTMENT',
                    object_id=instance.pk,
                    object_name=instance.name,
                    field_changed='name',
                    old_value=old_instance.name,
                    new_value=instance.name
                )
        except Department.DoesNotExist:
            pass
