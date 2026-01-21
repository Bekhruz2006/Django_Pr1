import openpyxl
from django.db import transaction
from .models import User, Student, Group
from datetime import datetime

class StudentImportService:
    @staticmethod
    def import_from_excel(file, default_group_id=None):
        wb = openpyxl.load_workbook(file)
        sheet = wb.active
        
        results = {
            'created': 0,
            'errors': []
        }

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            first_name, last_name, middle_name, student_id_manual = row[0], row[1], row[2], row[3]
            
            if not first_name or not last_name:
                continue

            try:
                with transaction.atomic():
                    base_username = f"{datetime.now().year}_{row_idx}_{str(datetime.now().microsecond)[:3]}"
                    
                    user = User.objects.create_user(
                        username=base_username,
                        password='password123',
                        first_name=first_name,
                        last_name=last_name,
                        role='STUDENT'
                    )

                    student, _ = Student.objects.get_or_create(user=user)
                    
                    if default_group_id:
                        student.group_id = default_group_id
                    
                    if student_id_manual:
                        student.student_id = str(student_id_manual)
                    else:
                        student.student_id = f"{datetime.now().year}S{user.id:05d}"
                    
                    student.save()
                    results['created'] += 1

            except Exception as e:
                results['errors'].append(f"Строка {row_idx}: {str(e)}")

        return results