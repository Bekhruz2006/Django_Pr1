# schedule/admin.py
from django.contrib import admin
from .models import (
    Faculty, Department, Group, Teacher, 
    Subject, TimeSlot, ScheduleSlot, Dean
)

@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code']

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'faculty']
    list_filter = ['faculty']
    search_fields = ['name', 'code']

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'course', 'department']
    list_filter = ['course', 'department']
    search_fields = ['name']

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'position']
    list_filter = ['department']
    search_fields = ['user__first_name', 'user__last_name', 'user__username']

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'credits', 'hours_per_semester', 'teacher', 'department']
    list_filter = ['department', 'teacher']
    search_fields = ['name', 'code']

@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_time', 'end_time']
    ordering = ['start_time']

@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ['group', 'subject', 'teacher', 'day_of_week', 'time_slot', 'room']
    list_filter = ['day_of_week', 'group', 'teacher']
    search_fields = ['subject__name', 'group__name', 'room']
    ordering = ['day_of_week', 'time_slot__start_time']

@admin.register(Dean)
class DeanAdmin(admin.ModelAdmin):
    list_display = ['user', 'faculty']
    list_filter = ['faculty']
    search_fields = ['user__first_name', 'user__last_name']