from django.core.management.base import BaseCommand
from schedule.models import ScheduleSlot, Semester, TimeSlot

class Command(BaseCommand):
    help = 'Очистка висячих записей расписания'

    def handle(self, *args, **options):
        deleted_count = 0
        
        for semester in Semester.objects.all():
            if semester.shift == 'MORNING':
                valid_slots = TimeSlot.objects.filter(
                    start_time__gte='08:00:00',
                    start_time__lt='14:00:00'
                )
            else:  # DAY
                valid_slots = TimeSlot.objects.filter(
                    start_time__gte='13:00:00',
                    start_time__lt='19:00:00'
                )
            
            valid_slot_ids = list(valid_slots.values_list('id', flat=True))
            
            invalid_slots = ScheduleSlot.objects.filter(
                semester=semester
            ).exclude(time_slot_id__in=valid_slot_ids)
            
            count = invalid_slots.count()
            if count > 0:
                self.stdout.write(
                    f'Семестр "{semester.name}": найдено {count} висячих записей'
                )
                for slot in invalid_slots:
                    self.stdout.write(
                        f'  - {slot.group.name}, {slot.subject.name}, '
                        f'{slot.get_day_of_week_display()} {slot.start_time}'
                    )
                
                invalid_slots.delete()
                deleted_count += count
        
        if deleted_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Удалено {deleted_count} висячих записей')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ Висячих записей не найдено')
            )