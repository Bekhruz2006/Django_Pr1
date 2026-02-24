from django.db import transaction
from .models import Course, CourseCategory, CourseEnrolment, CourseSection
from accounts.models import Student

class LMSManager:
    @staticmethod
    def sync_subject_to_course(subject):
        with transaction.atomic():
            category, _ = CourseCategory.objects.get_or_create(
                name=subject.department.name,
                faculty=subject.department.faculty
            )
            
            course, created = Course.objects.get_or_create(
                id_number=subject.code,
                defaults={
                    'category': category,
                    'full_name': f"{subject.name} ({subject.get_type_display()})",
                    'short_name': subject.name[:50],
                }
            )

            if created:
                for i in range(1, subject.semester_weeks + 1):
                    CourseSection.objects.create(
                        course=course,
                        name=f"Неделя {i}",
                        sequence=i
                    )

            if subject.teacher:
                CourseEnrolment.objects.get_or_create(
                    course=course,
                    user=subject.teacher.user,
                    defaults={'role': 'TEACHER'}
                )

            for group in subject.groups.all():
                students = Student.objects.filter(group=group, status='ACTIVE')
                for student in students:
                    CourseEnrolment.objects.get_or_create(
                        course=course,
                        user=student.user,
                        defaults={'role': 'STUDENT'}
                    )
            return course