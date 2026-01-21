import openpyxl
from difflib import SequenceMatcher
from django.db import transaction
from .models import Subject, Semester
from accounts.models import Teacher, Group, Department


class ScheduleImporter:
    
    def __init__(self, file, semester, default_group=None):
        self.file = file
        self.semester = semester
        self.default_group = default_group
        self.workbook = openpyxl.load_workbook(file)
        self.worksheet = self.workbook.active
        self.log = []
        self.subjects_created = 0
        self.teachers_created = 0
        self.slots_created = 0
    
    def run(self):
        try:
            with transaction.atomic():
                self._parse_and_import()
        except Exception as e:
            self.log.append(f"Критическая ошибка: {str(e)}")
        
        return {
            'subjects_created': self.subjects_created,
            'teachers_created': self.teachers_created,
            'slots_created': self.slots_created,
            'log': self.log
        }
    
    def _parse_and_import(self):
        rows = list(self.worksheet.iter_rows(values_only=False))
        
        if not rows:
            self.log.append("Файл пуст")
            return
        
        group_headers = []
        for idx, cell in enumerate(rows[0]):
            if cell.value:
                group_name = str(cell.value).strip()
                try:
                    group = Group.objects.get(name=group_name)
                    group_headers.append((idx, group))
                except Group.DoesNotExist:
                    self.log.append(f"Группа не найдена: {group_name}")
        
        if not group_headers and self.default_group:
            group_headers = [(1, self.default_group)]
            self.log.append(f"Используется группа по умолчанию: {self.default_group.name}")
        
        if not group_headers:
            self.log.append("Не найдены группы в файле и не установлена группа по умолчанию")
            return
        
        for row_idx, row in enumerate(rows[1:], start=2):
            day_cell = row[0]
            time_cell = row[1] if len(row) > 1 else None
            
            if not day_cell.value or not time_cell.value:
                continue
            
            day_of_week = str(day_cell.value).strip()
            time_slot = str(time_cell.value).strip()
            
            for col_idx, group in group_headers:
                if col_idx < len(row):
                    cell = row[col_idx]
                    if cell.value:
                        self._process_schedule_entry(
                            str(cell.value).strip(),
                            group,
                            day_of_week,
                            time_slot
                        )
    
    def _process_schedule_entry(self, entry_str, group, day_of_week, time_slot):
        if not entry_str or entry_str == 'None':
            return
        
        parts = entry_str.split('(')
        subject_name = parts[0].strip() if parts else ""
        
        subject_type = 'LECTURE'
        teacher_name = ""
        
        if len(parts) > 1:
            type_part = parts[1].split(')')[0].strip()
            if type_part.upper() in ['LECTURE', 'PRACTICE', 'SRSP']:
                subject_type = type_part.upper()
            
            remainder = parts[1].split(')')[1] if ')' in parts[1] else ""
            teacher_name = remainder.strip()
        
        if not subject_name:
            return
        
        teacher = None
        if teacher_name:
            teacher = self._find_or_create_teacher(teacher_name, group.specialty.department)
        
        subject = self._find_or_create_subject(
            subject_name,
            subject_type,
            group.specialty.department,
            teacher
        )
        
        if subject:
            pass
    
    def _find_or_create_teacher(self, name, department):
        existing = Teacher.objects.filter(
            user__last_name__iexact=name,
            department=department
        ).first()
        
        if existing:
            return existing
        
        teachers = Teacher.objects.filter(department=department)
        best_match = None
        best_ratio = 0.6
        
        for teacher in teachers:
            full_name = f"{teacher.user.last_name} {teacher.user.first_name}"
            ratio = SequenceMatcher(None, full_name.lower(), name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = teacher
        
        if best_match:
            self.log.append(f"Найден преподаватель по совпадению: {name} -> {best_match.user.get_full_name()}")
            return best_match
        
        from accounts.models import User
        try:
            parts = name.split()
            last_name = parts[0] if parts else "Unknown"
            first_name = parts[1] if len(parts) > 1 else "Teacher"
            
            username = f"teacher_{last_name}_{first_name}".lower()[:30]
            count = 1
            original_username = username
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{count}"
                count += 1
            
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=f"{username}@auto.local",
                role='TEACHER'
            )
            
            teacher = Teacher.objects.create(
                user=user,
                department=department,
                code=f"AUTO-{department.id}-{user.id}"
            )
            
            self.teachers_created += 1
            self.log.append(f"Создан преподаватель: {name} (код: {teacher.code})")
            return teacher
        except Exception as e:
            self.log.append(f"Ошибка при создании преподавателя {name}: {str(e)}")
            return None
    
    def _find_or_create_subject(self, name, subject_type, department, teacher=None):
        existing = Subject.objects.filter(
            name__iexact=name,
            department=department
        ).first()
        
        if existing:
            return existing
        
        try:
            code = f"AUTO-{department.id}-{Subject.objects.filter(department=department).count() + 1}"
            
            subject = Subject.objects.create(
                name=name,
                code=code,
                department=department,
                type=subject_type,
                teacher=teacher
            )
            
            self.subjects_created += 1
            self.log.append(f"Создан предмет: {name} (код: {code})")
            return subject
        except Exception as e:
            self.log.append(f"Ошибка при создании предмета {name}: {str(e)}")
            return None
