from django.contrib import admin
from .models import Subject, Semester, AcademicWeek, ScheduleSlot, ScheduleException, Classroom

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'credits', 'teacher', 'get_distribution']
    list_filter = ['teacher']
    search_fields = ['name', 'code']
    raw_id_fields = ['teacher']
    
    def get_distribution(self, obj):
        dist = obj.get_credits_distribution()
        return f"Л:{dist['LECTURE']} П:{dist['PRACTICE']} С:{dist['SRSP']}"
    get_distribution.short_description = 'Распределение'

@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ['number', 'floor', 'capacity', 'is_active']
    list_filter = ['floor', 'is_active']
    search_fields = ['number']
    ordering = ['floor', 'number']

@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ['name', 'number', 'shift', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active', 'number', 'shift']
    ordering = ['-start_date']

@admin.register(AcademicWeek)
class AcademicWeekAdmin(admin.ModelAdmin):
    list_display = ['semester', 'week_number', 'start_date', 'end_date', 'is_current']
    list_filter = ['semester', 'is_current']
    ordering = ['semester', 'week_number']

@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ['get_info', 'day_of_week', 'start_time', 'classroom', 'is_active']
    list_filter = ['semester', 'day_of_week', 'lesson_type', 'is_active', 'group']
    search_fields = ['subject__name', 'group__name', 'classroom__number']
    raw_id_fields = ['semester', 'group', 'subject', 'teacher', 'classroom']
    ordering = ['semester', 'day_of_week', 'start_time']
    
    def get_info(self, obj):
        return f"{obj.semester.name} | {obj.group.name} | {obj.subject.name} ({obj.get_lesson_type_display()})"
    get_info.short_description = 'Информация'

@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ['schedule_slot', 'exception_date', 'exception_type', 'reason_short']
    list_filter = ['exception_type', 'exception_date']
    search_fields = ['reason', 'schedule_slot__subject__name']
    raw_id_fields = ['schedule_slot', 'new_classroom', 'created_by']
    date_hierarchy = 'exception_date'
    
    def reason_short(self, obj):
        return obj.reason[:50] + '...' if len(obj.reason) > 50 else obj.reason
    reason_short.short_description = 'Причина'