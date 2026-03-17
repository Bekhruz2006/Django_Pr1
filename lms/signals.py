from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from accounts.models import Student
from schedule.models import Subject
from .models import Course, CourseCategory, CourseEnrolment
from lms.models import AssignmentSubmission
from journal.models import JournalEntry
from schedule.models import Subject
from .services import LMSManager

@receiver(post_save, sender=Subject)
def sync_subject_to_lms_course(sender, instance, created, **kwargs):
    shared_id = LMSManager.get_shared_course_id(instance)
    
    category, _ = CourseCategory.objects.get_or_create(
        name=instance.department.name,
        defaults={'faculty': instance.department.faculty}
    )
    
    course, course_created = Course.objects.get_or_create(
        id_number=shared_id,
        defaults={
            'full_name': instance.name,
            'short_name': instance.name[:100],
            'category': category,
            'allowed_department': instance.department,
        }
    )

    if instance.teacher:
        CourseEnrolment.objects.update_or_create(
            course=course,
            user=instance.teacher.user,
            defaults={'role': 'TEACHER', 'is_active': True}
        )

@receiver(m2m_changed, sender=Subject.groups.through)
def sync_groups_to_lms_course(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        shared_id = LMSManager.get_shared_course_id(instance)
        course = Course.objects.filter(id_number=shared_id).first()
        if course and pk_set:
            students = Student.objects.filter(group__id__in=pk_set, status='ACTIVE').select_related('user')
            
            enrolments =[]
            for student in students:
                if not CourseEnrolment.objects.filter(course=course, user=student.user).exists():
                    enrolments.append(CourseEnrolment(
                        course=course,
                        user=student.user,
                        role='STUDENT'
                    ))
            if enrolments:
                CourseEnrolment.objects.bulk_create(enrolments)

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
        course = instance.assignment.module.section.course
        student = instance.student.student_profile
        
        subjects = Subject.objects.filter(groups=student.group)
        target_subject = None
        for sub in subjects:
            if LMSManager.get_shared_course_id(sub) == course.id_number:
                target_subject = sub
                break
                
        if not target_subject:
            return
            
        entry, created = JournalEntry.objects.get_or_create(
            student=student,
            subject=target_subject,
            lesson_date=instance.updated_at.date(),
            defaults={
                'lesson_time': '08:00', 
                'lesson_type': 'PRACTICE',
                'attendance_status': 'PRESENT'
            }
        )
        
        entry.grade = float(instance.score)
        entry.attendance_status = 'PRESENT'
        entry.save()


