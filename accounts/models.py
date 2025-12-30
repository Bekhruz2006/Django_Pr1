from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import datetime

class User(AbstractUser):
    ROLE_CHOICES = [
        ('STUDENT', 'Студент'),
        ('TEACHER', 'Преподаватель'),
        ('DEAN', 'Декан'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Group(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Название группы")
    course = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Курс")
    academic_year = models.IntegerField(verbose_name="Год обучения")
    specialty = models.CharField(max_length=200, verbose_name="Специальность")
    
    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        ordering = ['course', 'name']
    
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
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='students', verbose_name="Группа")
    
    student_id = models.CharField(max_length=20, unique=True, verbose_name="Номер зачетки")
    course = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Курс")
    specialty = models.CharField(max_length=200, verbose_name="Специальность")
    admission_year = models.IntegerField(verbose_name="Год поступления")
    
    financing_type = models.CharField(max_length=10, choices=FINANCING_CHOICES, verbose_name="Тип финансирования")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Статус")
    education_type = models.CharField(max_length=10, choices=EDUCATION_TYPE_CHOICES, default='FULL_TIME', verbose_name="Вид обучения")
    education_language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, verbose_name="Язык обучения")
    
    birth_date = models.DateField(verbose_name="Дата рождения")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, verbose_name="Пол")
    nationality = models.CharField(max_length=50, verbose_name="Национальность")
    
    passport_series = models.CharField(max_length=10, verbose_name="Серия паспорта")
    passport_number = models.CharField(max_length=20, verbose_name="Номер паспорта")
    passport_issued_by = models.CharField(max_length=200, verbose_name="Кем выдан")
    passport_issue_date = models.DateField(verbose_name="Дата выдачи")
    
    registration_address = models.TextField(verbose_name="Адрес регистрации")
    residence_address = models.TextField(verbose_name="Адрес проживания")
    
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
            return stats.overall_gpa
        except Exception:
            return 0.0
    def get_total_absent(self):
        
        try:
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            return stats.total_absent
        except Exception:
            return 0  
    def get_group_rank(self):
        try:
            from journal.models import StudentStatistics
            stats, _ = StudentStatistics.objects.get_or_create(student=self)
            return stats.group_rank
        except Exception:
            return 0

class Teacher(models.Model):
    DEGREE_CHOICES = [
        ('NONE', 'Без степени'),
        ('CANDIDATE', 'Кандидат наук'),
        ('DOCTOR', 'Доктор наук'),
    ]
    
    TITLE_CHOICES = [
        ('NONE', 'Без звания'),
        ('ASSISTANT', 'Ассистент'),
        ('SENIOR_TEACHER', 'Старший преподаватель'),
        ('DOCENT', 'Доцент'),
        ('PROFESSOR', 'Профессор'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    
    degree = models.CharField(max_length=20, choices=DEGREE_CHOICES, default='NONE', verbose_name="Ученая степень")
    title = models.CharField(max_length=20, choices=TITLE_CHOICES, default='NONE', verbose_name="Ученое звание")
    
    biography = models.TextField(blank=True, verbose_name="Биография")
    research_interests = models.TextField(blank=True, verbose_name="Научные интересы")
    
    consultation_hours = models.CharField(max_length=200, blank=True, verbose_name="Часы консультаций")
    telegram = models.CharField(max_length=100, blank=True, verbose_name="Telegram")
    contact_email = models.EmailField(blank=True, verbose_name="Email для связи")
    
    class Meta:
        verbose_name = "Преподаватель"
        verbose_name_plural = "Преподаватели"
        ordering = ['user__last_name']
    
    def __str__(self):
        return f"{self.get_degree_display()} {self.user.get_full_name()}"

class Dean(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dean_profile')
    
    office_location = models.CharField(max_length=200, blank=True, verbose_name="Местоположение офиса")
    reception_hours = models.CharField(max_length=200, blank=True, verbose_name="Часы приема")
    contact_email = models.EmailField(blank=True, verbose_name="Email для связи")
    
    class Meta:
        verbose_name = "Декан"
        verbose_name_plural = "Деканы"
    
    def __str__(self):
        return f"Декан: {self.user.get_full_name()}"

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