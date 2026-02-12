from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import User

class ChatRoom(models.Model):

    ROOM_TYPE_CHOICES = [
        ('PRIVATE', _('Личный')),
        ('GROUP', _('Групповой')),
    ]
    
    name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Название")
    )
    
    room_type = models.CharField(
        max_length=10,
        choices=ROOM_TYPE_CHOICES,
        default='PRIVATE',
        verbose_name=_("Тип комнаты")
    )
    
    participants = models.ManyToManyField(
        User,
        related_name='chat_rooms',
        verbose_name=_("Участники")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))
    
    class Meta:
        verbose_name = _("Чат")
        verbose_name_plural = _("Чаты")
        ordering = ['-updated_at']
    
    def __str__(self):
        if self.name:
            return self.name
        
        names = [p.get_full_name() for p in self.participants.all()[:2]]
        return " — ".join(names)
    
    def get_last_message(self):
        
        return self.messages.order_by('-created_at').first()
    
    def get_unread_count(self, user):
        
        return self.messages.filter(is_read=False).exclude(sender=user).count()

class ChatMessage(models.Model):

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name=_("Комната")
    )
    
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        verbose_name=_("Отправитель")
    )
    
    content = models.TextField(verbose_name=_("Сообщение"))
    
    is_read = models.BooleanField(default=False, verbose_name=_("Прочитано"))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата отправки"))
    
    class Meta:
        verbose_name = _("Сообщение")
        verbose_name_plural = _("Сообщения")
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.sender.get_full_name()}: {self.content[:50]}"