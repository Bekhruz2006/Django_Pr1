from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date, time, timedelta
import random
import uuid

class Command(BaseCommand):
    help = 'Заполняет БД тестовыми данными (ИТРЗС, Факультеты, Студенты, LMS, Журналы)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Запуск масштабной генерации данных (ИТРЗС) ==='))
        try:
            with transaction.atomic():
                self._clean_db()
                self._create_structure()
                self._create_infrastructure()
                self._create_users_and_groups()
                self._create_rup_and_subjects()
                self._create_schedule()
                self._create_journal_and_matrix()
                self._create_lms_courses()
                self._create_orders()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Критическая ошибка: {e}'))
            import traceback
            traceback.print_exc()
            raise
        self.stdout.write(self.style.SUCCESS('✅ Тестовые данные успешно сгенерированы!'))
        self._print_credentials()

    def _clean_db(self):
        self.stdout.write('  → Очистка старой базы данных...')
        from schedule.models import AcademicPlan, SubjectTemplate, Subject, Semester, TimeSlot, Building, Classroom, ScheduleSlot
        from accounts.models import Institute, Faculty, Department, Specialty, User, Group, Student, Teacher, Order
        from journal.models import JournalEntry, MatrixStructure
        from lms.models import CourseCategory, Course
        from news.models import News
        from chat.models import ChatRoom

        Order.objects.all().delete()
        JournalEntry.objects.all().delete()
        ScheduleSlot.objects.all().delete()
        Course.objects.all().delete()
        CourseCategory.objects.all().delete()
        Subject.objects.all().delete()
        AcademicPlan.objects.all().delete()
        SubjectTemplate.objects.all().delete()
        Student.objects.all().delete()
        Group.objects.all().delete()
        Teacher.objects.all().delete()
        Specialty.objects.all().delete()
        Department.objects.all().delete()
        Faculty.objects.all().delete()
        Institute.objects.all().delete()
        Building.objects.all().delete()
        TimeSlot.objects.all().delete()
        Semester.objects.all().delete()
        MatrixStructure.objects.all().delete()
        News.objects.all().delete()
        ChatRoom.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def _create_structure(self):
        from accounts.models import Institute, Faculty, Department, Specialty
        self.stdout.write('  → Создание структуры ВУЗа (ИТРЗС)...')

        self.institute, _ = Institute.objects.get_or_create(
            abbreviation='ИТРЗС',
            defaults={'name': 'Институти технологияи рақамӣ ва зеҳни сунъӣ', 'address': 'г. Душанбе'}
        )

        self.faculty_ai, _ = Faculty.objects.get_or_create(code='ФЗС', defaults={'institute': self.institute, 'name': 'Зеҳни сунъӣ'})
        self.faculty_nm, _ = Faculty.objects.get_or_create(code='ФТР', defaults={'institute': self.institute, 'name': 'Табиӣ-риёзӣ'})
        
        self.dept_ai = Department.objects.create(name='Кафедраи зеҳни сунъӣ ва омӯзиши мошинӣ', faculty=self.faculty_ai, total_hours_budget=5000)
        self.dept_prog = Department.objects.create(name='Кафедраи барномасозӣ', faculty=self.faculty_ai, total_hours_budget=4500)
        
        self.dept_math = Department.objects.create(name='Кафедраи математикаи олӣ', faculty=self.faculty_nm, total_hours_budget=6000)
        self.dept_phys = Department.objects.create(name='Кафедраи физика', faculty=self.faculty_nm, total_hours_budget=4000)

        self.spec_ai = Specialty.objects.create(code='1-40 01 01', department=self.dept_ai, name='Зеҳни сунъӣ', qualification='Бакалавр')
        self.spec_prog = Specialty.objects.create(code='1-40 01 02', department=self.dept_prog, name='Барномасозии системавӣ', qualification='Бакалавр')
        self.spec_math = Specialty.objects.create(code='1-31 03 01', department=self.dept_math, name='Математикаи амалӣ', qualification='Бакалавр')

    def _create_infrastructure(self):
        from schedule.models import Building, Classroom, TimeSlot
        self.stdout.write('  → Создание инфраструктуры (Корпуса, Аудитории, Звонки)...')

        self.building = Building.objects.create(name='Бинои асосӣ', institute=self.institute, address='Душанбе')
        
        self.classrooms =[]
        for i in range(1, 6):
            self.classrooms.append(Classroom.objects.create(building=self.building, number=f'10{i}', floor=1, capacity=30, room_type='PRACTICE'))
            self.classrooms.append(Classroom.objects.create(building=self.building, number=f'20{i}', floor=2, capacity=100, room_type='LECTURE'))
            self.classrooms.append(Classroom.objects.create(building=self.building, number=f'30{i}', floor=3, capacity=25, room_type='COMPUTER'))

        times =[(time(8,0), time(8,50)), (time(9,0), time(9,50)), (time(10,10), time(11,0)), (time(11,10), time(12,0))]
        self.time_slots =[]
        for i, (st, et) in enumerate(times, 1):
            ts = TimeSlot.objects.create(institute=self.institute, shift='MORNING', number=i, start_time=st, end_time=et, duration=50)
            self.time_slots.append(ts)

    def _create_users_and_groups(self):
            from accounts.models import User, Dean, Teacher, Group, Student
            self.stdout.write('  → Создание пользователей (Деканы, Преподаватели, Массив студентов)...')
            PWD = 'test' 

            if not User.objects.filter(username='admin').exists():
                User.objects.create_superuser('admin', 'admin@test.com', 'admin', first_name='Администратор', last_name='Системы', role='DIRECTOR')

            def make_user(username, first, last, role):
                u, created = User.objects.get_or_create(username=username, defaults={'first_name': first, 'last_name': last, 'role': role})
                if created: 
                    u.set_password(PWD)
                    u.save()
                return u

            self.dean_ai_u = make_user('dean_ai', 'Рустам', 'Бобоев', 'DEAN')
            if hasattr(self.dean_ai_u, 'dean_profile'):
                self.dean_ai_u.dean_profile.faculty = self.faculty_ai
                self.dean_ai_u.dean_profile.save()

            self.dean_nm_u = make_user('dean_nm', 'Сафаралӣ', 'Қурбонов', 'DEAN')
            if hasattr(self.dean_nm_u, 'dean_profile'):
                self.dean_nm_u.dean_profile.faculty = self.faculty_nm
                self.dean_nm_u.dean_profile.save()

            self.teachers = []
            t_data =[
                ('Абдулло', 'Раҳимов', 'Доцент', self.dept_ai), 
                ('Зарина', 'Саидова', 'Ст. преподаватель', self.dept_prog), 
                ('Фирдавс', 'Гафуров', 'Ассистент', self.dept_math),
                ('Меҳроб', 'Назаров', 'Профессор', self.dept_phys)
            ]
            for i, (fn, ln, title, dept) in enumerate(t_data):
                u = make_user(f'teacher{i+1}', fn, ln, 'TEACHER')
                
                if hasattr(u, 'teacher_profile'):
                    t = u.teacher_profile
                    t.department = dept
                    t.title = title
                    t.save()
                    self.teachers.append(t)

            self.groups = []
            group_configs =[
                ('400101-24А', self.spec_ai, 1), ('400101-23А', self.spec_ai, 2),
                ('400102-24Б', self.spec_prog, 1), ('400102-23Б', self.spec_prog, 2),
                ('310301-24В', self.spec_math, 1), ('310301-23В', self.spec_math, 2),
            ]
            for name, spec, course in group_configs:
                g = Group.objects.create(name=name, specialty=spec, course=course, academic_year='2025-2026', curator=random.choice(self.teachers))
                self.groups.append(g)

            male_names =['Алишер', 'Фирдавс', 'Рустам', 'Меҳроб', 'Далер', 'Сино', 'Фарҳод', 'Азиз', 'Хуршед', 'Умед', 'Сӯҳроб', 'Ҷаҳонгир', 'Бахтиёр', 'Илҳом', 'Беҳрӯз', 'Шоҳрух']
            female_names =['Нилуфар', 'Зарина', 'Мадина', 'Шоира', 'Гулрӯ', 'Парвина', 'Сурайё', 'Таҳмина', 'Малика', 'Фарзона', 'Ситоара', 'Шаҳноза', 'Нигина', 'Маҳина']
            surnames =['Каримов', 'Шарипов', 'Раҳимов', 'Турсунов', 'Сафаров', 'Азизов', 'Мирзоев', 'Расулов', 'Қодиров', 'Назаров', 'Исмоилов', 'Бобоев', 'Ҷалилов', 'Одинаев']

            self.stdout.write('    Генерация студентов (по 15 человек в группе)...')
            student_counter = 1
            for group in self.groups:
                for i in range(15):
                    is_male = random.choice([True, False])
                    first_name = random.choice(male_names) if is_male else random.choice(female_names)
                    surname = random.choice(surnames)
                    if not is_male:
                        surname += 'а'

                    username = f"st{group.course}_{group.id}_{i+1}"
                    u = make_user(username, first_name, surname, 'STUDENT')
                    
                    if hasattr(u, 'student_profile'):
                        s = u.student_profile
                        s.group = group
                        s.course = group.course
                        s.specialty = group.specialty
                        s.student_id = f"25S{student_counter:05d}"
                        s.status = 'ACTIVE'
                        s.financing_type = random.choice(['BUDGET', 'CONTRACT'])
                        s.save()
                        student_counter += 1



    def _create_rup_and_subjects(self):
        from schedule.models import AcademicPlan, SubjectTemplate, PlanDiscipline, Subject, Semester
        self.stdout.write('  → Создание РУП и Дисциплин...')

        self.semester = Semester.get_current()

        disciplines_data =[
            ('Омӯзиши мошинӣ (ML)', 5, 32, 32, 0, self.teachers[0]),
            ('Барномасозӣ дар Python', 4, 16, 32, 16, self.teachers[1]),
            ('Математикаи дискретӣ', 4, 32, 16, 0, self.teachers[2]),
            ('Физикаи квантӣ', 3, 16, 16, 16, self.teachers[3]),
        ]

        self.subjects =[]
        for name, cred, lec, prac, srsp, teacher in disciplines_data:
            tmpl, _ = SubjectTemplate.objects.get_or_create(name=name)
            
            subj = Subject.objects.create(
                code=f'SUBJ-{uuid.uuid4().hex[:6]}',
                name=name, department=teacher.department, type='LECTURE', 
                teacher=teacher, lecture_hours=lec, practice_hours=prac, control_hours=srsp,
                is_active=True
            )
            subj.groups.set(self.groups)
            self.subjects.append(subj)

    def _create_schedule(self):
        from schedule.models import ScheduleSlot
        self.stdout.write('  → Построение расписания...')
        
        schedule_slots =[]
        for g_idx, group in enumerate(self.groups):
            for day in range(3):  
                for ts_idx in range(2): 
                    subj = self.subjects[(g_idx + day + ts_idx) % len(self.subjects)]
                    room = self.classrooms[(g_idx + day) % len(self.classrooms)]
                    ts = self.time_slots[ts_idx]
                    
                    schedule_slots.append(ScheduleSlot(
                        group=group, semester=self.semester, day_of_week=day, time_slot=ts,
                        subject=subj, teacher=subj.teacher, lesson_type=subj.type, 
                        classroom=room, room=room.number, start_time=ts.start_time, end_time=ts.end_time,
                        is_active=True, week_type='EVERY'
                    ))
        ScheduleSlot.objects.bulk_create(schedule_slots)

    def _create_journal_and_matrix(self):
        from journal.models import JournalEntry, StudentStatistics, MatrixStructure, MatrixColumn, StudentMatrixScore
        from accounts.models import Student
        self.stdout.write('  → Генерация Журнала (сотни оценок) и Матрицы Болонской системы...')

        today = timezone.now().date()
        start_date = today - timedelta(days=20)

        matrix = MatrixStructure.get_or_create_default(institute=self.institute, faculty=None)
        matrix_cols = list(matrix.columns.all())

        entries = []
        matrix_scores =[]
        students = list(Student.objects.filter(status='ACTIVE'))
        
        for student in students:
            student_type = student.id % 4 
            
            for subj in self.subjects:
                for day_offset in range(5):
                    lesson_date = start_date + timedelta(days=day_offset * 3)
                    if lesson_date > today: continue
                    
                    attendance = 'PRESENT'
                    grade = None
                    rand_val = random.random()

                    if student_type == 0:
                        if rand_val < 0.05: attendance = 'ABSENT_VALID'
                    elif student_type == 1:
                        if rand_val < 0.15: attendance = 'ABSENT_ILLNESS'
                    elif student_type == 2:
                        if rand_val < 0.25: attendance = 'ABSENT_INVALID'
                    else:
                        if rand_val < 0.40: attendance = 'ABSENT_INVALID'

                    entries.append(JournalEntry(
                        student=student, subject=subj, lesson_date=lesson_date, 
                        lesson_time=time(8,0), lesson_type=subj.type, 
                        grade=grade, attendance_status=attendance, created_by=subj.teacher
                    ))

                for col in matrix_cols:
                    if col.col_type in ['RATING', 'EXAM']:
                        score = 0
                        if student_type == 0: score = col.max_score * random.uniform(0.9, 1.0)
                        elif student_type == 1: score = col.max_score * random.uniform(0.75, 0.89)
                        elif student_type == 2: score = col.max_score * random.uniform(0.55, 0.74)
                        else: score = col.max_score * random.uniform(0.2, 0.5)
                        
                        matrix_scores.append(StudentMatrixScore(
                            student=student, subject=subj, column=col, score=round(score, 1)
                        ))

        JournalEntry.objects.bulk_create(entries, ignore_conflicts=True)
        StudentMatrixScore.objects.bulk_create(matrix_scores, ignore_conflicts=True)

        for group in self.groups:
            StudentStatistics.recalculate_group(group)

    def _create_lms_courses(self):
        from lms.models import CourseCategory, Course, CourseEnrolment, CourseSection, CourseModule, PageContent, Assignment
        from lms.services import LMSManager
        self.stdout.write('  → Создание LMS (Курсы, Модули)...')

        cat = CourseCategory.objects.create(name='Кафедраи зеҳни сунъӣ', faculty=self.faculty_ai)

        for subj in self.subjects:
            course = Course.objects.create(
                id_number=LMSManager.get_shared_course_id(subj),
                category=cat, full_name=subj.name, short_name=subj.name[:20], 
                summary=f'Официальный курс по дисциплине {subj.name}', is_visible=True
            )
            
            CourseEnrolment.objects.create(course=course, user=subj.teacher.user, role='TEACHER')
            
            enrolments =[]
            for g in subj.groups.all():
                for s in g.students.all():
                    enrolments.append(CourseEnrolment(course=course, user=s.user, role='STUDENT'))
            CourseEnrolment.objects.bulk_create(enrolments, ignore_conflicts=True)

            sec1 = CourseSection.objects.create(course=course, name="Введение", sequence=1)
            mod_page = CourseModule.objects.create(section=sec1, module_type='PAGE', title="Лекция 1", sequence=1)
            PageContent.objects.create(module=mod_page, content="<h3>Хуш омадед!</h3><p>Матни лексия...</p>")

    def _create_orders(self):
        from accounts.models import Order, OrderItem, Student, User
        self.stdout.write('  → Создание тестовых приказов...')
        admin = User.objects.filter(is_superuser=True).first()
        active_students = Student.objects.filter(status='ACTIVE')[:3]

        if active_students.exists():
            order1 = Order.objects.create(
                date=timezone.now().date(), order_type='EXPEL', 
                title='Фармон дар бораи хориҷ кардан', status='DRAFT', created_by=admin
            )
            for st in active_students:
                OrderItem.objects.create(order=order1, student=st, reason='Қарздории академикӣ')

    def _print_credentials(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('─── Тестовые аккаунты (пароль у всех: test) ───'))
        rows =[
            ('Суперпользователь', 'admin', 'test'),
            ('Декан Зеҳни сунъӣ', 'dean_ai', 'test'),
            ('Декан Табиӣ-риёзӣ', 'dean_nm', 'test'),
            ('Преподаватель 1',   'teacher1', 'test'),
            ('Студент 1',         'st1_1_1 (пример)', 'test'),
        ]
        for role, login, pwd in rows:
            self.stdout.write(f'  {role:<22} {login:<20} {pwd}')
        self.stdout.write('\nЧтобы найти логин конкретного студента, посмотрите список в админке или дашборде декана.')