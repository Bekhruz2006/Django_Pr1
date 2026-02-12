from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import User

class News(models.Model):
    CATEGORY_CHOICES = [
        ('ANNOUNCEMENT', _('Объявление')),
        ('EVENT', _('Мероприятие')),
        ('ACHIEVEMENT', _('Достижение')),
        ('SCHEDULE', _('Расписание')),
        ('OTHER', _('Другое')),
    ]
    
    title = models.CharField(max_length=200, verbose_name=_("Заголовок"))
    content = models.TextField(verbose_name=_("Содержание"))
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='ANNOUNCEMENT',
        verbose_name=_("Категория")
    )
    
    image = models.ImageField(
        upload_to='news_images/',
        blank=True,
        null=True,
        verbose_name=_("Изображение")
    )
    
    video_url = models.URLField(
        blank=True,
        verbose_name=_("Ссылка на видео (YouTube, Vimeo)")
    )
    
    video_file = models.FileField(
        upload_to='news_videos/',
        blank=True,
        null=True,
        verbose_name=_("Видео файл")
    )
    
    is_pinned = models.BooleanField(
        default=False,
        verbose_name=_("Закреплено")
    )
    
    is_published = models.BooleanField(
        default=True,
        verbose_name=_("Опубликовано")
    )
    
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='news_articles',
        verbose_name=_("Автор")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))
    
    views_count = models.IntegerField(default=0, verbose_name=_("Просмотры"))
    
    class Meta:
        verbose_name = _("Новость")
        verbose_name_plural = _("Новости")
        ordering = ['-is_pinned', '-created_at']
    
    def __str__(self):
        return self.title
    
    def increment_views(self):
        self.views_count += 1
        self.save(update_fields=['views_count'])

class NewsComment(models.Model):
    news = models.ForeignKey(
        News,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_("Новость")
    )
    
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("Автор")
    )
    
    content = models.TextField(verbose_name=_("Комментарий"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата"))
    
    class Meta:
        verbose_name = _("Комментарий")
        verbose_name_plural = _("Комментарии")
        ordering = ['created_at']
    
    def __str__(self):
        return f"Комментарий от {self.author.get_full_name()} к {self.news.title}"