

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AcademicWeek',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester_start_date', models.DateField(verbose_name='Дата начала семестра')),
                ('current_week', models.IntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)], verbose_name='Текущая учебная неделя')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активный семестр')),
            ],
            options={
                'verbose_name': 'Учебная неделя',
                'verbose_name_plural': 'Учебные недели',
                'ordering': ['-semester_start_date'],
            },
        ),
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Название предмета')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='Код предмета')),
                ('type', models.CharField(choices=[('LECTURE', 'Лекция'), ('PRACTICE', 'Практика'), ('SRSP', 'СРСП')], max_length=10, verbose_name='Тип занятия')),
                ('hours_per_semester', models.IntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name='Часов в семестр')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('teacher', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subjects', to='accounts.teacher', verbose_name='Преподаватель')),
            ],
            options={
                'verbose_name': 'Предмет',
                'verbose_name_plural': 'Предметы',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ScheduleSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day_of_week', models.IntegerField(choices=[(0, 'Понедельник'), (1, 'Вторник'), (2, 'Среда'), (3, 'Четверг'), (4, 'Пятница'), (5, 'Суббота')], verbose_name='День недели')),
                ('start_time', models.TimeField(verbose_name='Время начала')),
                ('end_time', models.TimeField(verbose_name='Время окончания')),
                ('classroom', models.CharField(max_length=50, verbose_name='Аудитория')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активно')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_slots', to='accounts.group', verbose_name='Группа')),
                ('teacher', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_slots', to='accounts.teacher', verbose_name='Преподаватель')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_slots', to='schedule.subject', verbose_name='Предмет')),
            ],
            options={
                'verbose_name': 'Слот расписания',
                'verbose_name_plural': 'Слоты расписания',
                'ordering': ['day_of_week', 'start_time'],
            },
        ),
        migrations.CreateModel(
            name='ScheduleException',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exception_date', models.DateField(verbose_name='Дата исключения')),
                ('exception_type', models.CharField(choices=[('CANCEL', 'Отмена'), ('RESCHEDULE', 'Перенос')], max_length=20, verbose_name='Тип исключения')),
                ('reason', models.TextField(verbose_name='Причина')),
                ('new_date', models.DateField(blank=True, null=True, verbose_name='Новая дата')),
                ('new_start_time', models.TimeField(blank=True, null=True, verbose_name='Новое время начала')),
                ('new_end_time', models.TimeField(blank=True, null=True, verbose_name='Новое время окончания')),
                ('new_classroom', models.CharField(blank=True, max_length=50, verbose_name='Новая аудитория')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Создал')),
                ('schedule_slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exceptions', to='schedule.scheduleslot', verbose_name='Слот расписания')),
            ],
            options={
                'verbose_name': 'Исключение в расписании',
                'verbose_name_plural': 'Исключения в расписании',
                'ordering': ['-exception_date'],
                'unique_together': {('schedule_slot', 'exception_date')},
            },
        ),
    ]
