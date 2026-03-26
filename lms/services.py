from django.db import transaction
import logging
from .models import Course, CourseCategory, CourseEnrolment, CourseSection
logger = logging.getLogger(__name__)
from accounts.models import Student
from schedule.models import Subject, Semester, ScheduleSlot
from lms.models import CourseModule, FolderResource, Assignment
from datetime import timedelta
import hashlib


class LMSManager:
    @staticmethod
    def get_shared_course_id(subject):
        return f"SUBJ_{subject.id}"

    @staticmethod
    def _legacy_crs_course_id(subject):
        clean_name = subject.name.strip().lower()
        name_hash = hashlib.md5(clean_name.encode('utf-8')).hexdigest()[:8]
        teacher_id = subject.teacher_id if subject.teacher_id else 0
        return f"CRS_{name_hash}_T{teacher_id}"

    @staticmethod
    def get_subject_from_shared_id(shared_id):
        from schedule.models import Subject
        if not shared_id:
            return None

        if shared_id.startswith("SUBJ_"):
            try:
                subj_id = int(shared_id.replace("SUBJ_", "", 1))
                return Subject.objects.filter(id=subj_id).first()
            except ValueError:
                pass
            except Exception:
                logger.exception("get_subject_from_shared_id SUBJ")

        if shared_id.startswith("CRS_"):
            try:
                parts = shared_id.split('_')
                teacher_id = int(parts[2][1:])
                subjects = Subject.objects.filter(teacher_id=teacher_id if teacher_id > 0 else None)
                for sub in subjects:
                    if LMSManager._legacy_crs_course_id(sub) == shared_id:
                        return sub
            except Exception:
                logger.exception("get_subject_from_shared_id CRS")

        if shared_id.startswith("DISC_"):
            try:
                parts = shared_id.split('_')
                disc_id = int(parts[1])
                type_part = parts[3]

                qs = Subject.objects.filter(plan_discipline_id=disc_id, type=type_part)
                sub = qs.first()
                if sub:
                    return sub
            except Exception:
                logger.exception("get_subject_from_shared_id DISC")

        sub = Subject.objects.filter(code=shared_id).first()
        if sub:
            return sub

        for sub in Subject.objects.all():
            base = f"DISC_{sub.plan_discipline_id}" if sub.plan_discipline_id else f"SUBJ_{sub.id}"
            if shared_id.startswith(base) and shared_id.endswith(sub.type):
                return sub

            old_base = f"NAME_{abs(hash(sub.name))}"
            if shared_id.startswith(old_base) and shared_id.endswith(sub.type):
                return sub

        return None

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
    @staticmethod
    def generate_structure_from_schedule(course):
        from journal.models import MatrixStructure
        from testing.models import Quiz
        from schedule.models import Subject, Semester
        
        subject = LMSManager.get_subject_from_shared_id(course.id_number)
        if not subject:
            return False, "Предмет не найден. Убедитесь, что курс привязан к предмету из расписания."

        group = subject.groups.first()
        if not group:
            return False, "У предмета нет привязанных групп."

        semester = Semester.objects.filter(is_active=True, course=group.course).first()
        if not semester:
            semester = Semester.objects.filter(is_active=True).first()

        if not semester:
            return False, "Активный семестр не найден."

        faculty = subject.department.faculty
        institute = faculty.institute

        matrix = MatrixStructure.get_or_create_default(institute=institute, faculty=None)

        course.sections.all().delete()

        for column in matrix.columns.all().order_by('order'):
            section_type = 'REGULAR'
            if column.col_type == 'RATING':
                section_type = 'RATING1' if '1' in column.name else 'RATING2'
            elif column.col_type == 'EXAM':
                section_type = 'EXAM'
            elif column.col_type == 'WEEK':
                section_type = column.week_type if hasattr(column, 'week_type') and column.week_type in ['RED', 'BLUE'] else 'REGULAR'
                
            section = CourseSection.objects.create(
                course=course,
                name=column.name,
                sequence=column.order,
                section_type=section_type,
                matrix_column_id=column.id
            )

            if column.col_type == 'WEEK':
                assign_mod = CourseModule.objects.create(
                    section=section, module_type='ASSIGNMENT',
                    title=f"Задания: {column.name}", sequence=1
                )
                Assignment.objects.create(module=assign_mod, description="Загрузите выполненное задание сюда.", max_score=column.max_score)
            
            elif column.col_type in ['RATING', 'EXAM']:
                quiz_mod = CourseModule.objects.create(
                    section=section, module_type='QUIZ',
                    title=f"Тестирование: {column.name}", sequence=1
                )
                Quiz.objects.create(
                    module=quiz_mod, 
                    description=f"Автоматический тест для колонки '{column.name}'.",
                    passing_score=(column.max_score / 2)
                )

        return True, "Структура LMS успешно сгенерирована на основе Сводной ведомости факультета!"
