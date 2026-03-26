import re
from datetime import datetime
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from accounts.models import Group
from .models import AcademicPlan, ScheduleException, ScheduleSlot, UnusedHourPool
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Group)
def auto_create_rup_for_group(sender, instance, created, **kwargs):
    if created and instance.specialty:
        try:
            academic_year_str = instance.academic_year or str(datetime.now().year)
            match = re.search(r'\d{4}', academic_year_str)
            start_year = int(match.group()) if match else datetime.now().year
            admission_year = start_year - instance.course + 1

            logger.debug(
                "auto_create_rup_for_group: group=%s specialty=%s admission_year=%s",
                instance.name, instance.specialty.code, admission_year
            )

            plan, plan_created = AcademicPlan.objects.get_or_create(
                specialty=instance.specialty,
                admission_year=admission_year,
                group__isnull=True,
                defaults={'is_active': True}
            )

            if plan_created:
                logger.info(
                    "Auto-created AcademicPlan for specialty=%s admission_year=%s triggered by group=%s",
                    instance.specialty.code, admission_year, instance.name
                )
            else:
                logger.debug(
                    "AcademicPlan already exists for specialty=%s admission_year=%s, skipped creation",
                    instance.specialty.code, admission_year
                )
        except Exception as e:
            logger.exception(
                "auto_create_rup_for_group failed for group=%s specialty=%s: %s",
                instance.name, getattr(instance.specialty, 'code', '?'), e
            )


@receiver(post_save, sender=ScheduleException)
def track_cancelled_hours(sender, instance, created, **kwargs):
    try:
        slot = instance.schedule_slot
        if instance.exception_type == 'CANCEL' and not instance.new_date:
            obj, pool_created = UnusedHourPool.objects.get_or_create(
                group=slot.group,
                subject=slot.subject,
                teacher=slot.teacher,
                semester=slot.semester,
                original_date=instance.exception_date,
                defaults={'reason': instance.reason or 'Отменено через Живой календарь'}
            )
            if pool_created:
                logger.info(
                    "UnusedHourPool created: group=%s subject=%s date=%s exception_id=%s",
                    slot.group.name, slot.subject.name, instance.exception_date, instance.pk
                )
            else:
                logger.debug(
                    "UnusedHourPool already exists for group=%s subject=%s date=%s",
                    slot.group.name, slot.subject.name, instance.exception_date
                )
        elif instance.exception_type == 'RESCHEDULE':
            updated = UnusedHourPool.objects.filter(
                group=slot.group,
                original_date=instance.exception_date
            ).update(is_recovered=True)
            if updated:
                logger.info(
                    "UnusedHourPool marked recovered: group=%s date=%s count=%s",
                    slot.group.name, instance.exception_date, updated
                )
    except Exception as e:
        logger.exception(
            "track_cancelled_hours failed for exception_id=%s: %s", instance.pk, e
        )


@receiver(pre_delete, sender=ScheduleSlot)
def backup_deleted_slot(sender, instance, **kwargs):
    if instance.is_active:
        try:
            UnusedHourPool.objects.create(
                group=instance.group,
                subject=instance.subject,
                teacher=instance.teacher,
                semester=instance.semester,
                reason='Полное удаление из шахматки расписания'
            )
            logger.info(
                "UnusedHourPool backup created on slot delete: slot_id=%s group=%s subject=%s",
                instance.pk, instance.group.name, instance.subject.name
            )
        except Exception as e:
            logger.exception(
                "backup_deleted_slot failed for slot_id=%s: %s", instance.pk, e
            )