# schedule/signals.py
import re
from datetime import datetime
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Group
from .models import AcademicPlan

@receiver(post_save, sender=Group)
def auto_create_rup_for_group(sender, instance, created, **kwargs):
    if created and instance.specialty and instance.academic_year:
        try:
            match = re.search(r'\d{4}', instance.academic_year)
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