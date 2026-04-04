
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
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'name', 'short_name', 'institute', 'code']
    list_filter = ['institute']
    search_fields = ['id', 'name', 'short_name', 'code']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)


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
        from django.db.models import (
            OuterRef, Subquery, IntegerField, F,
            ExpressionWrapper,
        )
        from schedule.models import Subject as _Subject
        from accounts.models import Teacher as _Teacher
 
        qs = super().get_queryset(request).select_related('faculty')
 
        staff_sq = (
            _Teacher.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(cnt=Count('id'))
            .values('cnt')
        )
 
        credits_sq = (
            _Subject.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(total=Sum('credits'))
            .values('total')
        )
        occupied_sq = (
            _Subject.objects
            .filter(department=OuterRef('pk'))
            .values('department')
            .annotate(
                total=Sum(
                    ExpressionWrapper(
                        F('lecture_hours') + F('practice_hours') +
                        F('lab_hours') + F('control_hours'),
                        output_field=IntegerField(),
                    )
                )
            )
            .values('total')
        )
 
        return qs.annotate(
            staff_count=Subquery(staff_sq, output_field=IntegerField()),
            total_credits=Subquery(credits_sq, output_field=IntegerField()),
            occupied_hours=Subquery(occupied_sq, output_field=IntegerField()),
        )
 
    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:#888;font-size:11px">#{}</span>', obj.pk)
 
    @admin.display(description='Преподавателей', ordering='staff_count')
    def staff_count_display(self, obj):
        return getattr(obj, 'staff_count', None) or 0
 
    @admin.display(description='Кредитов (∑)', ordering='total_credits')
    def total_credits_display(self, obj):
        return getattr(obj, 'total_credits', None) or 0
 
    @admin.display(description='Нагрузка (Занято / План)')
    def hours_stats(self, obj):
        occupied = getattr(obj, 'occupied_hours', None) or 0
        budget = obj.total_hours_budget or 0
        pct = round(occupied / budget * 100, 1) if budget else 0
        return f"{occupied} / {budget} ({pct}%)"


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
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(AdmissionPlan)
class AdmissionPlanAdmin(admin.ModelAdmin): 
    list_display = [
        'id_badge', 'specialty', 'academic_year',
        'study_form', 'financing_type', 'education_language',
        'target_quota', 'enrolled_count_display', 'fulfillment_display',
    ]
    list_filter = [
        'academic_year', 'specialty__department__faculty',
        'study_form', 'financing_type',
    ]
    search_fields = ['id', 'specialty__code', 'specialty__name', 'academic_year']
    list_select_related = ['specialty__department__faculty']
    ordering = ['-academic_year', 'specialty__code']
 
    def get_queryset(self, request):
        from django.db.models import OuterRef, Subquery, IntegerField, Value, Case, When, CharField
        from django.db.models.functions import Coalesce

        qs = super().get_queryset(request).annotate(
            mapped_edu_type=Case(
                When(study_form='FULL_TIME', then=Value('FULL_TIME')),
                When(study_form='PART_TIME', then=Value('PART_TIME')),
                When(study_form='DISTANCE',  then=Value('EVENING')),
                default=Value('FULL_TIME'),
                output_field=CharField(),
            ),
            mapped_fin_type=Case(
                When(financing_type='CONTRACT', then=Value('CONTRACT')),
                default=Value('BUDGET'),
                output_field=CharField(),
            )
        )

        enrolled_sq = (
            Student.objects
            .filter(
                specialty_id=OuterRef('specialty_id'),
                status='ACTIVE',
                education_type=OuterRef('mapped_edu_type'),
                education_language=OuterRef('education_language'),
                financing_type=OuterRef('mapped_fin_type'),
            )
            .values('specialty_id')
            .annotate(cnt=Count('id'))
            .values('cnt')
        )

        return qs.annotate(
            enrolled_count=Coalesce(
                Subquery(enrolled_sq, output_field=IntegerField()),
                Value(0),
            )
        )
 
    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color:#888;font-size:11px">#{}</span>', obj.pk)
 
    @admin.display(description='Зачислено (факт.)')
    def enrolled_count_display(self, obj):
        count = getattr(obj, 'enrolled_count', 0)
        color = '#16a34a' if count >= obj.target_quota else '#dc2626'
        return format_html(
            '<strong style="color:{}">{}</strong>',
            color,
            count,
        )
 
    @admin.display(description='Выполнение плана')
    def fulfillment_display(self, obj):
        count = getattr(obj, 'enrolled_count', 0)
        pct = round(count / obj.target_quota * 100, 1) if obj.target_quota else 0.0
        color = (
            '#16a34a' if pct >= 90
            else '#f59e0b' if pct >= 50
            else '#dc2626'
        )
        return format_html(
            '<span style="color:{};font-weight:bold">{} %</span>',
            color,
            pct,
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
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    form = GroupForm
    list_display = ['id_badge', 'name', 'course', 'academic_year', 'specialty']
    list_filter = ['course', 'academic_year']
    search_fields = ['id', 'name', 'specialty__name']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)

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
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'degree', 'title', 'department']
    list_filter = ['department']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'department']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(Dean)
class DeanAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'faculty', 'contact_email']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'faculty']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(ViceDean)
class ViceDeanAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'faculty', 'title']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'faculty']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'institute']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'institute']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)


@admin.register(ProRector)
class ProRectorAdmin(admin.ModelAdmin):
    list_display = ['id_badge', 'user', 'institute', 'title']
    search_fields = ['id', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user', 'institute']

    @admin.display(description='ID')
    def id_badge(self, obj):
        return format_html('<span style="color: blue;">{}</span>', obj.id)


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
        return format_html('<span style="color: blue;">{}</span>', obj.id)


admin.site.register(Specialization)
admin.site.register(Diploma)