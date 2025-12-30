from django.contrib import admin
from .models import Subject, AcademicWeek, ScheduleSlot, ScheduleException

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'type', 'hours_per_semester', 'teacher']
    list_filter = ['type']
    search_fields = ['name', 'code']
    raw_id_fields = ['teacher']

@admin.register(AcademicWeek)
class AcademicWeekAdmin(admin.ModelAdmin):
    list_display = ['semester_start_date', 'current_week', 'is_active']
    list_filter = ['is_active']
    
    def save_model(self, request, obj, form, change):
        
        if not change:  
            obj.current_week = obj.calculate_current_week()
        super().save_model(request, obj, form, change)

@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ['group', 'subject', 'day_of_week', 'start_time', 'end_time', 'classroom', 'teacher', 'is_active']
    list_filter = ['day_of_week', 'is_active', 'group']
    search_fields = ['subject__name', 'group__name', 'classroom']
    raw_id_fields = ['group', 'subject', 'teacher']
    ordering = ['day_of_week', 'start_time']

@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ['schedule_slot', 'exception_date', 'exception_type', 'reason']
    list_filter = ['exception_type', 'exception_date']
    search_fields = ['reason', 'schedule_slot__subject__name']
    raw_id_fields = ['schedule_slot', 'created_by']
    date_hierarchy = 'exception_date'