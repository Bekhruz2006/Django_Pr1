import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'department_platform.settings')
django.setup()

from accounts.models import Student
from journal.models import StudentStatistics

print("🔄 Начинаем пересчет статистики...")

students = Student.objects.all()
total = students.count()

for i, student in enumerate(students, 1):
    try:
        stats, created = StudentStatistics.objects.get_or_create(student=student)
        stats.recalculate()
        print(f"✅ [{i}/{total}] {student.user.get_full_name()}: GPA={stats.overall_gpa:.2f}, НБ={stats.total_absent}")
    except Exception as e:
        print(f"❌ [{i}/{total}] {student.user.get_full_name()}: Ошибка - {e}")

print("\n✨ Готово!")