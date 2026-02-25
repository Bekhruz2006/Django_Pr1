from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from accounts.models import Student
from schedule.models import Subject
from .models import Course, CourseCategory, CourseEnrolment

@receiver(post_save, sender=Subject)
def sync_subject_to_lms_course(sender, instance, created, **kwargs):
    category, _ = CourseCategory.objects.get_or_create(
        name=instance.department.name,
        defaults={'faculty': instance.department.faculty}
    )
    
    course, course_created = Course.objects.update_or_create(
        id_number=instance.code, # Связываем по коду предмета
        defaults={
            'full_name': f"{instance.name} ({instance.get_type_display()})",
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
        course = Course.objects.filter(id_number=instance.code).first()
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
        subject_codes =[sub.code for sub in subjects]
        
        courses = Course.objects.filter(id_number__in=subject_codes)
        
        for course in courses:
            CourseEnrolment.objects.get_or_create(
                course=course,
                user=instance.user,
                defaults={'role': 'STUDENT', 'is_active': True}
            )