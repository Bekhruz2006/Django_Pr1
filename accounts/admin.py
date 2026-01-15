from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Student, Teacher, Dean, ViceDean, Director, ProRector,
    Group, GroupTransferHistory,
    Institute, Faculty, Department, Specialty
)
from .forms import GroupForm, SpecialtyForm

@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = ['name', 'abbreviation']

@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ['name', 'institute', 'code']
    list_filter = ['institute']

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'faculty']
    list_filter = ['faculty__institute', 'faculty']
    search_fields = ['name']

@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    form = SpecialtyForm
    list_display = ['code', 'name', 'department', 'qualification']
    list_filter = ['department__faculty']
    search_fields = ['code', 'name']

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
    form = GroupForm
    list_display = ['name', 'course', 'academic_year', 'specialty']
    list_filter = ['course', 'academic_year']
    search_fields = ['name', 'specialty__name']

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['user', 'student_id', 'group', 'course', 'status']
    list_filter = ['course', 'status', 'financing_type', 'education_type']
    search_fields = ['user__first_name', 'user__last_name', 'student_id']
    raw_id_fields = ['user', 'group']

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['user', 'degree', 'title', 'department']
    list_filter = ['department']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'department']

@admin.register(Dean)
class DeanAdmin(admin.ModelAdmin):
    list_display = ['user', 'faculty', 'contact_email']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'faculty']

@admin.register(ViceDean)
class ViceDeanAdmin(admin.ModelAdmin):
    list_display = ['user', 'faculty', 'title']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'faculty']

@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ['user', 'institute']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'institute']

@admin.register(ProRector)
class ProRectorAdmin(admin.ModelAdmin):
    list_display = ['user', 'institute', 'title']
    search_fields = ['user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'institute']

@admin.register(GroupTransferHistory)
class GroupTransferHistoryAdmin(admin.ModelAdmin):
    list_display = ['student', 'from_group', 'to_group', 'transfer_date', 'transferred_by']
    list_filter = ['transfer_date']
    search_fields = ['student__user__first_name', 'student__user__last_name']
    raw_id_fields = ['student', 'from_group', 'to_group', 'transferred_by']