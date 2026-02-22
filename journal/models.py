from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
from accounts.models import Student, Teacher, User
from schedule.models import Subject, ScheduleSlot
from django.db.models.signals import post_save
from django.dispatch import receiver

class JournalEntry(models.Model):
    ATTENDANCE_CHOICES = [
        ('PRESENT', _('Присутствовал')),
        ('ABSENT_ILLNESS', _('НБ-Болезнь')),
        ('ABSENT_VALID', _('НБ-Уважительная')),
        ('ABSENT_INVALID', _('НБ-Неуважительная')),
    ]
    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='journal_entries',
        verbose_name=_("Студент")
    )
    
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='journal_entries',
        verbose_name=_("Предмет")
    )
    
    lesson_date = models.DateField(verbose_name=_("Дата занятия"))
    lesson_time = models.TimeField(verbose_name=_("Время начала пары"))
    lesson_type = models.CharField(
        max_length=10,
        choices=Subject.TYPE_CHOICES,
        verbose_name=_("Тип занятия")
    )

    grade = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name=_("Балл (1-12)")
    )
    
    attendance_status = models.CharField(
        max_length=20,
        choices=ATTENDANCE_CHOICES,
        default='PRESENT',
        verbose_name=_("Статус посещения")
    )

    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Время блокировки")
    )

    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_entries',
        verbose_name=_("Создал")
    )
    
    modified_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='modified_entries',
        verbose_name=_("Изменил")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Запись в журнале")
        verbose_name_plural = _("Записи в журнале")
        ordering = ['-lesson_date', 'lesson_time', 'student__user__last_name']
        unique_together = ['student', 'subject', 'lesson_date', 'lesson_time']
    
    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.subject.name} ({self.lesson_date})"
    
    def save(self, *args, **kwargs):
        if not self.locked_at and self.lesson_date and self.lesson_time:
            lesson_datetime = timezone.make_aware(
                timezone.datetime.combine(self.lesson_date, self.lesson_time)
            )
            self.locked_at = lesson_datetime + timedelta(hours=24)

        if self.grade is not None and self.grade > 0:
            self.attendance_status = 'PRESENT'
        elif self.attendance_status != 'PRESENT':
            self.grade = None
        
        super().save(*args, **kwargs)
    
    def is_locked(self):
        if not self.locked_at:
            return False
        return timezone.now() >= self.locked_at
    
    def can_edit(self, user):
        if self.is_locked():
            return False

        if not hasattr(user, 'teacher_profile'):
            return False
        
        return True
    
    def get_display_value(self):
        if self.grade is not None and self.grade > 0:
            return str(self.grade)
        elif self.attendance_status == 'PRESENT':
            return "✓"
        else:
            return self.get_attendance_status_display()

class JournalChangeLog(models.Model):
    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='change_logs',
        verbose_name=_("Запись")
    )
    
    changed_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("Кто изменил")
    )
    
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Когда"))

    old_grade = models.IntegerField(null=True, blank=True, verbose_name=_("Старый балл"))
    old_attendance = models.CharField(max_length=20, blank=True, verbose_name=_("Старая посещаемость"))

    new_grade = models.IntegerField(null=True, blank=True, verbose_name=_("Новый балл"))
    new_attendance = models.CharField(max_length=20, blank=True, verbose_name=_("Новая посещаемость"))
    
    comment = models.TextField(blank=True, verbose_name=_("Комментарий"))
    
    class Meta:
        verbose_name = _("Лог изменений")
        verbose_name_plural = _("Логи изменений")
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.changed_by.user.get_full_name() if self.changed_by else 'Система'} изменил запись {self.entry.id} в {self.changed_at}"
    
    def get_change_description(self):
        parts = []
        
        if self.old_grade != self.new_grade:
            old = self.old_grade if self.old_grade else "—"
            new = self.new_grade if self.new_grade else "—"
            parts.append(f"балл: {old} → {new}")
        
        if self.old_attendance != self.new_attendance:
            old_display = dict(JournalEntry.ATTENDANCE_CHOICES).get(self.old_attendance, self.old_attendance)
            new_display = dict(JournalEntry.ATTENDANCE_CHOICES).get(self.new_attendance, self.new_attendance)
            parts.append(f"посещаемость: {old_display} → {new_display}")
        
        return ", ".join(parts) if parts else "изменение"

class StudentStatistics(models.Model):
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='statistics',
        verbose_name=_("Студент")
    )
    
    overall_gpa = models.FloatField(default=0.0, verbose_name=_("Общий средний балл"))
    group_rank = models.IntegerField(default=0, verbose_name=_("Рейтинг в группе"))
    
    attendance_percentage = models.FloatField(default=0.0, verbose_name=_("Процент посещаемости"))
    total_lessons = models.IntegerField(default=0, verbose_name=_("Всего занятий"))
    attended_lessons = models.IntegerField(default=0, verbose_name=_("Посещено занятий"))
    
    absent_illness = models.IntegerField(default=0, verbose_name=_("НБ-Болезнь"))
    absent_valid = models.IntegerField(default=0, verbose_name=_("НБ-Уважительная"))
    absent_invalid = models.IntegerField(default=0, verbose_name=_("НБ-Неуважительная"))
    total_absent = models.IntegerField(default=0, verbose_name=_("Всего прогулов"))
    
    subjects_data = models.JSONField(default=dict, verbose_name=_("Данные по предметам"))
    
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("Последнее обновление"))
    
    class Meta:
        verbose_name = _("Статистика студента")
        verbose_name_plural = _("Статистика студентов")
    
    def __str__(self):
        return f"Статистика: {self.student.user.get_full_name()}"
    
    def recalculate(self):
        entries = JournalEntry.objects.filter(student=self.student)
        
        grades = entries.filter(grade__isnull=False, grade__gt=0).values_list('grade', flat=True)
        self.overall_gpa = sum(grades) / len(grades) if grades else 0.0
        
        self.total_lessons = entries.count()
        self.attended_lessons = entries.filter(attendance_status='PRESENT').count()
        self.attendance_percentage = (
            (self.attended_lessons / self.total_lessons * 100) 
            if self.total_lessons > 0 else 0.0
        )
        
        self.absent_illness = entries.filter(attendance_status='ABSENT_ILLNESS').count()
        self.absent_valid = entries.filter(attendance_status='ABSENT_VALID').count()
        self.absent_invalid = entries.filter(attendance_status='ABSENT_INVALID').count()
        self.total_absent = self.absent_illness + self.absent_valid + self.absent_invalid
        
        from schedule.models import Subject
        subjects_stats = {}
        for subject in Subject.objects.filter(journal_entries__student=self.student).distinct():
            subject_entries = entries.filter(subject=subject)
            subject_grades = subject_entries.filter(grade__isnull=False, grade__gt=0).values_list('grade', flat=True)
            
            subject_absent = subject_entries.exclude(attendance_status='PRESENT').count()
            
            subjects_stats[subject.id] = {
                'name': subject.name,
                'average_grade': sum(subject_grades) / len(subject_grades) if subject_grades else 0.0,
                'total_lessons': subject_entries.count(),
                'attended': subject_entries.filter(attendance_status='PRESENT').count(),
                'absent': subject_absent,
            }
        
        self.subjects_data = subjects_stats
        
        if self.student.group:
            group_students = Student.objects.filter(group=self.student.group)
            ranked = []
            for s in group_students:
                stats, _ = StudentStatistics.objects.get_or_create(student=s)
                ranked.append((s.id, stats.overall_gpa))
            
            ranked.sort(key=lambda x: x[1], reverse=True)
            for rank, (student_id, _) in enumerate(ranked, 1):
                if student_id == self.student.id:
                    self.group_rank = rank
                    break
        
        self.save()
    
    @classmethod
    def recalculate_group(cls, group):
        students = Student.objects.filter(group=group)
        for student in students:
            stats, _ = cls.objects.get_or_create(student=student)
            stats.recalculate()






@receiver(post_save, sender=JournalEntry)
def trigger_stats_recalculate(sender, instance, **kwargs):
    try:
        stats, _ = StudentStatistics.objects.get_or_create(student=instance.student)
        stats.recalculate()
    except Exception:
        pass
