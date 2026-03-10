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

    PARTICIPATION_CHOICES =[
        ('READY', _('Был готов')),
        ('NOT_READY', _('Не готов')),
        ('NONE', _('—')),
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

    grade = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        verbose_name=_("Балл (до 12.5 за неделю, до 100 за рейтинг)")
    )

    participation = models.CharField(
        max_length=20,
        choices=PARTICIPATION_CHOICES,
        default='NONE',
        verbose_name=_("Активность")
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

    old_grade = models.FloatField(null=True, blank=True, verbose_name=_("Старый балл"))
    old_attendance = models.CharField(max_length=20, blank=True, verbose_name=_("Старая посещаемость"))

    new_grade = models.FloatField(null=True, blank=True, verbose_name=_("Новый балл"))
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
                stats, created = StudentStatistics.objects.get_or_create(student=s)
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
            stats, created = cls.objects.get_or_create(student=student)
            stats.recalculate()






@receiver(post_save, sender=JournalEntry)
def trigger_stats_recalculate(sender, instance, **kwargs):
    try:
        stats, created = StudentStatistics.objects.get_or_create(student=instance.student)
        stats.recalculate()
    except Exception:
        pass


class SubjectRating(models.Model):
    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='subject_ratings')
    subject = models.ForeignKey('schedule.Subject', on_delete=models.CASCADE, related_name='student_ratings')
    
    r1_pb = models.FloatField(null=True, blank=True, verbose_name="Р1 ПБ")
    r1_to = models.FloatField(null=True, blank=True, verbose_name="Р1 ТО")
    
    r2_pb = models.FloatField(null=True, blank=True, verbose_name="Р2 ПБ")
    r2_to = models.FloatField(null=True, blank=True, verbose_name="Р2 ТО")
    
    exam_pb = models.FloatField(null=True, blank=True, verbose_name="Экзамен ПБ")
    exam_main = models.FloatField(null=True, blank=True, verbose_name="Экзамен Основной")
    exam_dop = models.FloatField(null=True, blank=True, verbose_name="Экзамен Доп.")

    class Meta:
        verbose_name = "Рейтинг студента"
        verbose_name_plural = "Рейтинги студентов"
        unique_together = ['student', 'subject']

    @property
    def r1_total(self):
        if self.r1_pb is None and self.r1_to is None: return None
        pb = self.r1_pb or 0
        to = self.r1_to or 0
        return round(0.4 * pb + 0.6 * to, 2)

    @property
    def r2_total(self):
        if self.r2_pb is None and self.r2_to is None: return None
        pb = self.r2_pb or 0
        to = self.r2_to or 0
        return round(0.4 * pb + 0.6 * to, 2)

    @property
    def itogo(self):
        r1 = self.r1_total or 0
        r2 = self.r2_total or 0
        return round((r1 + r2) / 4, 2)

    @property
    def final_score(self):
        exam = self.exam_main or self.exam_dop or 0
        return round(self.itogo + exam, 2)

    @property
    def letter_grade(self):
        score = self.final_score
        if score == 0: return 'F'
        if score >= 95: return 'A+'
        if score >= 90: return 'A'
        if score >= 85: return 'B+'
        if score >= 80: return 'B'
        if score >= 75: return 'C+'
        if score >= 70: return 'C'
        if score >= 65: return 'D+'
        if score >= 60: return 'D'
        if score >= 50: return 'E'
        return 'F'



class MatrixStructure(models.Model):
    institute = models.ForeignKey('accounts.Institute', on_delete=models.CASCADE, null=True, blank=True, verbose_name="Институт")
    faculty = models.ForeignKey('accounts.Faculty', on_delete=models.CASCADE, null=True, blank=True, verbose_name="Факультет")
    name = models.CharField(max_length=200, verbose_name="Название структуры (напр. Стандарт 2026)")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    class Meta:
        verbose_name = "Структура ведомости"
        verbose_name_plural = "Структуры ведомостей"

    def __str__(self):
        if self.faculty:
            return f"{self.name} (Фак: {self.faculty.abbreviation})"
        elif self.institute:
            return f"{self.name} (Инст: {self.institute.abbreviation})"
        return f"{self.name} (Глобальная)"

class MatrixColumn(models.Model):
    COL_TYPES =[
        ('WEEK', 'Учебная неделя'),
        ('RATING', 'Рейтинг (Ручной ввод)'),
        ('EXAM', 'Экзамен'),
        ('CALC', 'Вычисляемая (Итог)')
    ]
    structure = models.ForeignKey(MatrixStructure, on_delete=models.CASCADE, related_name='columns')
    name = models.CharField(max_length=100, verbose_name="Название (напр. Неделя 1, Р1 ПБ)")
    col_type = models.CharField(max_length=20, choices=COL_TYPES, default='WEEK')
    week_number = models.IntegerField(null=True, blank=True, verbose_name="Номер недели (если тип 'Неделя')")
    max_score = models.FloatField(default=100.0, verbose_name="Макс. балл")
    order = models.IntegerField(default=0, verbose_name="Порядок отображения")

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.name} ({self.get_col_type_display()})"

class StudentMatrixScore(models.Model):
    student = models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='matrix_scores')
    subject = models.ForeignKey('schedule.Subject', on_delete=models.CASCADE)
    column = models.ForeignKey(MatrixColumn, on_delete=models.CASCADE)
    score = models.FloatField(null=True, blank=True)
    updated_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'subject', 'column']


class StudentPerformancePrediction(models.Model):
    RISK_LEVELS = [
        ('LOW', _('Низкий риск')),
        ('MEDIUM', _('Средний риск')),
        ('HIGH', _('Высокий риск')),
    ]

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='performance_prediction',
        verbose_name=_("Студент")
    )

    predicted_gpa = models.FloatField(
        default=0.0,
        verbose_name=_("Предсказанный GPA")
    )

    risk_level = models.CharField(
        max_length=10,
        choices=RISK_LEVELS,
        default='LOW',
        verbose_name=_("Уровень риска")
    )

    risk_factors = models.JSONField(
        default=dict,
        verbose_name=_("Факторы риска (JSON)"),
        help_text=_("Массив факторов, определенных ИИ")
    )

    gpa_change_percentage = models.FloatField(
        default=0.0,
        verbose_name=_("Процент изменения GPA")
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Дата создания прогноза")
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Дата обновления")
    )

    notes = models.TextField(
        blank=True,
        verbose_name=_("Примечания")
    )

    class Meta:
        verbose_name = _("ИИ Прогноз успеваемости студента")
        verbose_name_plural = _("ИИ Прогнозы успеваемости студентов")
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.get_risk_level_display()}"