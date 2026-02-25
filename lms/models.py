from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from accounts.models import User, Faculty, Department, Institute, Group
from django.core.validators import FileExtensionValidator


class CourseCategory(models.Model):
    name= models.CharField(max_length=255, verbose_name=_("Название"))
    parent= models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    faculty= models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='course_categories')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='course_categories')
    institute = models.ForeignKey(Institute, on_delete=models.SET_NULL, null=True, blank=True, related_name='course_categories')
    description= models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Категория курса"); verbose_name_plural = _("Категории курсов")
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def get_full_path(self):
        return f"{self.parent.get_full_path()} / {self.name}" if self.parent else self.name


class Course(models.Model):
    VISIBILITY_CHOICES = [
        ('VISIBLE', _('Видимый (для записанных)')),
        ('HIDDEN',  _('Скрытый')),
        ('FACULTY', _('Только факультет')),
        ('DEPT',    _('Только кафедра')),
        ('GROUP',   _('Конкретная группа')),
    ]
    FORMAT_CHOICES = [
        ('TOPICS',  _('Тематический')),
        ('WEEKLY',  _('Недельный')),
        ('SOCIAL',  _('Социальный')),
    ]

    category= models.ForeignKey(CourseCategory, on_delete=models.CASCADE, related_name='courses')
    full_name= models.CharField(max_length=255, verbose_name=_("Полное название"))
    short_name= models.CharField(max_length=100, verbose_name=_("Краткое название"))
    id_number= models.CharField(max_length=100, blank=True, null=True, verbose_name=_("ID-номер"))
    summary= models.TextField(blank=True, verbose_name=_("Описание"))
    image= models.ImageField(upload_to='course_images/', blank=True, null=True)

    visibility= models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='VISIBLE')
    format= models.CharField(max_length=20, choices=FORMAT_CHOICES, default='TOPICS')
    is_visible= models.BooleanField(default=True)

    start_date= models.DateField(null=True, blank=True)
    end_date= models.DateField(null=True, blank=True)

    allow_self_enrol  = models.BooleanField(default=False)
    enrol_key= models.CharField(max_length=100, blank=True)

    allowed_faculty= models.ForeignKey(Faculty,    on_delete=models.SET_NULL, null=True, blank=True, related_name='lms_courses')
    allowed_department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='lms_courses')
    allowed_group= models.ForeignKey(Group,      on_delete=models.SET_NULL, null=True, blank=True, related_name='lms_courses')

    created_at= models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by= models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_courses')

    class Meta:
        verbose_name = _("Курс"); verbose_name_plural = _("Курсы")
        ordering = ['full_name']

    def __str__(self):
        return self.short_name

    def get_progress(self, user):
        total = CourseModule.objects.filter(section__course=self, is_visible=True, completion_required=True).count()
        if not total:
            return 100
        done = ModuleCompletion.objects.filter(module__section__course=self, user=user, is_completed=True).count()
        return round(done / total * 100)

    def get_enrolment(self, user):
        return self.enrolments.filter(user=user).first()

    def get_teacher(self):
        e = self.enrolments.filter(role='TEACHER').first()
        return e.user if e else None


class CourseEnrolment(models.Model):
    ROLE_CHOICES = [
        ('STUDENT',  _('Студент')),
        ('TEACHER',  _('Преподаватель')),
        ('MANAGER',  _('Менеджер курса')),
        ('OBSERVER', _('Наблюдатель')),
    ]
    course= models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrolments')
    user= models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_enrolments')
    role= models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    last_access = models.DateTimeField(null=True, blank=True)
    is_active  = models.BooleanField(default=True)

    class Meta:
        unique_together = ['course', 'user']
        verbose_name = _("Запись на курс")

    def touch(self):
        self.last_access = timezone.now()
        self.save(update_fields=['last_access'])


class CourseSection(models.Model):
    course= models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    name= models.CharField(max_length=255)
    summary= models.TextField(blank=True)
    sequence   = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ['sequence']
        verbose_name = _("Секция курса")

    def __str__(self):
        return f"{self.course.short_name} / {self.name}"


class CourseModule(models.Model):
    MODULE_TYPES = [
        ('PAGE',       _('Страница')),
        ('FILE',       _('Файл')),
        ('FOLDER',     _('Папка')),
        ('URL',        _('Внешняя ссылка')),
        ('VIDEO',      _('Видео')),
        ('ASSIGNMENT', _('Задание')),
        ('QUIZ',       _('Тест')),
        ('FORUM',      _('Форум')),
        ('LABEL',      _('Метка')),
        ('GLOSSARY',   _('Глоссарий')),
        ('ATTENDANCE', _('Посещаемость')),
    ]

    section= models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name='modules')
    module_type= models.CharField(max_length=20, choices=MODULE_TYPES)
    title= models.CharField(max_length=255)
    description= models.TextField(blank=True)
    sequence= models.PositiveIntegerField(default=0)
    is_visible= models.BooleanField(default=True)
    completion_required = models.BooleanField(default=False)

    available_from  = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    depends_on= models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='dependents')

    class Meta:
        ordering = ['sequence']
        verbose_name = _("Модуль курса")

    def __str__(self):
        return f"[{self.get_module_type_display()}] {self.title}"

    def is_available(self):
        now = timezone.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True

    def get_icon(self):
        return {
            'PAGE':       'bi-file-text text-primary',
            'FILE':       'bi-file-earmark-arrow-down text-info',
            'FOLDER':     'bi-folder2-open text-warning',
            'URL':        'bi-link-45deg text-primary',
            'VIDEO':      'bi-play-circle-fill text-danger',
            'ASSIGNMENT': 'bi-journal-arrow-up text-danger',
            'QUIZ':       'bi-ui-checks text-success',
            'FORUM':      'bi-chat-left-quote text-warning',
            'LABEL':      'bi-dash-lg text-muted',
            'GLOSSARY':   'bi-book text-teal',
            'ATTENDANCE': 'bi-calendar-check text-success',
        }.get(self.module_type, 'bi-box text-secondary')

    def get_detail_url(self):
        from django.urls import reverse
        return reverse('lms:module_detail', kwargs={'module_id': self.pk})


class ModuleCompletion(models.Model):
    user= models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_completions')
    module= models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='completions')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['user', 'module']

    def mark_complete(self):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save()

    def record_view(self):
        self.view_count += 1
        self.save(update_fields=['view_count'])



class PageContent(models.Model):
    module  = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='page_content')
    content = models.TextField()


class FileResource(models.Model):
    DISPLAY_CHOICES = [('INLINE','Встроить'),('DOWNLOAD','Скачать'),('NEW_TAB','Новая вкладка')]
    module= models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='file_resource')
    file= models.FileField(upload_to='lms/resources/%Y/%m/')
    display_type = models.CharField(max_length=15, choices=DISPLAY_CHOICES, default='DOWNLOAD')
    file_size= models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.file:
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    def get_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.1f} MB"


class FolderResource(models.Model):
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='folder_resource')


class FolderFile(models.Model):
    folder= models.ForeignKey(FolderResource, on_delete=models.CASCADE, related_name='files')
    name= models.CharField(max_length=255)
    file= models.FileField(upload_to='lms/folders/%Y/%m/')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']


class UrlResource(models.Model):
    module= models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='url_resource')
    external_url    = models.URLField()
    open_in_new_tab = models.BooleanField(default=True)


class VideoResource(models.Model):
    module= models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='video_resource')
    embed_url = models.URLField(blank=True)
    file= models.FileField(upload_to='lms/videos/', blank=True, null=True)


class Assignment(models.Model):
    SUBMISSION_TYPES = [('FILE','Файл'),('TEXT','Текст'),('BOTH','Файл + текст')]
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='assignment')
    description = models.TextField()
    due_date= models.DateTimeField(null=True, blank=True)
    max_score= models.FloatField(default=100.0)
    submission_type= models.CharField(max_length=10, choices=SUBMISSION_TYPES, default='FILE')
    max_file_size_mb= models.PositiveIntegerField(default=20)
    allowed_file_types= models.CharField(max_length=200, blank=True, default='pdf,doc,docx,zip')
    allow_late_submission = models.BooleanField(default=True)


class AssignmentSubmission(models.Model):
    STATUS_CHOICES = [
        ('DRAFT','Черновик'),('SUBMITTED','Сдано'),
        ('GRADED','Оценено'),('RETURNED','Возвращено'),
    ]
    assignment= models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    file  = models.FileField(upload_to='lms/submissions/%Y/%m/', blank=True, null=True)
    text_answer = models.TextField(blank=True)
    submitted_at= models.DateTimeField(auto_now_add=True)
    updated_at= models.DateTimeField(auto_now=True)
    score  = models.FloatField(null=True, blank=True)
    teacher_feedback = models.TextField(blank=True)
    graded_at   = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_submissions')
    is_late = models.BooleanField(default=False)

    class Meta:
        unique_together = ['assignment', 'student']
        verbose_name = _("Ответ студента")


class Forum(models.Model):
    FORUM_TYPES = [('ANNOUNCE','Объявления'),('DISCUSS','Обсуждение'),('QA','Вопрос-ответ')]
    module     = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='forum')
    forum_type = models.CharField(max_length=15, choices=FORUM_TYPES, default='DISCUSS')


class ForumThread(models.Model):
    forum  = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='threads')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_pinned  = models.BooleanField(default=False)
    is_locked  = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_pinned', '-created_at']


class ForumPost(models.Model):
    thread= models.ForeignKey(ForumThread, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    parent  = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    body  = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']


class GradeItem(models.Model):
    ITEM_TYPES = [('ASSIGNMENT','Задание'),('QUIZ','Тест'),('MANUAL','Ручная')]
    course   = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='grade_items')
    module = models.OneToOneField(CourseModule, on_delete=models.SET_NULL, null=True, blank=True, related_name='grade_item')
    name   = models.CharField(max_length=255)
    item_type  = models.CharField(max_length=15, choices=ITEM_TYPES, default='MANUAL')
    max_score  = models.FloatField(default=100.0)
    weight  = models.FloatField(default=1.0)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']


class GradeEntry(models.Model):
    grade_item = models.ForeignKey(GradeItem, on_delete=models.CASCADE, related_name='entries')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grade_entries')
    score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(auto_now=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='given_grades')
    is_excluded= models.BooleanField(default=False)

    class Meta:
        unique_together = ['grade_item', 'student']

    @property
    def percentage(self):
        if self.score is None or self.grade_item.max_score == 0:
            return None
        return round(self.score / self.grade_item.max_score * 100, 1)


class CourseAnnouncement(models.Model):
    course   = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_pinned  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']


class Glossary(models.Model):
    module = models.OneToOneField(CourseModule, on_delete=models.CASCADE, related_name='glossary')


class GlossaryEntry(models.Model):
    glossary   = models.ForeignKey(Glossary, on_delete=models.CASCADE, related_name='entries')
    concept    = models.CharField(max_length=255)
    definition = models.TextField()
    author     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['concept']


class CourseAccessLog(models.Model):
    course      = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='access_logs')
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-accessed_at']