# accounts/document_engine.py
import io
from docxtpl import DocxTemplate
from django.utils import timezone
from .models import DocumentTemplate, Student, StudentOrder

class DocumentGenerator:
    @staticmethod
    def generate_document(template_id, object_id):
        template_obj = DocumentTemplate.objects.get(id=template_id)
        doc = DocxTemplate(template_obj.file.path)
        
        context = {}
        filename = "document.docx"

        if template_obj.context_type == 'STUDENT_CERT':
            student = Student.objects.get(id=object_id)
            context = {
                'date_today': timezone.now().strftime('%d.%m.%Y'),
                'full_name': student.user.get_full_name(),
                'first_name': student.user.first_name,
                'last_name': student.user.last_name,
                'student_id': student.student_id,
                'course': student.course,
                'group_name': student.group.name if student.group else 'Не назначена',
                'specialty_code': student.specialty.code if student.specialty else '',
                'specialty_name': student.specialty.name if student.specialty else '',
                'financing': student.get_financing_type_display(),
                'education_type': student.get_education_type_display(),
                'faculty_name': student.specialty.department.faculty.name if student.specialty else '',
                'institute_name': student.specialty.department.faculty.institute.name if student.specialty else '',
            }
            filename = f"Spravka_{student.user.last_name}.docx"

        elif template_obj.context_type == 'STUDENT_ORDER':
            order = StudentOrder.objects.get(id=object_id)
            student = order.student
            context = {
                'order_number': order.number,
                'order_date': order.date.strftime('%d.%m.%Y'),
                'order_reason': order.reason,
                'order_type': order.get_order_type_display(),
                'student_full_name': student.user.get_full_name(),
                'group_name': student.group.name if student.group else '',
                'course': student.course,
                'specialty_name': student.specialty.name if student.specialty else '',
                'initiator_name': order.initiated_by.get_full_name() if order.initiated_by else '',
            }
            filename = f"Prikaz_{order.number}_{student.user.last_name}.docx"

        doc.render(context)
        
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        
        return file_stream, filename