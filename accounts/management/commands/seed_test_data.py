from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date


class Command(BaseCommand):
    help = 'Заполняет БД тестовыми данными для ручного тестирования'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Заполнение тестовых данных ==='))
        try:
            with transaction.atomic():
                self._create_structure()
                self._create_users()
                self._create_students()
                self._create_orders()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка: {e}'))
            raise
        self.stdout.write(self.style.SUCCESS('✅ Тестовые данные успешно созданы!'))
        self._print_credentials()

    def _create_structure(self):
        from accounts.models import Institute, Faculty, Department, Specialty, Specialization

        self.stdout.write('  → Создание структуры...')

        self.institute, _ = Institute.objects.get_or_create(
            abbreviation='ТГТУ',
            defaults={'name': 'Таджикский государственный технический университет', 'address': 'г. Душанбе, пр. Академиков Раджабовых, 10'}
        )

        self.faculty_it, _ = Faculty.objects.get_or_create(
            code='ФИТ-01',
            defaults={'institute': self.institute, 'name': 'Факультет информационных технологий'}
        )
        self.faculty_eng, _ = Faculty.objects.get_or_create(
            code='ФЭ-02',
            defaults={'institute': self.institute, 'name': 'Энергетический факультет'}
        )

        self.dept_cs, _ = Department.objects.get_or_create(
            name='Кафедра компьютерных наук',
            defaults={'faculty': self.faculty_it, 'total_wage_rate': 8.0, 'total_hours_budget': 4000}
        )
        self.dept_se, _ = Department.objects.get_or_create(
            name='Кафедра программной инженерии',
            defaults={'faculty': self.faculty_it, 'total_wage_rate': 6.0, 'total_hours_budget': 3200}
        )
        self.dept_power, _ = Department.objects.get_or_create(
            name='Кафедра электроэнергетики',
            defaults={'faculty': self.faculty_eng, 'total_wage_rate': 5.0, 'total_hours_budget': 2800}
        )

        self.spec_cs, _ = Specialty.objects.get_or_create(
            code='400.101.08',
            defaults={'department': self.dept_cs, 'name': 'Прикладная информатика', 'qualification': 'Бакалавр'}
        )
        self.spec_se, _ = Specialty.objects.get_or_create(
            code='400.102.09',
            defaults={'department': self.dept_se, 'name': 'Программная инженерия', 'qualification': 'Бакалавр'}
        )
        self.spec_power, _ = Specialty.objects.get_or_create(
            code='500.201.01',
            defaults={'department': self.dept_power, 'name': 'Электроэнергетика и электротехника', 'qualification': 'Бакалавр'}
        )

        Specialization.objects.get_or_create(
            specialty=self.spec_cs, name='Разработка программного обеспечения',
            defaults={'code': '400.101.08.01'}
        )
        Specialization.objects.get_or_create(
            specialty=self.spec_cs, name='Искусственный интеллект',
            defaults={'code': '400.101.08.02'}
        )

        self.stdout.write(self.style.SUCCESS('     ✓ Структура создана'))

    def _create_users(self):
        from accounts.models import (
            User, Dean, ViceDean, Director, ProRector, HeadOfDepartment, Teacher,
            HRProfile, Group
        )

        self.stdout.write('  → Создание пользователей...')
        PWD = 'test1234'

        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@test.com', 'admin123',
                first_name='Администратор', last_name='Системы', role='DIRECTOR')
            self.stdout.write('     ✓ admin / admin123 (суперпользователь)')

        def make_user(username, first, last, role, **kw):
            u, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first, 'last_name': last, 'role': role,
                          'phone': '+992900000000', **kw}
            )
            if created:
                u.set_password(PWD)
                u.save()
            return u

        self.director_u = make_user('director_test', 'Фарид', 'Рахимов', 'DIRECTOR')
        Director.objects.get_or_create(user=self.director_u,
            defaults={'institute': self.institute})

        self.prorector_u = make_user('prorector_test', 'Зафар', 'Хасанов', 'PRO_RECTOR')
        ProRector.objects.get_or_create(user=self.prorector_u,
            defaults={'institute': self.institute, 'title': 'Зам. директора по учебной работе'})

        self.dean_u = make_user('dean_test', 'Мирзо', 'Турсунов', 'DEAN')
        dean_profile, _ = Dean.objects.get_or_create(user=self.dean_u,
            defaults={'faculty': self.faculty_it, 'contact_email': 'fit@tgtu.tj',
                      'office_location': '101', 'reception_hours': 'Пн-Пт 10:00-12:00'})
        if not dean_profile.faculty:
            dean_profile.faculty = self.faculty_it; dean_profile.save()

        self.vicedean_u = make_user('vicedean_test', 'Нилуфар', 'Алиева', 'VICE_DEAN')
        ViceDean.objects.get_or_create(user=self.vicedean_u,
            defaults={'faculty': self.faculty_it, 'title': 'Зам. декана по учебной работе'})

        self.head_u = make_user('head_test', 'Баходур', 'Назаров', 'HEAD_OF_DEPT')
        HeadOfDepartment.objects.get_or_create(user=self.head_u,
            defaults={'department': self.dept_cs, 'degree': 'к.т.н.'})

        self.hr_u = make_user('hr_test', 'Ситора', 'Каримова', 'HR')
        HRProfile.objects.get_or_create(user=self.hr_u,
            defaults={'department_name': 'Отдел кадров'})

        self.teachers = []
        teacher_data = [
            ('Абдулло', 'Рустамов', 'к.т.н.', 'Доцент'),
            ('Сухроб',  'Махмудов', 'д.т.н.', 'Профессор'),
            ('Зарина',  'Садыкова', 'к.ф.-м.н.', 'Доцент'),
            ('Фирдавс', 'Гафуров',  '',          'Ст. преподаватель'),
            ('Мадина',  'Юсупова',  'к.т.н.', 'Доцент'),
            ('Тимур',   'Одинаев',  '',          'Ассистент'),
            ('Лола',    'Насирова', 'к.п.н.', 'Доцент'),
            ('Шамсиддин','Бобоев',  'д.т.н.', 'Профессор'),
            ('Озода',   'Рахимова', 'к.т.н.', 'Ст. преподаватель'),
            ('Дилшод',  'Азизов',   '',          'Ассистент'),
        ]
        for i, (fn, ln, degree, title) in enumerate(teacher_data):
            u = make_user(f'teacher{i+1:02d}', fn, ln, 'TEACHER')
            t, _ = Teacher.objects.get_or_create(user=u,
                defaults={'department': self.dept_cs if i < 5 else self.dept_se,
                          'degree': degree, 'title': title,
                          'contact_email': f'teacher{i+1}@tgtu.tj'})
            self.teachers.append(t)

        self.teacher_test = make_user('teacher_test', 'Тест', 'Преподаватель', 'TEACHER')
        t, _ = Teacher.objects.get_or_create(user=self.teacher_test,
            defaults={'department': self.dept_cs, 'degree': 'к.т.н.', 'title': 'Доцент'})
        self.teachers.insert(0, t)

        self.groups = []
        group_data = [
            ('400101-22А', 1, '2024-2025', self.spec_cs),
            ('400101-23А', 2, '2024-2025', self.spec_cs),
            ('400101-22Б', 1, '2024-2025', self.spec_cs),
            ('400102-22А', 1, '2024-2025', self.spec_se),
            ('400102-23А', 2, '2024-2025', self.spec_se),
            ('500201-22А', 1, '2024-2025', self.spec_power),
            ('500201-23А', 2, '2024-2025', self.spec_power),
            ('400101-21А', 3, '2024-2025', self.spec_cs),
        ]
        for name, course, year, spec in group_data:
            g, _ = Group.objects.get_or_create(name=name,
                defaults={'specialty': spec, 'course': course, 'academic_year': year,
                          'language': 'RU', 'curator': self.teachers[0] if self.teachers else None})
            self.groups.append(g)

        self.stdout.write(self.style.SUCCESS('     ✓ Пользователи и группы созданы'))

    def _create_students(self):
        from accounts.models import User, Student

        self.stdout.write('  → Создание студентов...')
        PWD = 'test1234'

        student_names = [
            ('Алишер', 'Каримов'), ('Нилуфар', 'Рахимова'), ('Фирдавс', 'Турсунов'),
            ('Зарина',  'Юсупова'), ('Баходур', 'Назаров'),  ('Шахло',   'Маликова'),
            ('Дилшод',  'Собиров'), ('Мадина',  'Хасанова'), ('Тохир',   'Ашуров'),
            ('Лола',    'Бобоева'), ('Умед',    'Расулов'),  ('Ситора',  'Давлатова'),
            ('Сухроб',  'Мирзоев'), ('Гулнора', 'Алиева'),   ('Бехзод',  'Холматов'),
            ('Фотима',  'Саидова'), ('Зафар',   'Муминов'),  ('Хилола',  'Рустамова'),
            ('Акбар',   'Назаров'), ('Камола',  'Исмоилова'),
        ]

        self.test_student = None
        statuses = ['ACTIVE'] * 14 + ['ACADEMIC_LEAVE', 'ACADEMIC_LEAVE', 'ACTIVE', 'ACTIVE', 'ACTIVE', 'ACTIVE']
        financings = ['BUDGET'] * 12 + ['CONTRACT'] * 8

        for idx, (fn, ln) in enumerate(student_names):
            username = f'student_{idx+1:03d}'
            u, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': fn, 'last_name': ln, 'role': 'STUDENT'}
            )
            if created:
                u.set_password(PWD); u.save()

            group = self.groups[idx % len(self.groups)]
            status = statuses[idx]
            financing = financings[idx]

            if hasattr(u, 'student_profile'):
                s = u.student_profile
                s.group = group
                s.course = group.course
                s.status = status
                s.financing_type = financing
                s.specialty = group.specialty
                s.birth_date = date(2002 - idx % 3, (idx % 12) + 1, (idx % 28) + 1)
                s.gender = 'M' if idx % 2 == 0 else 'F'
                s.nationality = 'Таджик'
                s.passport_series = 'А'
                s.passport_number = f'12345{idx:03d}'
                s.admission_year = 2022 + (group.course % 2)
                if financing == 'CONTRACT':
                    s.contract_amount = 3000
                    s.paid_amount = 1500 if idx % 3 != 0 else 0
                s.save()
                if idx == 0:
                    self.test_student = s

        u, created = User.objects.get_or_create(
            username='student_test',
            defaults={'first_name': 'Тест', 'last_name': 'Студентов', 'role': 'STUDENT'}
        )
        if created:
            u.set_password(PWD); u.save()
        if hasattr(u, 'student_profile'):
            s = u.student_profile
            s.group = self.groups[0]
            s.course = 1
            s.specialty = self.spec_cs
            s.status = 'ACTIVE'
            s.financing_type = 'BUDGET'
            s.birth_date = date(2004, 5, 15)
            s.gender = 'M'
            s.nationality = 'Таджик'
            s.save()

        for i, (fn, ln, status) in enumerate([
            ('Отчисленный', 'Студент', 'EXPELLED'),
            ('Выпускник', 'Иванов', 'GRADUATED'),
        ]):
            username = f'student_archive_{i}'
            u, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': fn, 'last_name': ln, 'role': 'STUDENT'}
            )
            if created:
                u.set_password(PWD); u.save()
            if hasattr(u, 'student_profile'):
                s = u.student_profile
                s.group = None
                s.status = status
                s.specialty = self.spec_cs
                s.birth_date = date(2000, 1, 1)
                s.save()

        for i in range(3):
            u, created = User.objects.get_or_create(
                username=f'unassigned_{i}',
                defaults={'first_name': f'Нераспр{i}', 'last_name': 'Студент', 'role': 'STUDENT'}
            )
            if created:
                u.set_password(PWD); u.save()
            if hasattr(u, 'student_profile'):
                s = u.student_profile
                s.group = None
                s.status = 'ACTIVE'
                s.specialty = self.spec_cs
                s.birth_date = date(2003, 3, 3)
                s.save()

        self.stdout.write(self.style.SUCCESS('     ✓ Студенты созданы'))

    def _create_orders(self):
        from accounts.models import Order, OrderItem, Student, User

        self.stdout.write('  → Создание тестовых приказов...')

        admin = User.objects.filter(is_superuser=True).first()
        active_students = Student.objects.filter(status='ACTIVE')[:5]

        if active_students.exists():
            order1, _ = Order.objects.get_or_create(
                number='DRAFT-TEST-001',
                defaults={
                    'date': timezone.now().date(),
                    'order_type': 'EXPEL',
                    'title': 'Тестовый приказ об отчислении (ЧЕРНОВИК)',
                    'status': 'DRAFT',
                    'created_by': admin,
                }
            )
            for st in active_students[:2]:
                OrderItem.objects.get_or_create(order=order1, student=st,
                    defaults={'reason': 'Тест — академическая задолженность'})

            if len(self.groups) >= 2:
                order2, _ = Order.objects.get_or_create(
                    number='DRAFT-TEST-002',
                    defaults={
                        'date': timezone.now().date(),
                        'order_type': 'TRANSFER',
                        'title': 'Тестовый приказ о переводе в группу',
                        'status': 'DRAFT',
                        'created_by': admin,
                    }
                )
                for st in active_students[2:4]:
                    OrderItem.objects.get_or_create(order=order2, student=st,
                        defaults={'reason': 'Тест — перевод по заявлению',
                                  'target_group': self.groups[1]})

        self.stdout.write(self.style.SUCCESS('     ✓ Приказы созданы'))

    def _print_credentials(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('─── Тестовые аккаунты (пароль: test1234) ───'))
        rows = [
            ('Суперпользователь', 'admin',          'admin123'),
            ('Директор',          'director_test',   'test1234'),
            ('Проректор',         'prorector_test',  'test1234'),
            ('Декан ФИТ',         'dean_test',       'test1234'),
            ('Зам. декана',       'vicedean_test',   'test1234'),
            ('Зав. кафедрой',     'head_test',       'test1234'),
            ('Преподаватель',     'teacher_test',    'test1234'),
            ('Студент',           'student_test',    'test1234'),
            ('HR',                'hr_test',         'test1234'),
        ]
        for role, login, pwd in rows:
            self.stdout.write(f'  {role:<22} {login:<20} {pwd}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            '⚠  Для тестирования нераспределённых студентов:\n'
            '   Логин: unassigned_0, unassigned_1, unassigned_2 / пароль: test1234'
        ))