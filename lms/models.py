from django.db import models
from accounts.models import Teacher, Group
from schedule.models import Subject, Subgroup

class CourseWorkspace(models.Model):
    """
    Рабочее пространство курса (Аналог 'course' в Moodle).
    Уникальное пространство для связки Предмет + Преподаватель + Группа (или Подгруппа).
    """
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='workspaces', verbose_name="Предмет")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='workspaces', verbose_name="Преподаватель")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='workspaces', verbose_name="Группа")
    
    # Логика подгрупп
    is_subgroup = models.BooleanField(default=False, verbose_name="Это подгруппа?")
    subgroup = models.ForeignKey(Subgroup, on_delete=models.CASCADE, null=True, blank=True, related_name='workspaces', verbose_name="Связь с подгруппой")
    subgroup_name = models.CharField(max_length=100, blank=True, verbose_name="Имя подгруппы (Текстом)")

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Рабочее пространство"
        verbose_name_plural = "Рабочие пространства"
        unique_together = ['subject', 'group', 'subgroup'] # Один воркспейс на конкретную сущность

    def __str__(self):
        target = self.subgroup_name if self.is_subgroup else self.group.name
        return f"{self.subject.name} | {target} | {self.teacher.user.get_last_name()}"


class CourseSection(models.Model):
    """
    Секция курса (Аналог 'course_sections' в Moodle).
    Может быть Неделей или Темой. Сюда же можно привязывать тип занятия (Лекция/Практика).
    """
    workspace = models.ForeignKey(CourseWorkspace, on_delete=models.CASCADE, related_name='sections', verbose_name="Пространство")
    title = models.CharField(max_length=255, verbose_name="Название секции (Тема/Неделя)")
    description = models.TextField(blank=True, verbose_name="Описание (HTML)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок (Сортировка)")
    is_visible = models.BooleanField(default=True, verbose_name="Видимость для студентов")
    
    # Привязка к типу занятия (полезно для генерации пустых блоков)
    lesson_type = models.CharField(max_length=20, choices=Subject.TYPE_CHOICES, null=True, blank=True, verbose_name="Тип занятия (Опционально)")

    class Meta:
        verbose_name = "Секция курса"
        verbose_name_plural = "Секции курса"
        ordering = ['order']

    def __str__(self):
        return f"{self.workspace} - {self.title}"


class Material(models.Model):
    MATERIAL_TYPES = [
        ('PDF', 'PDF Документ'),
        ('DOC', 'Word Документ'),
        ('VIDEO', 'Видео (Файл)'),
        ('LINK', 'Внешняя ссылка (YouTube и др.)'),
        ('PAGE', 'Текстовая страница (HTML)'),
        ('ASSIGNMENT', 'Задание (Загрузка ответа)'), 
        ('QUIZ', 'Тест/Экзамен'),
    ]

    section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name='materials', verbose_name="Секция")
    title = models.CharField(max_length=255, verbose_name="Название материала")
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPES, verbose_name="Тип материала")
    
    content = models.TextField(blank=True, verbose_name="Текст/HTML контент")
    file = models.FileField(upload_to='lms_materials/%Y/%m/', null=True, blank=True, verbose_name="Файл")
    external_link = models.URLField(blank=True, verbose_name="Внешняя ссылка")
    
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок в секции")
    is_visible = models.BooleanField(default=True, verbose_name="Видимость")

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ['section', 'order']

    def __str__(self):
        return f"[{self.get_material_type_display()}] {self.title}"