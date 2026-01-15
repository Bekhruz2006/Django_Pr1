from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import datetime

# --- СТРУКТУРА УНИВЕРСИТЕТА ---

class Institute(models.Model):
    """Институт (Верхний уровень)"""
    name = models.CharField(max_length=200, verbose_name="Название института")
    abbreviation = models.CharField(max_length=20, verbose_name="Аббревиатура")
    address = models.TextField(verbose_name="Адрес", blank=True)

    class Meta:
        verbose_name = "Институт"
        verbose_name_plural = "Институты"

    def __str__(self):
        return self.name

class Faculty(models.Model):
    """Факультет"""
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
    """Кафедра"""
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments', verbose_name="Факультет")
    name = models.CharField(max_length=200, verbose_name="Название кафедры")

    class Meta:
        verbose_name = "Кафедра"
        verbose_name_plural = "Кафедры"
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name

class Specialty(models.Model):
    """Направление (Специальность)"""
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

# --- ПОЛЬЗОВАТЕЛИ ---

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

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT', db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_management(self):
        return self.role in ['DEAN', 'VICE_DEAN', 'PRO_RECTOR', 'DIRECTOR', 'HEAD_OF_DEPT'] or self.is_superuser

class Director(models.Model):
    """Директор института или Ректор"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='director_profile')
    institute = models.ForeignKey(Institute, on_delete=models.SET_NULL, null=True, related_name='directors', verbose_name="Возглавляет")

    def __str__(self):
        return f"Директор: {self.user.get_full_name()}"

class ProRector(models.Model):
    """Проректоры / Заместители директора"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='prorector_profile')
    institute = models.ForeignKey(Institute, on_delete=models.SET_NULL, null=True, related_name='prorectors')
    title = models.CharField(max_length=200, verbose_name="Должность (напр. Зам. по учебной работе)")

    def __str__(self):
        return f"{self.title}: {self.user.get_full_name()}"

class Dean(models.Model):
    """Декан факультета"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dean_profile')
    faculty = models.OneToOneField(Faculty, on_delete=models.SET_NULL, null=True, related_name='dean_manager')
    contact_email = models.EmailField(blank=True)
    office_location = models.CharField(max_length=200, blank=True)
    reception_hours = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Декан: {self.user.get_full_name()}"

class ViceDean(models.Model):
    """Зам. декана"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vicedean_profile')
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, related_name='vice_deans')
    title = models.CharField(max_length=200, default="Муовини декан", verbose_name="Должность для подписи")
    area_of_responsibility = models.CharField(max_length=200, verbose_name="Область ответственности")

    def __str__(self):
        return f"Зам. декана: {self.user.get_full_name()}"

class HeadOfDepartment(models.Model):
    """Заведующий кафедрой"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='head_of_dept_profile')
    department = models.OneToOneField(Department, on_delete=models.SET_NULL, null=True, related_name='head', verbose_name="Кафедра")
    degree = models.CharField(max_length=100, blank=True, verbose_name="Ученая степень")

    def __str__(self):
        return f"Зав. каф: {self.user.get_full_name()}"

class Teacher(models.Model):
    """Преподаватель"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='teachers', verbose_name="Кафедра")

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
    """Учебная группа"""
    specialty = models.ForeignKey(Specialty, on_delete=models.CASCADE, related_name='groups', verbose_name="Направление")
    name = models.CharField(max_length=50, unique=True, verbose_name="Название группы (напр. 400101-А)")
    course = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(6)], verbose_name="Курс")
    academic_year = models.CharField(max_length=20, verbose_name="Учебный год")
    language = models.CharField(max_length=2, choices=[('TJ', 'TJ'), ('RU', 'RU'), ('EN', 'EN')], default='RU', verbose_name="Язык")

    # ✅ НОВОЕ ПОЛЕ
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
    """Студент"""
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
    """История переводов студентов"""
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

# Сигналы создания профилей
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
