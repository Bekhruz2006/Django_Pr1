from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.urls import reverse
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
import json

try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from .models import Subject, ScheduleSlot, ScheduleException, Semester, Classroom, AcademicWeek, TimeSlot
from .forms import (SubjectForm, ScheduleSlotForm, ScheduleExceptionForm,
                   SemesterForm, ClassroomForm, BulkClassroomForm)
from accounts.models import Group, Student, Teacher

def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'

def is_teacher(user):
    return user.is_authenticated and user.role == 'TEACHER'

def is_student(user):
    return user.is_authenticated and user.role == 'STUDENT'

# ============ КОНСТРУКТОР РАСПИСАНИЯ ============

@login_required
@user_passes_test(is_dean)
def schedule_constructor(request):
    """Вертикальный конструктор расписания с проверкой конфликтов"""
    selected_group_id = request.GET.get('group')

    groups = Group.objects.all().order_by('name')
    time_slots = TimeSlot.objects.all().order_by('start_time')
    subjects = Subject.objects.select_related('teacher__user').all()

    schedule_slots = []
    selected_group = None

    if selected_group_id:
        try:
            selected_group = Group.objects.get(id=selected_group_id)
            active_semester = Semester.get_active()
            if active_semester:
                schedule_slots = ScheduleSlot.objects.filter(
                    group=selected_group,
                    semester=active_semester,
                    is_active=True
                ).select_related('subject', 'teacher__user', 'time_slot')
        except Group.DoesNotExist:
            pass

    context = {
        'groups': groups,
        'selected_group': selected_group,
        'time_slots': time_slots,
        'subjects': subjects,
        'schedule_slots': schedule_slots,
    }

    return render(request, 'schedule/constructor_vertical.html', context)

# ============ AJAX ENDPOINTS ============

@login_required
@require_POST
def create_schedule_slot(request):
    """Новая логика: Создание занятия с проверкой конфликтов"""
    try:
        data = json.loads(request.body)

        group_id = data.get('group')
        subject_id = data.get('subject')
        day_of_week = data.get('day_of_week')
        time_slot_id = data.get('time_slot')

        if not all([group_id, subject_id, day_of_week is not None, time_slot_id]):
            return JsonResponse({
                'success': False,
                'error': 'Не хватает обязательных данных'
            }, status=400)

        active_semester = Semester.get_active()
        if not active_semester:
            return JsonResponse({
                'success': False,
                'error': 'Активный семестр не найден. Создайте и активируйте семестр.'
            }, status=400)

        try:
            group = Group.objects.get(id=group_id)
            subject = Subject.objects.get(id=subject_id)
            time_slot = TimeSlot.objects.get(id=time_slot_id)
        except (Group.DoesNotExist, Subject.DoesNotExist, TimeSlot.DoesNotExist) as e:
            return JsonResponse({
                'success': False,
                'error': f'Объект не найден: {str(e)}'
            }, status=404)

        conflicts = []

        # 1. Конфликт: та же группа в это же время
        if ScheduleSlot.objects.filter(
            group=group,
            day_of_week=day_of_week,
            time_slot=time_slot,
            semester=active_semester,
            is_active=True
        ).exists():
            conflicts.append(f'⚠️ У группы {group.name} уже есть занятие в это время')

        # 2. Конфликт: тот же преподаватель в это же время
        if subject.teacher:
            teacher_conflict = ScheduleSlot.objects.filter(
                teacher=subject.teacher,
                day_of_week=day_of_week,
                time_slot=time_slot,
                semester=active_semester,
                is_active=True
            ).exclude(group=group)

            if teacher_conflict.exists():
                existing = teacher_conflict.first()
                conflicts.append(
                    f'❌ Преподаватель {subject.teacher.user.get_full_name()} '
                    f'занят в это время (группа {existing.group.name})'
                )

        # 3. Проверка: лекции могут быть максимум у 2 групп
        if subject.type == 'LECTURE':
            lecture_count = ScheduleSlot.objects.filter(
                subject=subject,
                day_of_week=day_of_week,
                time_slot=time_slot,
                semester=active_semester,
                is_active=True
            ).count()

            if lecture_count >= 2:
                conflicts.append(
                    f'⚠️ Лекция уже назначена для 2 групп (максимум). '
                    f'Практика и СРСП только для одной группы.'
                )

        if conflicts:
            return JsonResponse({
                'success': False,
                'error': 'Обнаружены конфликты расписания',
                'conflicts': conflicts
            }, status=400)

        schedule_slot = ScheduleSlot.objects.create(
            group=group,
            subject=subject,
            day_of_week=day_of_week,
            time_slot=time_slot,
            semester=active_semester,
            teacher=subject.teacher,
            room=None
        )

        return JsonResponse({
            'success': True,
            'slot': {
                'id': schedule_slot.id,
                'subject_name': schedule_slot.subject.name,
                'teacher_name': schedule_slot.teacher.user.get_full_name() if schedule_slot.teacher else 'Не назначен',
                'room': schedule_slot.room,
                'day_of_week': schedule_slot.day_of_week,
                'time_slot': schedule_slot.time_slot.id
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Неверный формат JSON'
        }, status=400)
    except Exception as e:
        print(f"❌ Ошибка создания слота: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Ошибка сервера: {str(e)}'
        }, status=500)

@login_required
@require_POST
def update_schedule_room(request, slot_id):
    """Обновление номера кабинета"""
    try:
        data = json.loads(request.body)
        room = data.get('room', '').strip()

        schedule_slot = ScheduleSlot.objects.get(id=slot_id)
        schedule_slot.room = room if room else None
        schedule_slot.save()

        return JsonResponse({
            'success': True,
            'room': schedule_slot.room or 'Не указан'
        })

    except ScheduleSlot.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Занятие не найдено'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Ошибка: {str(e)}'
        }, status=500)

@login_required
@require_POST
def delete_schedule_slot(request, slot_id):
    """Удаление занятия"""
    try:
        schedule_slot = ScheduleSlot.objects.get(id=slot_id)

        if not (request.user.is_staff or hasattr(request.user, 'dean_profile')):
            return JsonResponse({
                'success': False,
                'error': 'Нет прав на удаление'
            }, status=403)

        schedule_slot.delete()

        return JsonResponse({
            'success': True,
            'message': 'Занятие удалено'
        })

    except ScheduleSlot.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Занятие не найдено'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Ошибка: {str(e)}'
        }, status=500)

# ============ ОСТАЛЬНЫЕ ФУНКЦИИ ============

@login_required
def schedule_view(request):
    user = request.user
    group = None
    schedule_slots = []
    active_semester = Semester.get_active()

    if not active_semester:
        messages.warning(request, 'Активный семестр не найден.')
        return render(request, 'schedule/no_semester.html')

    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                schedule_slots = ScheduleSlot.objects.filter(
                    group=group,
                    semester=active_semester,
                    is_active=True
                ).select_related('subject', 'teacher__user', 'classroom', 'group').order_by('day_of_week', 'start_time')
        except Student.DoesNotExist:
            pass

    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            schedule_slots = ScheduleSlot.objects.filter(
                teacher=teacher,
                semester=active_semester,
                is_active=True
            ).select_related('subject', 'group', 'classroom').order_by('day_of_week', 'start_time')
        except Teacher.DoesNotExist:
            pass

    elif user.role == 'DEAN':
        group_id = request.GET.get('group')
        groups = Group.objects.all()

        if group_id:
            group = get_object_or_404(Group, id=group_id)
            schedule_slots = ScheduleSlot.objects.filter(
                group=group,
                semester=active_semester,
                is_active=True
            ).select_related('subject', 'teacher__user', 'classroom').order_by('day_of_week', 'start_time')

        return render(request, 'schedule/schedule_dean.html', {
            'groups': groups,
            'selected_group': group,
            'schedule_slots': schedule_slots,
            'active_semester': active_semester,
        })

    schedule_by_day = {}
    for slot in schedule_slots:
        day = slot.get_day_of_week_display()
        if day not in schedule_by_day:
            schedule_by_day[day] = []
        schedule_by_day[day].append(slot)

    return render(request, 'schedule/schedule_view.html', {
        'group': group,
        'schedule_by_day': schedule_by_day,
        'schedule_slots': schedule_slots,
        'active_semester': active_semester,
    })

@login_required
def today_classes(request):
    user = request.user
    today = datetime.now()
    day_of_week = today.weekday()
    current_time = today.time()
    active_semester = Semester.get_active()

    classes = []

    if not active_semester:
        return render(request, 'schedule/today_widget.html', {
            'classes': classes,
            'current_time': current_time,
            'today': today,
        })

    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            if student.group:
                classes = ScheduleSlot.objects.filter(
                    group=student.group,
                    semester=active_semester,
                    day_of_week=day_of_week,
                    is_active=True
                ).select_related('subject', 'teacher__user', 'classroom').order_by('start_time')
        except Student.DoesNotExist:
            pass

    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            classes = ScheduleSlot.objects.filter(
                teacher=teacher,
                semester=active_semester,
                day_of_week=day_of_week,
                is_active=True
            ).select_related('subject', 'group', 'classroom').order_by('start_time')
        except Teacher.DoesNotExist:
            pass

    return render(request, 'schedule/today_widget.html', {
        'classes': classes,
        'current_time': current_time,
        'today': today,
    })

@user_passes_test(is_dean)
def manage_subjects(request):
    subjects = Subject.objects.all().select_related('teacher__user')

    search = request.GET.get('search', '')
    if search:
        subjects = subjects.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    return render(request, 'schedule/manage_subjects.html', {
        'subjects': subjects,
        'search': search,
    })

@user_passes_test(is_dean)
def add_subject(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f'Предмет "{subject.name}" создан. Кредиты распределены: {subject.get_credits_distribution()}')
            return redirect('schedule:manage_subjects')
    else:
        form = SubjectForm()

    return render(request, 'schedule/subject_form.html', {
        'form': form,
        'title': 'Добавить предмет',
    })

@user_passes_test(is_dean)
def edit_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, 'Предмет обновлен')
            return redirect('schedule:manage_subjects')
    else:
        form = SubjectForm(instance=subject)

    return render(request, 'schedule/subject_form.html', {
        'form': form,
        'subject': subject,
        'title': 'Редактировать предмет',
    })

@user_passes_test(is_dean)
def delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    subject.delete()
    messages.success(request, 'Предмет удален')
    return redirect('schedule:manage_subjects')

@user_passes_test(is_dean)
def manage_semesters(request):
    semesters = Semester.objects.all()
    active_semester = Semester.get_active()

    return render(request, 'schedule/manage_semesters.html', {
        'semesters': semesters,
        'active_semester': active_semester,
    })

@user_passes_test(is_dean)
def add_semester(request):
    if request.method == 'POST':
        form = SemesterForm(request.POST)
        if form.is_valid():
            semester = form.save()
            messages.success(request, f'Семестр "{semester.name}" создан')
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm()

    return render(request, 'schedule/semester_form.html', {
        'form': form,
        'title': 'Добавить семестр',
    })

@user_passes_test(is_dean)
def edit_semester(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    if request.method == 'POST':
        form = SemesterForm(request.POST, instance=semester)
        if form.is_valid():
            form.save()
            messages.success(request, 'Семестр обновлен')
            return redirect('schedule:manage_semesters')
    else:
        form = SemesterForm(instance=semester)

    return render(request, 'schedule/semester_form.html', {
        'form': form,
        'semester': semester,
        'title': 'Редактировать семестр',
    })

@user_passes_test(is_dean)
def toggle_semester_active(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    semester.is_active = not semester.is_active
    semester.save()

    status = "активирован" if semester.is_active else "деактивирован"
    messages.success(request, f'Семестр {status}')
    return redirect('schedule:manage_semesters')

@user_passes_test(is_dean)
def manage_classrooms(request):
    classrooms = Classroom.objects.all().order_by('floor', 'number')

    return render(request, 'schedule/manage_classrooms.html', {
        'classrooms': classrooms,
    })

@user_passes_test(is_dean)
def add_classroom(request):
    if request.method == 'POST':
        form = ClassroomForm(request.POST)
        if form.is_valid():
            classroom = form.save()
            messages.success(request, f'Кабинет {classroom.number} добавлен')
            return redirect('schedule:manage_classrooms')
    else:
        form = ClassroomForm()

    return render(request, 'schedule/classroom_form.html', {
        'form': form,
        'title': 'Добавить кабинет',
    })

@user_passes_test(is_dean)
def bulk_add_classrooms(request):
    if request.method == 'POST':
        form = BulkClassroomForm(request.POST)
        if form.is_valid():
            floor = form.cleaned_data['floor']
            start = form.cleaned_data['start_number']
            end = form.cleaned_data['end_number']
            capacity = form.cleaned_data['capacity']

            created = 0
            for num in range(start, end + 1):
                number = f"{num}"
                if not Classroom.objects.filter(number=number).exists():
                    Classroom.objects.create(
                        number=number,
                        floor=floor,
                        capacity=capacity
                    )
                    created += 1

            messages.success(request, f'Создано {created} кабинетов на {floor} этаже')
            return redirect('schedule:manage_classrooms')
    else:
        form = BulkClassroomForm()

    return render(request, 'schedule/bulk_classroom_form.html', {
        'form': form,
    })

@user_passes_test(is_dean)
def delete_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)
    classroom.delete()
    messages.success(request, f'Кабинет {classroom.number} удален')
    return redirect('schedule:manage_classrooms')

@user_passes_test(is_dean)
def manage_academic_week(request):
    from .forms import AcademicWeekForm

    active_semester = Semester.get_active()
    current_week = AcademicWeek.get_current()

    if request.method == 'POST':
        form = AcademicWeekForm(request.POST, instance=current_week)
        if form.is_valid():
            week = form.save(commit=False)

            if active_semester:
                week.semester = active_semester

                AcademicWeek.objects.filter(is_current=True).update(is_current=False)
                week.is_current = True

                semester_start = form.cleaned_data['semester_start_date']
                week_num = form.cleaned_data['current_week']

                week.start_date = semester_start + timedelta(weeks=week_num - 1)
                week.end_date = week.start_date + timedelta(days=6)
                week.week_number = week_num

                week.save()

                messages.success(request, f'Учебная неделя {week_num} установлена')
            else:
                messages.error(request, 'Сначала создайте и активируйте семестр')

            return redirect('schedule:manage_academic_week')
    else:
        initial = {}
        if current_week:
            initial = {
                'semester_start_date': current_week.semester.start_date if current_week.semester else None,
                'current_week': current_week.week_number
            }
        form = AcademicWeekForm(initial=initial)

    return render(request, 'schedule/manage_academic_week.html', {
        'form': form,
        'current_week': current_week,
        'active_semester': active_semester,
    })

@login_required
def group_list(request):
    user = request.user

    if user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            active_semester = Semester.get_active()
            if active_semester:
                group_ids = ScheduleSlot.objects.filter(
                    teacher=teacher,
                    semester=active_semester,
                    is_active=True
                ).values_list('group_id', flat=True).distinct()
                groups = Group.objects.filter(id__in=group_ids)
            else:
                groups = Group.objects.none()
        except Teacher.DoesNotExist:
            groups = Group.objects.none()

    elif user.role == 'DEAN':
        groups = Group.objects.all()

    else:
        messages.error(request, 'Доступ запрещен')
        return redirect('core:dashboard')

    groups_with_students = []
    for group in groups:
        students = Student.objects.filter(group=group).select_related('user').order_by('user__last_name')
        groups_with_students.append({
            'group': group,
            'students': students
        })

    return render(request, 'schedule/group_list.html', {
        'groups_with_students': groups_with_students,
    })

@login_required
def export_schedule(request):
    if not DOCX_AVAILABLE:
        messages.error(request, 'Библиотека python-docx не установлена. Установите: pip install python-docx')
        return redirect('schedule:view')

    user = request.user
    group = None
    schedule_slots = []
    active_semester = Semester.get_active()

    if not active_semester:
        messages.error(request, 'Активный семестр не найден')
        return redirect('schedule:view')

    if user.role == 'STUDENT':
        try:
            student = user.student_profile
            group = student.group
            if group:
                schedule_slots = ScheduleSlot.objects.filter(
                    group=group,
                    semester=active_semester,
                    is_active=True
                ).select_related('subject', 'teacher__user', 'classroom').order_by('day_of_week', 'start_time')
        except Student.DoesNotExist:
            messages.error(request, 'Профиль студента не найден')
            return redirect('schedule:view')

    elif user.role == 'TEACHER':
        try:
            teacher = user.teacher_profile
            schedule_slots = ScheduleSlot.objects.filter(
                teacher=teacher,
                semester=active_semester,
                is_active=True
            ).select_related('subject', 'group', 'classroom').order_by('day_of_week', 'start_time')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль преподавателя не найден')
            return redirect('schedule:view')

    elif user.role == 'DEAN':
        group_id = request.GET.get('group')
        if group_id:
            group = get_object_or_404(Group, id=group_id)
            schedule_slots = ScheduleSlot.objects.filter(
                group=group,
                semester=active_semester,
                is_active=True
            ).select_related('subject', 'teacher__user', 'classroom').order_by('day_of_week', 'start_time')

    if not schedule_slots:
        messages.error(request, 'Нет данных для экспорта')
        return redirect('schedule:view')

    doc = Document()

    if group:
        heading = doc.add_heading(f'РАСПИСАНИЕ ЗАНЯТИЙ', 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        info = doc.add_paragraph()
        info.add_run(f'Группа: {group.name}\n').bold = True
        info.add_run(f'Курс: {group.course}\n')
        info.add_run(f'Семестр: {active_semester.name}\n')
        info.add_run(f'Смена: {active_semester.get_shift_display()}\n')
        info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        heading = doc.add_heading(f'Расписание преподавателя {user.get_full_name()}', 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

    time_slots = {}
    for slot in schedule_slots:
        time_key = f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
        if time_key not in time_slots:
            time_slots[time_key] = {i: None for i in range(6)}
        time_slots[time_key][slot.day_of_week] = slot

    if time_slots:
        table = doc.add_table(rows=1, cols=7)
        table.style = 'Light Grid Accent 1'

        header_cells = table.rows[0].cells
        header_cells[0].text = 'Время'
        for i, day in enumerate(days):
            header_cells[i + 1].text = day

        for time_key in sorted(time_slots.keys()):
            row_cells = table.add_row().cells
            row_cells[0].text = time_key

            for day_num in range(6):
                slot = time_slots[time_key][day_num]
                if slot:
                    if user.role == 'TEACHER':
                        cell_text = f"{slot.subject.name}\n{slot.get_lesson_type_display()}\n{slot.group.name}"
                        if slot.classroom:
                            cell_text += f"\nКаб. {slot.classroom.number}"
                    else:
                        teacher_name = slot.teacher.user.get_full_name() if slot.teacher else 'Не назначен'
                        cell_text = f"{slot.subject.name}\n{slot.get_lesson_type_display()}\n{teacher_name}"
                        if slot.classroom:
                            cell_text += f"\nКаб. {slot.classroom.number}"
                    row_cells[day_num + 1].text = cell_text

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    filename = f'schedule_{group.name if group else user.username}_{datetime.now().strftime("%Y%m%d")}.docx'
    response['Content-Disposition'] = f'attachment; filename={filename}'

    doc.save(response)
    return response
