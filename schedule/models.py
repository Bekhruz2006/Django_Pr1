# schedule/models.py
from django.db import models
from django.contrib.auth.models import User

class Faculty(models.Model):
    """Факультет"""
    name = models.CharField(max_length=200, verbose_name="Название")
    code = models.CharField(max_length=10, unique=True, verbose_name="Код")
    
    class Meta:
        verbose_name = "Факультет"
        verbose_name_plural = "Факультеты"
    
    def __str__(self):
        return self.name


class Department(models.Model):
    """Кафедра"""
    name = models.CharField(max_length=200, verbose_name="Название")
    code = models.CharField(max_length=10, unique=True, verbose_name="Код")
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, verbose_name="Факультет")
    
    class Meta:
        verbose_name = "Кафедра"
        verbose_name_plural = "Кафедры"
    
    def __str__(self):
        return self.name


class Group(models.Model):
    """Учебная группа"""
    name = models.CharField(max_length=50, unique=True, verbose_name="Название")
    course = models.IntegerField(verbose_name="Курс")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, verbose_name="Кафедра")
    
    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Teacher(models.Model):
    """Преподаватель"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, verbose_name="Кафедра")
    position = models.CharField(max_length=100, verbose_name="Должность", blank=True)
    
    class Meta:
        verbose_name = "Преподаватель"
        verbose_name_plural = "Преподаватели"
    
    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Subject(models.Model):
    """Учебный предмет"""
    name = models.CharField(max_length=200, verbose_name="Название")
    code = models.CharField(max_length=20, unique=True, verbose_name="Код")
    credits = models.IntegerField(verbose_name="Кредиты")
    hours_per_semester = models.IntegerField(default=0, verbose_name="Часов в семестр")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Преподаватель")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, verbose_name="Кафедра")
    
    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class TimeSlot(models.Model):
    """Временной слот (время начала и окончания пары)"""
    start_time = models.TimeField(verbose_name="Время начала")
    end_time = models.TimeField(verbose_name="Время окончания")
    name = models.CharField(max_length=50, blank=True, null=True, verbose_name="Название")
    
    class Meta:
        verbose_name = "Временной слот"
        verbose_name_plural = "Временные слоты"
        ordering = ['start_time']
    
    def __str__(self):
        if self.name:
            return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class ScheduleSlot(models.Model):
    """Занятие в расписании"""
    DAYS_OF_WEEK = [
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
    ]
    
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Группа")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name="Предмет")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Преподаватель")
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK, verbose_name="День недели")
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, verbose_name="Время")
    room = models.CharField(max_length=20, blank=True, null=True, verbose_name="Аудитория/Кабинет")
    
    class Meta:
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        unique_together = ['group', 'day_of_week', 'time_slot']
        ordering = ['day_of_week', 'time_slot__start_time']
    
    def __str__(self):
        day_name = dict(self.DAYS_OF_WEEK)[self.day_of_week]
        return f"{self.group.name} - {self.subject.name} ({day_name}, {self.time_slot})"


class Dean(models.Model):
    """Декан"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dean_profile')
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, verbose_name="Факультет")
    
    class Meta:
        verbose_name = "Декан"
        verbose_name_plural = "Деканы"
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.faculty.name}"