from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
from accounts.models import Student, Teacher, User
from schedule.models import Subject, ScheduleSlot

class JournalEntry(models.Model):
    """ÐÐ°Ð¿Ð¸ÑÑ Ð² Ð¶ÑÑÐ½Ð°Ð»Ðµ - Ð¾ÑÐµÐ½ÐºÐ° Ð¸Ð»Ð¸ Ð¿Ð¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ"""
    
    ATTENDANCE_CHOICES = [
        ('PRESENT', 'ÐÑÐ¸ÑÑÑÑÑÐ²Ð¾Ð²Ð°Ð»'),
        ('ABSENT_ILLNESS', 'ÐÐ-ÐÐ¾Ð»ÐµÐ·Ð½Ñ'),
        ('ABSENT_VALID', 'ÐÐ-Ð£Ð²Ð°Ð¶Ð¸ÑÐµÐ»ÑÐ½Ð°Ñ'),
        ('ABSENT_INVALID', 'ÐÐ-ÐÐµÑÐ²Ð°Ð¶Ð¸ÑÐµÐ»ÑÐ½Ð°Ñ'),
    ]
    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='journal_entries',
        verbose_name="Ð¡ÑÑÐ´ÐµÐ½Ñ"
    )
    
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='journal_entries',
        verbose_name="ÐÑÐµÐ´Ð¼ÐµÑ"
    )
    
    lesson_date = models.DateField(verbose_name="ÐÐ°ÑÐ° Ð·Ð°Ð½ÑÑÐ¸Ñ")
    lesson_time = models.TimeField(verbose_name="ÐÑÐµÐ¼Ñ Ð½Ð°ÑÐ°Ð»Ð° Ð¿Ð°ÑÑ")
    lesson_type = models.CharField(
        max_length=10,
        choices=Subject.TYPE_CHOICES,
        verbose_name="Ð¢Ð¸Ð¿ Ð·Ð°Ð½ÑÑÐ¸Ñ"
    )
    
    # ÐÑÐµÐ½ÐºÐ° Ð¸Ð»Ð¸ Ð¿Ð¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ (Ð²Ð·Ð°Ð¸Ð¼Ð¾Ð¸ÑÐºÐ»ÑÑÐ°ÑÑÐ¸Ðµ)
    grade = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="ÐÐ°Ð»Ð» (1-12)"
    )
    
    attendance_status = models.CharField(
        max_length=20,
        choices=ATTENDANCE_CHOICES,
        default='PRESENT',
        verbose_name="Ð¡ÑÐ°ÑÑÑ Ð¿Ð¾ÑÐµÑÐµÐ½Ð¸Ñ"
    )
    
    # ÐÐ»Ð¾ÐºÐ¸ÑÐ¾Ð²ÐºÐ° ÑÐµÑÐµÐ· 24 ÑÐ°ÑÐ°
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="ÐÑÐµÐ¼Ñ Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²ÐºÐ¸"
    )
    
    # ÐÐµÑÐ°Ð´Ð°Ð½Ð½ÑÐµ
    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_entries',
        verbose_name="Ð¡Ð¾Ð·Ð´Ð°Ð»"
    )
    
    modified_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='modified_entries',
        verbose_name="ÐÐ·Ð¼ÐµÐ½Ð¸Ð»"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "ÐÐ°Ð¿Ð¸ÑÑ Ð² Ð¶ÑÑÐ½Ð°Ð»Ðµ"
        verbose_name_plural = "ÐÐ°Ð¿Ð¸ÑÐ¸ Ð² Ð¶ÑÑÐ½Ð°Ð»Ðµ"
        ordering = ['-lesson_date', 'lesson_time', 'student__user__last_name']
        unique_together = ['student', 'subject', 'lesson_date', 'lesson_time']
    
    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.subject.name} ({self.lesson_date})"
    
    def save(self, *args, **kwargs):
        # ÐÐ²ÑÐ¾Ð¼Ð°ÑÐ¸ÑÐµÑÐºÐ¾Ðµ Ð²ÑÑÐ¸ÑÐ»ÐµÐ½Ð¸Ðµ Ð²ÑÐµÐ¼ÐµÐ½Ð¸ Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²ÐºÐ¸
        if not self.locked_at and self.lesson_date and self.lesson_time:
            lesson_datetime = timezone.make_aware(
                timezone.datetime.combine(self.lesson_date, self.lesson_time)
            )
            self.locked_at = lesson_datetime + timedelta(hours=24)
        
        # ÐÐ°Ð»Ð¸Ð´Ð°ÑÐ¸Ñ: Ð±Ð°Ð»Ð» Ð¸ ÐÐ Ð²Ð·Ð°Ð¸Ð¼Ð¾Ð¸ÑÐºÐ»ÑÑÐ°ÑÑÐ¸Ðµ
        if self.grade is not None and self.grade > 0:
            # ÐÑÐ»Ð¸ ÑÑÐ¾Ð¸Ñ Ð±Ð°Ð»Ð» - ÑÑÐ°ÑÑÑ Ð°Ð²ÑÐ¾Ð¼Ð°ÑÐ¸ÑÐµÑÐºÐ¸ "ÐÑÐ¸ÑÑÑÑÑÐ²Ð¾Ð²Ð°Ð»"
            self.attendance_status = 'PRESENT'
        elif self.attendance_status != 'PRESENT':
            # ÐÑÐ»Ð¸ ÑÑÐ°ÑÑÑ ÐÐ - Ð¿Ð¾Ð»Ðµ Ð±Ð°Ð»Ð»Ð° Ð¾ÑÐ¸ÑÐ°ÐµÑÑÑ
            self.grade = None
        
        super().save(*args, **kwargs)
    
    def is_locked(self):
        """ÐÐ ÐÐ¢ÐÐ§ÐÐ! ÐÑÐ¾Ð²ÐµÑÐºÐ° Ð±Ð»Ð¾ÐºÐ¸ÑÐ¾Ð²ÐºÐ¸ ÑÐµÑÐµÐ· 24 ÑÐ°ÑÐ°"""
        if not self.locked_at:
            return False
        return timezone.now() >= self.locked_at
    
    def can_edit(self, user):
        """ÐÑÐ¾Ð²ÐµÑÐºÐ° Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑÐ¸ ÑÐµÐ´Ð°ÐºÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ñ"""
        # ÐÑÐ°Ð²Ð¸Ð»Ð¾ 24 ÑÐ°ÑÐ¾Ð² ÐÐ ÐÐ¢ÐÐÐÐ¯ÐÐ¢Ð¡Ð¯ ÐÐÐÐÐÐÐ
        if self.is_locked():
            return False
        
        # Ð¢Ð¾Ð»ÑÐºÐ¾ Ð¿ÑÐµÐ¿Ð¾Ð´Ð°Ð²Ð°ÑÐµÐ»Ñ Ð¼Ð¾Ð¶ÐµÑ ÑÐµÐ´Ð°ÐºÑÐ¸ÑÐ¾Ð²Ð°ÑÑ
        if not hasattr(user, 'teacher_profile'):
            return False
        
        return True
    
    def get_display_value(self):
        """ÐÑÐ¾Ð±ÑÐ°Ð¶Ð°ÐµÐ¼Ð¾Ðµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ðµ ÑÑÐµÐ¹ÐºÐ¸"""
        if self.grade is not None and self.grade > 0:
            return str(self.grade)
        elif self.attendance_status == 'PRESENT':
            return "â"
        else:
            return self.get_attendance_status_display()


class JournalChangeLog(models.Model):
    """ÐÑÑÐ¾ÑÐ¸Ñ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹ Ð² Ð¶ÑÑÐ½Ð°Ð»Ðµ"""
    
    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='change_logs',
        verbose_name="ÐÐ°Ð¿Ð¸ÑÑ"
    )
    
    changed_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="ÐÑÐ¾ Ð¸Ð·Ð¼ÐµÐ½Ð¸Ð»"
    )
    
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="ÐÐ¾Ð³Ð´Ð°")
    
    # Ð¡ÑÐ°ÑÑÐµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ñ
    old_grade = models.IntegerField(null=True, blank=True, verbose_name="Ð¡ÑÐ°ÑÑÐ¹ Ð±Ð°Ð»Ð»")
    old_attendance = models.CharField(max_length=20, blank=True, verbose_name="Ð¡ÑÐ°ÑÐ°Ñ Ð¿Ð¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ")
    
    # ÐÐ¾Ð²ÑÐµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ñ
    new_grade = models.IntegerField(null=True, blank=True, verbose_name="ÐÐ¾Ð²ÑÐ¹ Ð±Ð°Ð»Ð»")
    new_attendance = models.CharField(max_length=20, blank=True, verbose_name="ÐÐ¾Ð²Ð°Ñ Ð¿Ð¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ")
    
    comment = models.TextField(blank=True, verbose_name="ÐÐ¾Ð¼Ð¼ÐµÐ½ÑÐ°ÑÐ¸Ð¹")
    
    class Meta:
        verbose_name = "ÐÐ¾Ð³ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹"
        verbose_name_plural = "ÐÐ¾Ð³Ð¸ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹"
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.changed_by.user.get_full_name() if self.changed_by else 'Ð¡Ð¸ÑÑÐµÐ¼Ð°'} Ð¸Ð·Ð¼ÐµÐ½Ð¸Ð» Ð·Ð°Ð¿Ð¸ÑÑ {self.entry.id} Ð² {self.changed_at}"
    
    def get_change_description(self):
        """Ð§ÐµÐ»Ð¾Ð²ÐµÐºÐ¾ÑÐ¸ÑÐ°ÐµÐ¼Ð¾Ðµ Ð¾Ð¿Ð¸ÑÐ°Ð½Ð¸Ðµ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ñ"""
        parts = []
        
        if self.old_grade != self.new_grade:
            old = self.old_grade if self.old_grade else "â"
            new = self.new_grade if self.new_grade else "â"
            parts.append(f"Ð±Ð°Ð»Ð»: {old} â {new}")
        
        if self.old_attendance != self.new_attendance:
            old_display = dict(JournalEntry.ATTENDANCE_CHOICES).get(self.old_attendance, self.old_attendance)
            new_display = dict(JournalEntry.ATTENDANCE_CHOICES).get(self.new_attendance, self.new_attendance)
            parts.append(f"Ð¿Ð¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ: {old_display} â {new_display}")
        
        return ", ".join(parts) if parts else "Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ"


class StudentStatistics(models.Model):
    """ÐÑÑ ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ¸ ÑÑÑÐ´ÐµÐ½ÑÐ° Ð´Ð»Ñ Ð¾Ð¿ÑÐ¸Ð¼Ð¸Ð·Ð°ÑÐ¸Ð¸"""
    
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='statistics',
        verbose_name="Ð¡ÑÑÐ´ÐµÐ½Ñ"
    )
    
    # GPA Ð¸ ÑÐµÐ¹ÑÐ¸Ð½Ð³
    overall_gpa = models.FloatField(default=0.0, verbose_name="ÐÐ±ÑÐ¸Ð¹ ÑÑÐµÐ´Ð½Ð¸Ð¹ Ð±Ð°Ð»Ð»")
    group_rank = models.IntegerField(default=0, verbose_name="Ð ÐµÐ¹ÑÐ¸Ð½Ð³ Ð² Ð³ÑÑÐ¿Ð¿Ðµ")
    
    # ÐÐ¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ
    attendance_percentage = models.FloatField(default=0.0, verbose_name="ÐÑÐ¾ÑÐµÐ½Ñ Ð¿Ð¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÐ¸")
    total_lessons = models.IntegerField(default=0, verbose_name="ÐÑÐµÐ³Ð¾ Ð·Ð°Ð½ÑÑÐ¸Ð¹")
    attended_lessons = models.IntegerField(default=0, verbose_name="ÐÐ¾ÑÐµÑÐµÐ½Ð¾ Ð·Ð°Ð½ÑÑÐ¸Ð¹")
    
    # Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° Ð¿Ð¾ Ð¿ÑÐµÐ´Ð¼ÐµÑÐ°Ð¼ (JSON Ð´Ð»Ñ Ð³Ð¸Ð±ÐºÐ¾ÑÑÐ¸)
    subjects_data = models.JSONField(default=dict, verbose_name="ÐÐ°Ð½Ð½ÑÐµ Ð¿Ð¾ Ð¿ÑÐµÐ´Ð¼ÐµÑÐ°Ð¼")
    
    last_updated = models.DateTimeField(auto_now=True, verbose_name="ÐÐ¾ÑÐ»ÐµÐ´Ð½ÐµÐµ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ")
    
    class Meta:
        verbose_name = "Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° ÑÑÑÐ´ÐµÐ½ÑÐ°"
        verbose_name_plural = "Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° ÑÑÑÐ´ÐµÐ½ÑÐ¾Ð²"
    
    def __str__(self):
        return f"Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ°: {self.student.user.get_full_name()}"
    
    def recalculate(self):
        """ÐÐµÑÐµÑÑÐµÑ Ð²ÑÐµÐ¹ ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ¸"""
        entries = JournalEntry.objects.filter(student=self.student)
        
        # ÐÐ±ÑÐ¸Ð¹ ÑÑÐµÐ´Ð½Ð¸Ð¹ Ð±Ð°Ð»Ð»
        grades = entries.filter(grade__isnull=False, grade__gt=0).values_list('grade', flat=True)
        self.overall_gpa = sum(grades) / len(grades) if grades else 0.0
        
        # ÐÐ¾ÑÐµÑÐ°ÐµÐ¼Ð¾ÑÑÑ
        self.total_lessons = entries.count()
        self.attended_lessons = entries.filter(attendance_status='PRESENT').count()
        self.attendance_percentage = (
            (self.attended_lessons / self.total_lessons * 100) 
            if self.total_lessons > 0 else 0.0
        )
        
        # Ð¡ÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ° Ð¿Ð¾ Ð¿ÑÐµÐ´Ð¼ÐµÑÐ°Ð¼
        subjects_stats = {}
        for subject in Subject.objects.filter(journal_entries__student=self.student).distinct():
            subject_entries = entries.filter(subject=subject)
            subject_grades = subject_entries.filter(grade__isnull=False, grade__gt=0).values_list('grade', flat=True)
            
            subjects_stats[subject.id] = {
                'name': subject.name,
                'average_grade': sum(subject_grades) / len(subject_grades) if subject_grades else 0.0,
                'total_lessons': subject_entries.count(),
                'attended': subject_entries.filter(attendance_status='PRESENT').count(),
            }
        
        self.subjects_data = subjects_stats
        
        # Ð ÐµÐ¹ÑÐ¸Ð½Ð³ Ð² Ð³ÑÑÐ¿Ð¿Ðµ
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
        """ÐÐµÑÐµÑÑÐµÑ ÑÑÐ°ÑÐ¸ÑÑÐ¸ÐºÐ¸ Ð´Ð»Ñ Ð²ÑÐµÐ¹ Ð³ÑÑÐ¿Ð¿Ñ (Ð´Ð»Ñ ÑÐµÐ¹ÑÐ¸Ð½Ð³Ð¾Ð²)"""
        students = Student.objects.filter(group=group)
        for student in students:
            stats, _ = cls.objects.get_or_create(student=student)
            stats.recalculate()