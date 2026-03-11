from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date, time, timedelta
import random

class Command(BaseCommand):
    help = 'Заполняет БД тестовыми данными (РУП, Расписание, LMS, Журналы, Матрицы)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Запуск масштабной генерации данных (V2) ==='))
        try:
            with transaction.atomic():
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

    def _create_structure(self):
        from accounts.models import Institute, Faculty, Department, Specialty, Specialization
        self.stdout.write('  → Создание структуры ВУЗа...')

        self.institute, _ = Institute.objects.get_or_create(
            abbreviation='ТГТУ',
            defaults={'name': 'Таджикский государственный технический университет', 'address': 'г. Душанбе, пр. Раджабовых, 10'}
        )

        self.faculty_it, _ = Faculty.objects.get_or_create(code='ФИТ-01', defaults={'institute': self.institute, 'name': 'Факультет информационных технологий'})
        
        self.dept_cs, _ = Department.objects.get_or_create(name='Кафедра компьютерных наук', defaults={'faculty': self.faculty_it, 'total_wage_rate': 8.0, 'total_hours_budget': 4000})
        self.dept_se, _ = Department.objects.get_or_create(name='Кафедра программной инженерии', defaults={'faculty': self.faculty_it, 'total_wage_rate': 6.0, 'total_hours_budget': 3200})

        self.spec_cs, _ = Specialty.objects.get_or_create(code='400.101.08', defaults={'department': self.dept_cs, 'name': 'Прикладная информатика', 'qualification': 'Бакалавр'})
        self.spec_se, _ = Specialty.objects.get_or_create(code='400.102.09', defaults={'department': self.dept_se, 'name': 'Программная инженерия', 'qualification': 'Бакалавр'})

    def _create_infrastructure(self):
        from schedule.models import Building, Classroom, TimeSlot
        self.stdout.write('  → Создание инфраструктуры (Корпуса, Аудитории, Звонки)...')

        self.building, _ = Building.objects.get_or_create(name='Главный корпус', defaults={'institute': self.institute, 'address': 'ул. Главная 1'})
        
        # Аудитории
        rooms =[('101', 'LECTURE', 100), ('102', 'PRACTICE', 30), ('201', 'COMPUTER', 25), ('202', 'COMPUTER', 25)]
        self.classrooms =[]
        for num, r_type, cap in rooms:
            room, _ = Classroom.objects.get_or_create(building=self.building, number=num, defaults={'floor': int(num[0]), 'capacity': cap, 'room_type': r_type})
            self.classrooms.append(room)

        # Сетка звонков (1 смена)
        times =[(time(8,0), time(8,50)), (time(9,0), time(9,50)), (time(10,10), time(11,0)), (time(11,10), time(12,0))]
        self.time_slots =[]
        for i, (st, et) in enumerate(times, 1):
            ts, _ = TimeSlot.objects.get_or_create(institute=self.institute, shift='MORNING', number=i, defaults={'start_time': st, 'end_time': et, 'duration': 50})
            self.time_slots.append(ts)

    def _create_users_and_groups(self):
        from accounts.models import User, Dean, HeadOfDepartment, Teacher, Group, Student
        self.stdout.write('  → Создание пользователей и групп...')
        PWD = 'test1234'

        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@test.com', 'admin123', first_name='Администратор', last_name='Системы', role='DIRECTOR')

        def make_user(username, first, last, role):
            u, created = User.objects.get_or_create(username=username, defaults={'first_name': first, 'last_name': last, 'role': role})
            if created: u.set_password(PWD); u.save()
            return u

        self.dean_u = make_user('dean_test', 'Мирзо', 'Турсунов', 'DEAN')
        Dean.objects.get_or_create(user=self.dean_u, defaults={'faculty': self.faculty_it})

        # Преподаватели
        self.teachers = []
        t_data =[('Абдулло', 'Рустамов', 'Доцент'), ('Зарина', 'Садыкова', 'Ст. преподаватель'), ('Фирдавс', 'Гафуров', 'Ассистент')]
        for i, (fn, ln, title) in enumerate(t_data):
            u = make_user(f'teacher0{i+1}', fn, ln, 'TEACHER')
            t, _ = Teacher.objects.get_or_create(user=u, defaults={'department': self.dept_cs, 'title': title})
            self.teachers.append(t)

        # Группы
        self.groups = []
        for name in['400101-24А', '400101-24Б']:
            g, _ = Group.objects.get_or_create(name=name, defaults={'specialty': self.spec_cs, 'course': 1, 'academic_year': '2024-2025', 'curator': self.teachers[0]})
            self.groups.append(g)

        # Студенты
        student_names =[('Алишер', 'Каримов'), ('Нилуфар', 'Рахимова'), ('Фирдавс', 'Турсунов'), ('Зарина', 'Юсупова'), ('Баходур', 'Назаров'), ('Шахло', 'Маликова')]
        for idx, (fn, ln) in enumerate(student_names):
            u = make_user(f'student_{idx+1:02d}', fn, ln, 'STUDENT')
            if hasattr(u, 'student_profile'):
                s = u.student_profile
                s.group = self.groups[idx % 2]
                s.course = 1
                s.status = 'ACTIVE'
                s.financing_type = 'BUDGET' if idx % 2 == 0 else 'CONTRACT'
                s.save()

    def _create_rup_and_subjects(self):
        from schedule.models import AcademicPlan, SubjectTemplate, PlanDiscipline, Subject, Semester
        self.stdout.write('  → Создание РУП и Дисциплин...')

        self.semester, _ = Semester.objects.get_or_create(
            academic_year='2024-2025', number=1, course=1,
            defaults={'name': 'Осенний семестр', 'shift': 'MORNING', 'start_date': timezone.now().date() - timedelta(days=60), 'end_date': timezone.now().date() + timedelta(days=60), 'is_active': True, 'faculty': self.faculty_it}
        )

        self.plan, _ = AcademicPlan.objects.get_or_create(specialty=self.spec_cs, admission_year=2024, defaults={'is_active': True})

        disciplines_data =[
            ('Программирование на Python', 5, 32, 32, 0, self.teachers[0]),
            ('Высшая математика', 4, 32, 16, 16, self.teachers[1]),
            ('Базы данных (SQL)', 4, 16, 32, 16, self.teachers[2]),
        ]

        self.subjects =[]
        for name, cred, lec, prac, srsp, teacher in disciplines_data:
            tmpl, _ = SubjectTemplate.objects.get_or_create(name=name)
            p_disc, _ = PlanDiscipline.objects.get_or_create(
                plan=self.plan, subject_template=tmpl, semester_number=1,
                defaults={'credits': cred, 'lecture_hours': lec, 'practice_hours': prac, 'control_hours': srsp, 'independent_hours': cred*24 - (lec+prac+srsp)}
            )
            
            subj, _ = Subject.objects.get_or_create(
                code=f'CS10{len(self.subjects)+1}',
                defaults={'name': name, 'department': self.dept_cs, 'type': 'LECTURE', 'teacher': teacher, 'plan_discipline': p_disc, 'lecture_hours': lec, 'practice_hours': prac, 'control_hours': srsp}
            )
            subj.groups.set(self.groups)
            self.subjects.append(subj)

    def _create_schedule(self):
        from schedule.models import ScheduleSlot
        self.stdout.write('  → Построение расписания (Шахматки)...')
        
        # Расставляем предметы по дням и времени
        schedule_mapping = [
            (0, 0, self.subjects[0], 'LECTURE', self.classrooms[0]), # Пн, 1 пара, Python Лекция
            (0, 1, self.subjects[0], 'PRACTICE', self.classrooms[2]),# Пн, 2 пара, Python Практика
            (1, 0, self.subjects[1], 'LECTURE', self.classrooms[0]), # Вт, 1 пара, Математика Лекция
            (1, 1, self.subjects[1], 'PRACTICE', self.classrooms[1]),# Вт, 2 пара, Математика Практика
            (2, 0, self.subjects[2], 'LECTURE', self.classrooms[0]), # Ср, 1 пара, БД Лекция
            (2, 1, self.subjects[2], 'PRACTICE', self.classrooms[3]),# Ср, 2 пара, БД Практика
        ]

        for group in self.groups:
            for day, ts_idx, subj, l_type, room in schedule_mapping:
                ts = self.time_slots[ts_idx]
                ScheduleSlot.objects.get_or_create(
                    group=group, semester=self.semester, day_of_week=day, time_slot=ts,
                    defaults={'subject': subj, 'teacher': subj.teacher, 'lesson_type': l_type, 'classroom': room, 'room': room.number, 'start_time': ts.start_time, 'end_time': ts.end_time}
                )

    def _create_journal_and_matrix(self):
        from journal.models import JournalEntry, StudentStatistics, MatrixStructure, MatrixColumn, StudentMatrixScore
        from accounts.models import Student
        self.stdout.write('  → Генерация Журнала и Матрицы (Рейтингов)...')

        today = timezone.now().date()
        start_date = today - timedelta(days=45)

        # 1. Журнал посещаемости
        entries =[]
        for group in self.groups:
            students = list(group.students.all())
            for idx, student in enumerate(students):
                student_type = idx % 4 # 0-Отличник, 1-Хорошист, 2-Болеет, 3-Прогульщик
                for subj in self.subjects:
                    for day_offset in range(10):
                        lesson_date = start_date + timedelta(days=day_offset * 4)
                        if lesson_date > today: continue
                        
                        attendance = 'PRESENT'
                        grade = None
                        rand_val = random.random()

                        if student_type == 0:
                            if rand_val < 0.02: attendance = 'ABSENT_VALID'
                            else: grade = random.randint(10, 12)
                        elif student_type == 1:
                            if rand_val < 0.05: attendance = 'ABSENT_VALID'
                            elif rand_val < 0.10: attendance = 'ABSENT_ILLNESS'
                            else: grade = random.randint(7, 9)
                        elif student_type == 2:
                            if rand_val < 0.30: attendance = 'ABSENT_ILLNESS'
                            else: grade = random.randint(5, 8)
                        else:
                            if rand_val < 0.40: attendance = 'ABSENT_INVALID'
                            else: grade = random.randint(1, 4)

                        if attendance != 'PRESENT': grade = None
                        if attendance == 'PRESENT' and random.random() < 0.3: grade = None

                        entries.append(JournalEntry(student=student, subject=subj, lesson_date=lesson_date, lesson_time=time(8,0), lesson_type=subj.type, grade=grade, attendance_status=attendance, created_by=subj.teacher))
        JournalEntry.objects.bulk_create(entries, ignore_conflicts=True)

        for group in self.groups:
            StudentStatistics.recalculate_group(group)

        # 2. Матрица (Сводная ведомость)
        matrix, _ = MatrixStructure.objects.get_or_create(faculty=self.faculty_it, defaults={'name': 'Стандартная матрица ФИТ'})
        cols =[
            ('Неделя 1', 'WEEK', 12.5, 1), ('Неделя 2', 'WEEK', 12.5, 2),
            ('Рейтинг 1 (Р1)', 'RATING', 100.0, 3), ('Рейтинг 2 (Р2)', 'RATING', 100.0, 4),
            ('Экзамен', 'EXAM', 100.0, 5)
        ]
        matrix_cols =[]
        for name, ctype, max_s, order in cols:
            c, _ = MatrixColumn.objects.get_or_create(structure=matrix, name=name, defaults={'col_type': ctype, 'max_score': max_s, 'order': order})
            matrix_cols.append(c)

        matrix_scores =[]
        for group in self.groups:
            for idx, student in enumerate(group.students.all()):
                student_type = idx % 4
                for subj in self.subjects:
                    for col in matrix_cols:
                        score = 0
                        if student_type == 0: score = col.max_score * random.uniform(0.9, 1.0)
                        elif student_type == 1: score = col.max_score * random.uniform(0.7, 0.89)
                        elif student_type == 2: score = col.max_score * random.uniform(0.5, 0.7)
                        else: score = col.max_score * random.uniform(0.1, 0.4)
                        
                        matrix_scores.append(StudentMatrixScore(student=student, subject=subj, column=col, score=round(score, 1)))
        StudentMatrixScore.objects.bulk_create(matrix_scores, ignore_conflicts=True)

    def _create_lms_courses(self):
        from lms.models import CourseCategory, Course, CourseEnrolment, CourseSection, CourseModule, PageContent, Assignment
        self.stdout.write('  → Создание LMS (Курсы, Модули, Задания)...')

        cat, _ = CourseCategory.objects.get_or_create(name='Кафедра компьютерных наук', faculty=self.faculty_it)

        for subj in self.subjects:
            course, _ = Course.objects.get_or_create(
                id_number=subj.code,
                defaults={'category': cat, 'full_name': subj.name, 'short_name': subj.name[:20], 'summary': f'Официальный курс по дисциплине {subj.name}', 'is_visible': True}
            )
            
            CourseEnrolment.objects.get_or_create(course=course, user=subj.teacher.user, defaults={'role': 'TEACHER'})
            for g in subj.groups.all():
                for s in g.students.all():
                    CourseEnrolment.objects.get_or_create(course=course, user=s.user, defaults={'role': 'STUDENT'})

            if course.sections.count() == 0:
                sec1 = CourseSection.objects.create(course=course, name="Неделя 1: Введение", sequence=1)
                sec2 = CourseSection.objects.create(course=course, name="Неделя 2: Базовые концепции", sequence=2)

                mod_page = CourseModule.objects.create(section=sec1, module_type='PAGE', title="Лекция 1 (Текст)", sequence=1)
                PageContent.objects.create(module=mod_page, content="<h3>Добро пожаловать на курс!</h3><p>Здесь будет текст лекции...</p>")

                mod_ass = CourseModule.objects.create(section=sec1, module_type='ASSIGNMENT', title="Практическая работа №1", sequence=2)
                Assignment.objects.create(module=mod_ass, description="Выполните задание и прикрепите файл с решением.", max_score=100)

    def _create_orders(self):
        from accounts.models import Order, OrderItem, Student, User
        self.stdout.write('  → Создание тестовых приказов...')
        admin = User.objects.filter(is_superuser=True).first()
        active_students = Student.objects.filter(status='ACTIVE')[:2]

        if active_students.exists():
            order1, _ = Order.objects.get_or_create(number='DRAFT-TEST-001', defaults={'date': timezone.now().date(), 'order_type': 'EXPEL', 'title': 'Тестовый приказ об отчислении', 'status': 'DRAFT', 'created_by': admin})
            for st in active_students:
                OrderItem.objects.get_or_create(order=order1, student=st, defaults={'reason': 'Академическая задолженность'})

    def _print_credentials(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('─── Тестовые аккаунты (пароль: test1234) ───'))
        rows =[
            ('Суперпользователь', 'admin',          'admin123'),
            ('Декан ФИТ',         'dean_test',       'test1234'),
            ('Преподаватель',     'teacher01',       'test1234'),
            ('Студент (Отличник)','student_01',      'test1234'),
            ('Студент (Риск)',    'student_04',      'test1234'),
        ]
        for role, login, pwd in rows:
            self.stdout.write(f'  {role:<22} {login:<20} {pwd}')
        self.stdout.write('')