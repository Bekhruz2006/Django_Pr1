from django.contrib import admin
from .models import (
    Subject, TimeSlot, ScheduleSlot, Semester, 
    Classroom, ScheduleException, AcademicWeek
)

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'type', 'credits', 'hours_per_semester', 'teacher']
    list_filter = ['type', 'teacher']
    search_fields = ['name', 'code']
    raw_id_fields = ['teacher']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'code', 'type')
        }),
        ('Учебная нагрузка', {
            'fields': ('credits', 'hours_per_semester')
        }),
        ('Преподаватель', {
            'fields': ('teacher',)
        }),
    )

@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_time', 'end_time']
    ordering = ['start_time']

@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ['name', 'number', 'shift', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active', 'shift', 'number']
    ordering = ['-start_date']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'number', 'shift')
        }),
        ('Период', {
            'fields': ('start_date', 'end_date')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )

@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ['number', 'floor', 'capacity', 'is_active']
    list_filter = ['floor', 'is_active']
    search_fields = ['number']
    ordering = ['floor', 'number']

@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ['group', 'subject', 'teacher', 'day_of_week', 'time_slot', 'classroom', 'semester', 'is_active']
    list_filter = ['day_of_week', 'semester', 'is_active', 'subject__type']
    search_fields = ['subject__name', 'group__name', 'teacher__user__first_name', 'teacher__user__last_name']
    raw_id_fields = ['group', 'subject', 'teacher', 'classroom']
    ordering = ['semester', 'day_of_week', 'time_slot__start_time']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('group', 'subject', 'teacher', 'semester')
        }),
        ('Расписание', {
            'fields': ('day_of_week', 'time_slot')
        }),
        ('Место проведения', {
            'fields': ('classroom', 'room')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('group', 'subject', 'teacher__user', 'semester', 'time_slot', 'classroom')

@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ['schedule_slot', 'exception_type', 'exception_date', 'reason_short']
    list_filter = ['exception_type', 'exception_date']
    search_fields = ['schedule_slot__subject__name', 'reason']
    raw_id_fields = ['schedule_slot', 'new_classroom']
    date_hierarchy = 'exception_date'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('schedule_slot', 'exception_type', 'exception_date', 'reason')
        }),
        ('Перенос (если применимо)', {
            'fields': ('new_date', 'new_start_time', 'new_end_time', 'new_classroom'),
            'classes': ('collapse',)
        }),
    )
    
    def reason_short(self, obj):
        return obj.reason[:50] + '...' if len(obj.reason) > 50 else obj.reason
    reason_short.short_description = 'Причина'

@admin.register(AcademicWeek)
class AcademicWeekAdmin(admin.ModelAdmin):
    list_display = ['week_number', 'semester', 'start_date', 'end_date', 'is_current']
    list_filter = ['is_current', 'semester']
    ordering = ['-start_date']
    
    fieldsets = (
        ('Информация о неделе', {
            'fields': ('semester', 'week_number')
        }),
        ('Период', {
            'fields': ('start_date', 'end_date')
        }),
        ('Статус', {
            'fields': ('is_current',)
        }),
    )