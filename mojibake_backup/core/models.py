from django.db import models
from django.utils import timezone
from accounts.models import User

class News(models.Model):
    """Новости на главной странице"""
    
    CATEGORY_CHOICES = [
        ('GENERAL', 'Общие'),
        ('ACADEMIC', 'Учебные'),
        ('EVENT', 'Мероприятия'),
        ('IMPORTANT', 'Важное'),
    ]
    
    title = models.CharField(max_length=200, verbose_name="Заголовок")
    content = models.TextField(verbose_name="Содержание")
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='GENERAL',
        verbose_name="Категория"
    )
    
    image = models.ImageField(
        upload_to='news_images/',
        blank=True,
        null=True,
        verbose_name="Изображение"
    )
    
    is_pinned = models.BooleanField(
        default=False,
        verbose_name="Закрепить"
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name="Опубликовано"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Автор"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    
    views_count = models.IntegerField(
        default=0,
        verbose_name="Просмотров"
    )
    
    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"
        ordering = ['-is_pinned', '-created_at']
    
    def __str__(self):
        return self.title
    
    def increment_views(self):
        self.views_count += 1
        self.save(update_fields=['views_count'])


class ChatRoom(models.Model):
    """Комнаты чата (групповые или личные)"""
    
    ROOM_TYPE_CHOICES = [
        ('PERSONAL', 'Личный'),
        ('GROUP', 'Групповой'),
        ('ANNOUNCEMENT', 'Объявления'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название")
    room_type = models.CharField(
        max_length=20,
        choices=ROOM_TYPE_CHOICES,
        default='PERSONAL',
        verbose_name="Тип чата"
    )
    
    participants = models.ManyToManyField(
        User,
        related_name='chat_rooms',
        verbose_name="Участники"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_rooms',
        verbose_name="Создатель"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Для личных чатов - храним обоих участников отдельно
    user1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='personal_chats_1'
    )
    user2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='personal_chats_2'
    )
    
    class Meta:
        verbose_name = "Чат"
        verbose_name_plural = "Чаты"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def get_last_message(self):
        return self.messages.order_by('-created_at').first()


class ChatMessage(models.Model):
    """Сообщения в чате"""
    
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name="Комната"
    )
    
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        verbose_name="Отправитель"
    )
    
    message = models.TextField(verbose_name="Сообщение")
    
    file = models.FileField(
        upload_to='chat_files/',
        blank=True,
        null=True,
        verbose_name="Файл"
    )
    
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.sender.get_full_name()}: {self.message[:30]}"