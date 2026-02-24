from django.db import models
from accounts.models import User, Faculty

class CourseCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название категории")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Категория курса"
        verbose_name_plural = "Категории курсов"

class Course(models.Model):
    category = models.ForeignKey(CourseCategory, on_delete=models.CASCADE, related_name='courses')
    full_name = models.CharField(max_length=255, verbose_name="Полное название курса")
    short_name = models.CharField(max_length=100, verbose_name="Краткое название")
    id_number = models.CharField(max_length=100, blank=True, verbose_name="Идентификационный номер")
    
    summary = models.TextField(blank=True, verbose_name="Описание курса")
    is_visible = models.BooleanField(default=True, verbose_name="Видимость курса")
    
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

class CourseEnrolment(models.Model):
    ROLE_CHOICES = [
        ('STUDENT', 'Студент'),
        ('TEACHER', 'Преподаватель (Ассистент)'),
        ('MANAGER', 'Управляющий курсом'),
    ]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrolments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_enrolments')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['course', 'user']

class CourseSection(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=255, verbose_name="Название (Неделя/Тема)")
    summary = models.TextField(blank=True)
    sequence = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ['sequence']

class CourseModule(models.Model):
    MODULE_TYPES = [
        ('RESOURCE', 'Файл/Страница/Папка'),
        ('ASSIGNMENT', 'Задание (КМД)'),
        ('QUIZ', 'Тест'),
        ('FORUM', 'Форум/Объявления'),
        ('URL', 'Внешняя ссылка / Видеоконференция'),
        ('FEEDBACK', 'Обратная связь / Опрос'),
        ('GLOSSARY', 'Глоссарий'),
    ]
    
    section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name='modules')
    module_type = models.CharField(max_length=20, choices=MODULE_TYPES)
    title = models.CharField(max_length=255)
    sequence = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    

    class Meta:
        ordering = ['sequence']

class ModuleCondition(models.Model):
    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='conditions')
    depends_on_module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='dependents')
    min_score = models.FloatField(null=True, blank=True, verbose_name="Минимальный балл")
    must_be_completed = models.BooleanField(default=True)


class Assignment(models.Model):
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='assignment_detail')
    description = models.TextField()
    allow_submissions_from = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    max_score = models.FloatField(default=100.0)

class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='submissions/')
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.FloatField(null=True, blank=True)
    teacher_feedback = models.TextField(blank=True)


class Resource(models.Model):
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='resource_detail')
    content = models.TextField(blank=True, verbose_name="Текст страницы (HTML)")
    file = models.FileField(upload_to='course_resources/', null=True, blank=True)
    display_type = models.CharField(max_length=20, choices=[
        ('EMBED', 'Встроить на страницу'),
        ('DOWNLOAD', 'Принудительное скачивание'),
        ('PAGE', 'Веб-страница (текст)'),
    ], default='DOWNLOAD')

class UrlResource(models.Model):
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='url_detail')
    external_url = models.URLField(verbose_name="Ссылка")
    open_in_new_window = models.BooleanField(default=True)
