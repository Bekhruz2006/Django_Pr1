from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import datetime
from django.utils.translation import gettext_lazy as _

from .models import (
    User, Student, Teacher, Dean, ViceDean, Director, ProRector,
    HeadOfDepartment, HRProfile, SpecialistProfile, Faculty, Department,
    StructureChangeLog
)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == 'STUDENT':
            year = datetime.now().year
            Student.objects.create(user=instance, student_id=f"{year}S{instance.id:05d}")
        elif instance.role == 'TEACHER':
            Teacher.objects.create(user=instance)
        elif instance.role == 'DEAN':
            Dean.objects.create(user=instance)
        elif instance.role == 'VICE_DEAN':
            ViceDean.objects.create(user=instance)
        elif instance.role == 'DIRECTOR':
            Director.objects.create(user=instance)
        elif instance.role == 'PRO_RECTOR':
            ProRector.objects.create(user=instance, title="Заместитель директора")
        elif instance.role == 'HEAD_OF_DEPT':
            HeadOfDepartment.objects.create(user=instance)
        elif instance.role == 'HR':
            HRProfile.objects.get_or_create(user=instance)
        elif instance.role == 'SPECIALIST':
            SpecialistProfile.objects.get_or_create(user=instance)


@receiver(pre_save, sender=Faculty)
def log_faculty_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Faculty.objects.get(pk=instance.pk)
            if old_instance.name != instance.name:
                StructureChangeLog.objects.create(
                    object_type='FACULTY',
                    object_id=instance.pk,
                    object_name=instance.name,
                    field_changed='name',
                    old_value=old_instance.name,
                    new_value=instance.name
                )
        except Faculty.DoesNotExist:
            pass


@receiver(pre_save, sender=Department)
def log_department_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Department.objects.get(pk=instance.pk)
            if old_instance.name != instance.name:
                StructureChangeLog.objects.create(
                    object_type='DEPARTMENT',
                    object_id=instance.pk,
                    object_name=instance.name,
                    field_changed='name',
                    old_value=old_instance.name,
                    new_value=instance.name
                )
        except Department.DoesNotExist:
            pass
