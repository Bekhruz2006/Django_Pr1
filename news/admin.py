from django.contrib import admin
from .models import News, NewsComment

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'author', 'is_published', 'is_pinned', 'views_count', 'created_at']
    list_filter = ['category', 'is_published', 'is_pinned', 'created_at']
    search_fields = ['title', 'content']
    date_hierarchy = 'created_at'
    readonly_fields = ['views_count', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'content', 'category', 'author')
        }),
        ('Медиа', {
            'fields': ('image', 'video_url', 'video_file')
        }),
        ('Настройки публикации', {
            'fields': ('is_published', 'is_pinned', 'views_count')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(NewsComment)
class NewsCommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'news', 'content_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['content', 'author__first_name', 'author__last_name']
    date_hierarchy = 'created_at'
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Комментарий'
