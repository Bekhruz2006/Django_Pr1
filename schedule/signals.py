import re
from datetime import datetime
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Group
from .models import AcademicPlan
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import ScheduleException, ScheduleSlot, UnusedHourPool

@receiver(post_save, sender=Group)
def auto_create_rup_for_group(sender, instance, created, **kwargs):
    if created and instance.specialty:
        try:
            academic_year_str = instance.academic_year or str(datetime.now().year)
            
            match = re.search(r'\d{4}', academic_year_str)
            start_year = int(match.group()) if match else datetime.now().year
            
            admission_year = start_year - instance.course + 1

            plan, plan_created = AcademicPlan.objects.get_or_create(
                specialty=instance.specialty,
                admission_year=admission_year,
                group__isnull=True,
                defaults={'is_active': True}
            )
            
            if plan_created:
                print(f"Автоматически создан РУП для специальности {instance.specialty.code} (Год набора: {admission_year})")
        except Exception as e:
            print(f"Ошибка автосоздания РУП: {e}")

@receiver(post_save, sender=ScheduleException)
def track_cancelled_hours(sender, instance, created, **kwargs):
    if instance.exception_type == 'CANCEL':
        slot = instance.schedule_slot
        UnusedHourPool.objects.get_or_create(
            group=slot.group,
            subject=slot.subject,
            teacher=slot.teacher,
            semester=slot.semester,
            original_date=instance.exception_date,
            defaults={'reason': instance.reason or 'Отменено через Живой календарь'}
        )
    elif instance.exception_type == 'RESCHEDULE':
        UnusedHourPool.objects.filter(
            group=instance.schedule_slot.group,
            original_date=instance.exception_date
        ).update(is_recovered=True)

@receiver(pre_delete, sender=ScheduleSlot)
def backup_deleted_slot(sender, instance, **kwargs):
    if instance.is_active:
        UnusedHourPool.objects.create(
            group=instance.group,
            subject=instance.subject,
            teacher=instance.teacher,
            semester=instance.semester,
            reason='Полное удаление из шахматки расписания'
        )

