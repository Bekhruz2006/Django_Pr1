from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Student, Teacher, Dean, Group, GroupTransferHistory

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'role', 'is_active']
    list_filter = ['role', 'is_active', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Дополнительная информация', {'fields': ('role', 'phone', 'photo')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Дополнительная информация', {'fields': ('role', 'phone', 'photo')}),
    )

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'course', 'academic_year', 'specialty']
    list_filter = ['course', 'academic_year']
    search_fields = ['name', 'specialty']

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['user', 'student_id', 'group', 'course', 'status']
    list_filter = ['course', 'status', 'financing_type', 'education_type']
    search_fields = ['user__first_name', 'user__last_name', 'student_id']
    raw_id_fields = ['user', 'group']

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['user', 'degree', 'title']
    list_filter = ['degree', 'title']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user']

@admin.register(Dean)
class DeanAdmin(admin.ModelAdmin):
    list_display = ['user', 'contact_email']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user']

@admin.register(GroupTransferHistory)
class GroupTransferHistoryAdmin(admin.ModelAdmin):
    list_display = ['student', 'from_group', 'to_group', 'transfer_date', 'transferred_by']
    list_filter = ['transfer_date']
    search_fields = ['student__user__first_name', 'student__user__last_name']
    raw_id_fields = ['student', 'from_group', 'to_group', 'transferred_by']