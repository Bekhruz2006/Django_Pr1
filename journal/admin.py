from django.contrib import admin
from django.utils.html import format_html
from .models import JournalEntry, JournalChangeLog, StudentStatistics
from .models import MatrixStructure, MatrixColumn, StudentMatrixScore

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'lesson_date', 'lesson_time', 
                    'grade', 'attendance_status', 'is_locked_display', 'modified_by']
    list_filter = ['lesson_date', 'subject', 'attendance_status', 'lesson_type']
    search_fields = ['student__user__first_name', 'student__user__last_name', 
                     'subject__name']
    date_hierarchy = 'lesson_date'
    raw_id_fields = ['student', 'subject', 'created_by', 'modified_by']
    readonly_fields = ['locked_at', 'created_at', 'updated_at', 'is_locked_display']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('student', 'subject', 'lesson_date', 'lesson_time', 'lesson_type')
        }),
        ('Оценка и посещаемость', {
            'fields': ('grade', 'attendance_status')
        }),
        ('Блокировка', {
            'fields': ('locked_at', 'is_locked_display'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_by', 'modified_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def is_locked_display(self, obj):
        if obj.is_locked():
            return format_html(
                '<span style="color: red; font-weight: bold;">🔒 Заблокировано</span>'
            )
        else:
            return format_html(
                '<span style="color: green;">✓ Редактируемо</span>'
            )
    is_locked_display.short_description = 'Статус блокировки'
    
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_locked():
            
            return ['student', 'subject', 'lesson_date', 'lesson_time', 
                    'lesson_type', 'grade', 'attendance_status', 
                    'locked_at', 'created_at', 'updated_at', 'is_locked_display']
        return self.readonly_fields

@admin.register(JournalChangeLog)
class JournalChangeLogAdmin(admin.ModelAdmin):
    list_display = ['entry_display', 'changed_by', 'changed_at', 'change_description_display']
    list_filter = ['changed_at', 'changed_by']
    search_fields = ['entry__student__user__first_name', 'entry__student__user__last_name',
                     'changed_by__user__first_name', 'changed_by__user__last_name']
    date_hierarchy = 'changed_at'
    raw_id_fields = ['entry', 'changed_by']
    readonly_fields = ['changed_at']
    
    fieldsets = (
        ('Информация об изменении', {
            'fields': ('entry', 'changed_by', 'changed_at')
        }),
        ('Старые значения', {
            'fields': ('old_grade', 'old_attendance')
        }),
        ('Новые значения', {
            'fields': ('new_grade', 'new_attendance')
        }),
        ('Дополнительно', {
            'fields': ('comment',)
        }),
    )
    
    def entry_display(self, obj):
        return f"{obj.entry.student.user.get_full_name()} - {obj.entry.subject.name}"
    entry_display.short_description = 'Запись'
    
    def change_description_display(self, obj):
        return obj.get_change_description()
    change_description_display.short_description = 'Изменение'

@admin.register(StudentStatistics)
class StudentStatisticsAdmin(admin.ModelAdmin):
    list_display = ['student', 'overall_gpa', 'group_rank', 'attendance_percentage', 
                    'total_lessons', 'last_updated']
    list_filter = ['last_updated']
    search_fields = ['student__user__first_name', 'student__user__last_name']
    raw_id_fields = ['student']
    readonly_fields = ['last_updated']
    
    fieldsets = (
        ('Студент', {
            'fields': ('student',)
        }),
        ('Успеваемость', {
            'fields': ('overall_gpa', 'group_rank')
        }),
        ('Посещаемость', {
            'fields': ('attendance_percentage', 'total_lessons', 'attended_lessons')
        }),
        ('Дополнительно', {
            'fields': ('subjects_data', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['recalculate_statistics']
    
    def recalculate_statistics(self, request, queryset):
        count = 0
        for stats in queryset:
            stats.recalculate()
            count += 1
        self.message_user(request, f'Пересчитана статистика для {count} студентов')
    recalculate_statistics.short_description = 'Пересчитать статистику'







class MatrixColumnInline(admin.TabularInline):
    model = MatrixColumn
    extra = 1

@admin.register(MatrixStructure)
class MatrixStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'institute', 'faculty', 'is_active']
    list_filter =['institute', 'faculty', 'is_active']
    search_fields = ['name']
    inlines = [MatrixColumnInline]

@admin.register(StudentMatrixScore)
class StudentMatrixScoreAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'column', 'score', 'updated_at']
    list_filter = ['column__structure', 'column__col_type']
    search_fields =['student__user__last_name', 'subject__name']
    readonly_fields = ['updated_at', 'updated_by']