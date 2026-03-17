from django.db import transaction
from .models import Course, CourseCategory, CourseEnrolment, CourseSection
from accounts.models import Student
from schedule.models import Subject, Semester, ScheduleSlot
from lms.models import CourseModule, FolderResource, Assignment
from datetime import timedelta


class LMSManager:
    @staticmethod
    def get_shared_course_id(subject):
        if subject.plan_discipline_id:
            base = f"DISC_{subject.plan_discipline_id}"
        else:
            base = f"SUBJ_{subject.id}"
        teacher_id = subject.teacher_id if subject.teacher_id else 0
        return f"{base}_T{teacher_id}_{subject.type}"

    @staticmethod
    def get_subject_from_shared_id(shared_id):
        from schedule.models import Subject
        if not shared_id:
            return None
            
        if shared_id.startswith("DISC_"):
            try:
                parts = shared_id.split('_')
                disc_id = int(parts[1])
                type_part = parts[3]
                
                qs = Subject.objects.filter(plan_discipline_id=disc_id, type=type_part)
                sub = qs.first()
                if sub: return sub
            except:
                pass
                
        if shared_id.startswith("SUBJ_"):
            try:
                parts = shared_id.split('_')
                subj_id = int(parts[1])
                sub = Subject.objects.filter(id=subj_id).first()
                if sub: return sub
            except:
                pass
        
        sub = Subject.objects.filter(code=shared_id).first()
        if sub: return sub
        
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
        
        matrix = MatrixStructure.objects.filter(faculty=faculty, is_active=True).first()
        if not matrix:
            matrix = MatrixStructure.objects.filter(institute=institute, faculty__isnull=True, is_active=True).first()
        if not matrix:
            matrix = MatrixStructure.objects.filter(faculty__isnull=True, institute__isnull=True, is_active=True).first()
            
        if not matrix or not matrix.columns.exists():
            return False, "Структура Сводной ведомости (Матрица) не настроена деканатом. Настройте её в Журнале."

        course.sections.all().delete()

        for column in matrix.columns.all().order_by('order'):
            section_type = 'REGULAR'
            if column.col_type == 'RATING':
                section_type = 'RATING1' if '1' in column.name else 'RATING2'
            elif column.col_type == 'EXAM':
                section_type = 'EXAM'
                
            section = CourseSection.objects.create(
                course=course,
                name=column.name,
                sequence=column.order,
                section_type=section_type
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
                    passing_score=(column.max_score / 2) # Проходной балл 50%
                )

        return True, "Структура LMS успешно сгенерирована на основе Сводной ведомости факультета!"
