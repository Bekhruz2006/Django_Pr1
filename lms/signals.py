from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from accounts.models import Student
from schedule.models import Subject
from .models import Course, CourseCategory, CourseEnrolment
from lms.models import AssignmentSubmission, CourseModule
from journal.models import MatrixStructure, MatrixColumn, StudentMatrixScore
from .services import LMSManager, LMSGradeSynchronizer

@receiver(m2m_changed, sender=Subject.groups.through)
def sync_groups_to_lms_course(sender, instance, action, pk_set, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        from .services import LMSManager
        LMSManager.sync_subject_to_course(instance)

@receiver(post_save, sender=Student)
def sync_student_to_lms_courses(sender, instance, **kwargs):
    if instance.group and instance.status == 'ACTIVE':
        subjects = instance.group.subjects.all()
        shared_codes =[LMSManager.get_shared_course_id(sub) for sub in subjects]
        
        courses = Course.objects.filter(id_number__in=shared_codes)
        
        for course in courses:
            CourseEnrolment.objects.get_or_create(
                course=course,
                user=instance.user,
                defaults={'role': 'STUDENT', 'is_active': True}
            )

@receiver(post_save, sender=AssignmentSubmission)
def sync_lms_grade_to_journal(sender, instance, **kwargs):
    if instance.status == 'GRADED' and instance.score is not None:
        section = instance.assignment.module.section
        LMSGradeSynchronizer.sync_section_grades(section, instance.student, instance.graded_by)

@receiver(post_save, sender=CourseModule)
@receiver(post_delete, sender=CourseModule)
def rebalance_grades_on_module_change(sender, instance, **kwargs):
    if instance.module_type in ['ASSIGNMENT', 'QUIZ']:
        course = instance.section.course
        students = [e.user for e in course.enrolments.filter(role='STUDENT', is_active=True)]
        for student in students:
            LMSGradeSynchronizer.sync_section_grades(instance.section, student)


