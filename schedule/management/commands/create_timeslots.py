# schedule/management/commands/create_timeslots.py
from django.core.management.base import BaseCommand
from schedule.models import TimeSlot
from datetime import time

class Command(BaseCommand):
    help = 'Создание стандартных временных слотов'

    def handle(self, *args, **options):
        # Стандартные временные слоты (10 пар)
        slots = [
            (time(8, 0), time(8, 50), '1 пара'),
            (time(9, 0), time(9, 50), '2 пара'),
            (time(10, 0), time(10, 50), '3 пара'),
            (time(11, 0), time(11, 50), '4 пара'),
            (time(12, 0), time(12, 50), '5 пара'),
            (time(13, 0), time(13, 50), '6 пара'),
            (time(14, 0), time(14, 50), '7 пара'),
            (time(15, 0), time(15, 50), '8 пара'),
            (time(16, 0), time(16, 50), '9 пара'),
            (time(17, 0), time(17, 50), '10 пара'),
            (time(18, 0), time(18, 50), '11 пара'),
        ]
        
        created_count = 0
        for start, end, name in slots:
            obj, created = TimeSlot.objects.get_or_create(
                start_time=start,
                end_time=end,
                defaults={'name': name}
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Создан слот: {name} ({start}-{end})'))
            else:
                self.stdout.write(f'  Уже существует: {name}')
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Создано {created_count} новых временных слотов'))
        self.stdout.write(f'📊 Всего в системе: {TimeSlot.objects.count()} слотов')