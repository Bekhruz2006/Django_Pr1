from django.db import models
from accounts.models import User

class News(models.Model):

    CATEGORY_CHOICES = [
        ('ANNOUNCEMENT', 'Объявление'),
        ('EVENT', 'Мероприятие'),
        ('ACHIEVEMENT', 'Достижение'),
        ('SCHEDULE', 'Расписание'),
        ('OTHER', 'Другое'),
    ]
    
    title = models.CharField(max_length=200, verbose_name="Заголовок")
    content = models.TextField(verbose_name="Содержание")
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='ANNOUNCEMENT',
        verbose_name="Категория"
    )
    
    image = models.ImageField(
        upload_to='news_images/',
        blank=True,
        null=True,
        verbose_name="Изображение"
    )
    
    video_url = models.URLField(
        blank=True,
        verbose_name="Ссылка на видео (YouTube, Vimeo)"
    )
    
    video_file = models.FileField(
        upload_to='news_videos/',
        blank=True,
        null=True,
        verbose_name="Видео файл"
    )
    
    is_pinned = models.BooleanField(
        default=False,
        verbose_name="Закреплено"
    )
    
    is_published = models.BooleanField(
        default=True,
        verbose_name="Опубликовано"
    )
    
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='news_articles',
        verbose_name="Автор"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    views_count = models.IntegerField(default=0, verbose_name="Просмотры")
    
    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"
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
        verbose_name="Новость"
    )
    
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="Автор"
    )
    
    content = models.TextField(verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата")
    
    class Meta:
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        ordering = ['created_at']
    
    def __str__(self):
        return f"Комментарий от {self.author.get_full_name()} к {self.news.title}"