
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count, Sum, Q
from django.utils.html import format_html

from .models import (
    User, Student, Teacher, Dean, ViceDean, Director, ProRector,
    Group, GroupTransferHistory,
    Institute, Faculty, Department, Specialty, StructureChangeLog,
    Order, OrderItem, Specialization, Diploma,
    AdmissionPlan,
)
from .forms import GroupForm, SpecialtyForm


class ProRectorInline(admin.TabularInline):
    model = ProRector
    extra = 1
    fields = ['user', 'title']
    raw_id_fields = ['user']


@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'name', 'abbreviation']
    search_fields = ['id', 'name', 'abbreviation']
    inlines = [ProRectorInline]

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'name', 'short_name', 'institute', 'code']
    list_filter = ['institute']
    search_fields = ['id', 'name', 'short_name', 'code']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = [
        'id_badge', 'name', 'faculty',
        'staff_count_display', 'total_credits_display',
        'total_wage_rate', 'hours_stats',
    ]
    list_filter = ['faculty__institute', 'faculty']
    search_fields = ['id', 'name']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('faculty').prefetch_related('subjects').annotate(
            staff_count=Count('teachers', distinct=True),
            total_credits=Sum('subjects__credits'),
        )

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:

    @admin.display(description='Преподавателей', ordering='staff_count')
    def staff_count_display(self, obj):
        return getattr(obj, 'staff_count', '—')

    @admin.display(description='Кредитов (∑)', ordering='total_credits')
    def total_credits_display(self, obj):
        return getattr(obj, 'total_credits', 0) or 0

    def hours_stats(self, obj):
        occupied = obj.get_occupied_hours()
        return f"{occupied} / {obj.total_hours_budget} ({obj.get_load_percentage()}%)"
    hours_stats.short_description = "Нагрузка (Занято / План)"


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    form = SpecialtyForm
    list_display = [
        'id_badge', 'code', 'name', 'education_level',
        'department', 'qualification',
    ]
    list_filter = ['department__faculty', 'education_level']
    search_fields = ['id', 'code', 'name', 'name_tj', 'name_ru', 'name_en']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(AdmissionPlan)
class AdmissionPlanAdmin(admin.ModelAdmin):
    list_display = [
        'id_badge', 'specialty', 'academic_year',
        'study_form', 'financing_type', 'education_language',
        'target_quota', 'enrolled_count_display', 'fulfillment_display',
    ]
    list_filter = ['academic_year', 'specialty__department__faculty', 'study_form', 'financing_type']
    search_fields = ['id', 'specialty__code', 'specialty__name', 'academic_year']
    list_select_related = ['specialty__department__faculty']
    ordering = ['-academic_year', 'specialty__code']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:

    @admin.display(description='Зачислено (факт.)')
    def enrolled_count_display(self, obj):
        count = obj.get_enrolled_count()
        return format_html(
            '<strong style="color: {}">{}</strong>',
            '
            count,
        )

    @admin.display(description='Выполнение плана')
    def fulfillment_display(self, obj):
        pct = obj.get_fulfillment_percent()
        color = '
        return format_html(
            '<span style="color:{};font-weight:bold">{} %</span>',
            color, pct,
        )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['id_badge', 'username', 'first_name', 'last_name', 'role', 'is_active']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['id', 'username', 'first_name', 'last_name']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Дополнительная информация', {
            'fields': ('role', 'employee_category', 'phone', 'photo', 'birth_date', 'address', 'passport_number')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Дополнительная информация', {
            'fields': ('role', 'employee_category', 'phone', 'photo', 'birth_date', 'address', 'passport_number')
        }),
    )

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    form = GroupForm
    list_display = ['id_badge', 'name', 'course', 'academic_year', 'specialty']
    list_filter = ['course', 'academic_year']
    search_fields = ['id', 'name', 'specialty__name']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'student_id', 'group', 'course', 'financing_type', 'status']
    list_editable = ['financing_type', 'status']
    list_filter = ['course', 'status', 'financing_type', 'education_type']
    search_fields = ['id', 'user__first_name', 'user__last_name', 'student_id']
    raw_id_fields = ['user', 'group']
    list_select_related = ['user', 'group']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'degree', 'title', 'department']
    list_filter = ['department']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'department']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Dean)
class DeanAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'faculty', 'contact_email']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'faculty']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(ViceDean)
class ViceDeanAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'faculty', 'title']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'faculty']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'institute']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'institute']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(ProRector)
class ProRectorAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'institute', 'title']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'institute']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


@admin.register(StructureChangeLog)
class StructureChangeLogAdmin(admin.ModelAdmin):
    list_display = ['object_type', 'object_name', 'field_changed', 'old_value', 'new_value', 'changed_at']
    list_filter = ['object_type', 'changed_at']
    readonly_fields = [
        'object_type', 'object_id', 'object_name', 'field_changed',
        'old_value', 'new_value', 'changed_at', 'changed_by',
    ]

    def has_add_permission(self, request):
        return False


@admin.register(GroupTransferHistory)
class GroupTransferHistoryAdmin(admin.ModelAdmin):
    list_display = ['student', 'from_group', 'to_group', 'transfer_date', 'transferred_by']
    list_filter = ['transfer_date']
    search_fields = ['student__user__first_name', 'student__user__last_name']
    raw_id_fields = ['student', 'from_group', 'to_group', 'transferred_by']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    raw_id_fields = ['student', 'target_group']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'number', 'date', 'order_type', 'status']
    list_filter = ['order_type', 'status', 'date']
    search_fields = ['id', 'number', 'title']
    inlines = [OrderItemInline]

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:


admin.site.register(Specialization)
admin.site.register(Diploma)