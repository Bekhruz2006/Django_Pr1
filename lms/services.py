from django.db import transaction
from .models import Course, CourseCategory, CourseEnrolment, CourseSection
from accounts.models import Student
from schedule.models import Subject, Semester, ScheduleSlot
from lms.models import CourseModule, FolderResource, Assignment
from datetime import timedelta


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
    @staticmethod
    def generate_structure_from_schedule(course):
        subject = Subject.objects.filter(code=course.id_number).first()
        if not subject:
            return False, "Предмет не найден. Убедитесь, что ID-номер курса совпадает с кодом предмета (Силлабуса)."

        group = subject.groups.first()
        if not group:
            return False, "У предмета нет привязанных групп."

        semester = Semester.objects.filter(is_active=True, course=group.course).first()
        if not semester:
            semester = Semester.objects.filter(is_active=True).first()

        if not semester or not semester.start_date or not semester.end_date:
            return False, "Активный семестр с датами не найден."

        slots = ScheduleSlot.objects.filter(subject=subject, semester=semester, is_active=True).order_by('day_of_week', 'start_time')
        if not slots.exists():
            return False, "Нет составленного расписания для данного предмета в текущем семестре."

        course.sections.all().delete()

        start_date = semester.start_date
        end_date = semester.end_date
        current_date = start_date

        week_num = 1
        lesson_counter = 1

        while current_date <= end_date:
            week_start = current_date - timedelta(days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            week_type = 'RED' if week_num % 2 != 0 else 'BLUE'

            week_slots =[]
            for slot in slots:
                if slot.week_type == 'EVERY' or slot.week_type == week_type:
                    lesson_date = week_start + timedelta(days=slot.day_of_week)
                    if start_date <= lesson_date <= end_date:
                        week_slots.append({'slot': slot, 'date': lesson_date})

            if week_slots:
                week_slots.sort(key=lambda x: (x['date'], x['slot'].start_time))

                is_last_week = (current_date + timedelta(days=7)) > end_date
                section_name = f"Неделя {week_num} (Дата: {week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')})"
                if is_last_week:
                    section_name += " [Последняя неделя]"

                section = CourseSection.objects.create(
                    course=course,
                    name=section_name,
                    sequence=week_num
                )

                seq = 1
                for item in week_slots:
                    slot = item['slot']
                    l_date = item['date']

                    lesson_title = f"{lesson_counter} занятие (Дата {l_date.strftime('%d.%m.%Y')}) ({slot.get_lesson_type_display()})"

                    CourseModule.objects.create(
                        section=section, module_type='LABEL',
                        title=lesson_title, sequence=seq
                    )
                    seq += 1

                    folder_mod = CourseModule.objects.create(
                        section=section, module_type='FOLDER',
                        title=f"Материалы: {lesson_title}", sequence=seq
                    )
                    FolderResource.objects.create(module=folder_mod)
                    seq += 1

                    quiz_mod = CourseModule.objects.create(
                        section=section, module_type='QUIZ',
                        title=f"Тест: {lesson_title}", sequence=seq
                    )
                    from testing.models import Quiz
                    Quiz.objects.create(module=quiz_mod, description="Тест по материалам занятия")
                    seq += 1

                    assign_mod = CourseModule.objects.create(
                        section=section, module_type='ASSIGNMENT',
                        title=f"Задание: {lesson_title}", sequence=seq
                    )
                    Assignment.objects.create(module=assign_mod, description="Задание для самостоятельной работы")
                    seq += 1

                    lesson_counter += 1

            current_date += timedelta(days=7)
            week_num += 1

        return True, "Структура успешно сгенерирована из расписания!"
