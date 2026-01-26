from django.db import transaction
from django.db.models import Q
from accounts.models import Group, Student, Department, Specialty
from schedule.models import Subject, ScheduleSlot, Semester, TimeSlot, Classroom
import datetime

def clean_search_term(term):
    if not term: return ""
    term = str(term).lower().strip()
    if len(term) > 5:
        if term.endswith('ии') or term.endswith('ия') or term.endswith('ой'):
            return term[:-2]
    return term

def find_groups_smart(search_type, query, user_faculty=None):
    groups = Group.objects.none()
    context_obj = None

    raw_query = str(query).strip()
    clean_query = clean_search_term(raw_query)

    if search_type == 'course' or (raw_query.isdigit() and len(raw_query) == 1):
        try:
            course = int(raw_query)
            groups = Group.objects.filter(course=course)
            if user_faculty:
                groups = groups.filter(specialty__department__faculty=user_faculty)
            return groups, f"{course} курс"
        except:
            pass

    if search_type == 'department' or len(clean_query) > 3:
        dept = Department.objects.filter(name__icontains=clean_query).first()
        if not dept:
            spec = Specialty.objects.filter(name__icontains=clean_query).first()
            if spec:
                dept = spec.department

        if dept:
            groups = Group.objects.filter(specialty__department=dept)
            return groups, dept

    groups = Group.objects.filter(name__icontains=raw_query)
    if groups.exists():
        return groups, "по названию группы"

    return Group.objects.none(), None

def execute_action(user, data):
    action = data.get('action')
    params = data.get('params', {})

    if action in ['chat', 'question']:
        return data.get('text', params.get('text', '...'))

    if user.role in ['DEAN', 'VICE_DEAN', 'SUPERUSER']:

        if action == 'add_subject':
            try:
                name = params.get('name')
                credits = int(params.get('credits', 4))
                search_type = params.get('search_type', 'mixed')
                search_query = params.get('search_query')
                is_stream = params.get('is_stream', False)

                if not name: return "❌ Не указано название предмета."
                if not search_query: return "❌ Не указано, для кого (группа/кафедра/курс)."

                user_faculty = None
                if hasattr(user, 'dean_profile') and user.dean_profile.faculty:
                    user_faculty = user.dean_profile.faculty

                target_groups, context_obj = find_groups_smart(search_type, search_query, user_faculty)

                if not target_groups.exists():
                    return f"❌ Не удалось найти группы по запросу: '{search_query}'. Проверьте название кафедры или группы."

                target_department = None

                if isinstance(context_obj, Department):
                    target_department = context_obj
                elif target_groups.first() and target_groups.first().specialty:
                    target_department = target_groups.first().specialty.department
                if not target_department and user_faculty:
                    target_department = user_faculty.departments.first()

                if not target_department:
                    return "❌ Группы найдены, но неясно, к какой кафедре привязать предмет."

                total_hours = credits * 24
                lecture = int(total_hours * 0.4)
                practice = int(total_hours * 0.4)
                srsp = total_hours - lecture - practice

                subject, created = Subject.objects.get_or_create(
                    name=name,
                    department=target_department,
                    defaults={
                        'code': f"AI-{datetime.datetime.now().strftime('%M%S')}",
                        'credits': credits,
                        'lecture_hours': lecture,
                        'practice_hours': practice,
                        'control_hours': srsp,
                        'is_stream_subject': is_stream
                    }
                )

                subject.groups.add(*target_groups)

                action_str = "создан" if created else "обновлен"
                group_list_str = ", ".join([g.name for g in target_groups[:3]])
                if target_groups.count() > 3: group_list_str += f" и еще {target_groups.count()-3}"

                return (f"✅ Предмет '<b>{name}</b>' {action_str}.\n"
                        f"🏫 Кафедра: {target_department.name}\n"
                        f"🎓 Кредитов: {credits}\n"
                        f"👥 Назначен группам ({target_groups.count()}): {group_list_str}")

            except Exception as e:
                return f"❌ Ошибка выполнения: {str(e)}"

        elif action == 'add_schedule':
            try:
                g_query = params.get('group_query')
                s_query = params.get('subject_query')
                day = int(params.get('day', 0))
                time_str = params.get('time')
                room = params.get('room')
                is_military = params.get('is_military', False)

                groups, _ = find_groups_smart('group', g_query)
                group = groups.first()
                if not group: return f"❌ Группа '{g_query}' не найдена."

                semester = Semester.objects.filter(is_active=True).first()
                if not semester: return "❌ Нет активного семестра."

                if is_military:
                    ScheduleSlot.objects.filter(group=group, day_of_week=day, semester=semester).delete()

                    mil_subj, _ = Subject.objects.get_or_create(
                        name="Военная кафедра",
                        defaults={'code':'MIL', 'department': group.specialty.department}
                    )

                    slots_created = 0
                    for h in [8, 9, 10]:
                        ts = TimeSlot.objects.filter(start_time__hour=h).first()
                        if ts:
                            ScheduleSlot.objects.create(
                                group=group, subject=mil_subj, semester=semester,
                                day_of_week=day, time_slot=ts, is_military=True,
                                start_time=ts.start_time, end_time=ts.end_time
                            )
                            slots_created += 1
                    return f"✅ Военная кафедра назначена группе {group.name} на {day}-й день."

                subject = Subject.objects.filter(name__icontains=s_query).first()
                if not subject: return f"❌ Предмет '{s_query}' не найден."

                h, m = map(int, time_str.split(':'))
                time_slot = TimeSlot.objects.filter(start_time__hour=h).first() # Упрощенный поиск по часу
                if not time_slot: return f"❌ Слот {time_str} не найден."

                ScheduleSlot.objects.create(
                    group=group, subject=subject, teacher=subject.teacher,
                    semester=semester, day_of_week=day, time_slot=time_slot,
                    room=room,
                    start_time=time_slot.start_time, end_time=time_slot.end_time
                )

                return f"✅ Занятие добавлено: {group.name}, {subject.name}, {time_str}"

            except Exception as e:
                return f"❌ Ошибка расписания: {str(e)}"

        elif action == 'delete_subject':
            try:
                name = params.get('name')
                search_query = params.get('search_query')

                if not name: return "❌ Не указано название предмета для удаления."

                target_department = None

                if search_query:
                    _, context_obj = find_groups_smart('department', search_query)
                    if isinstance(context_obj, Department):
                        target_department = context_obj

                if not target_department and hasattr(user, 'dean_profile') and user.dean_profile.faculty:
                    dept_candidates = user.dean_profile.faculty.departments.all()
                    subjects = Subject.objects.filter(name__icontains=name, department__in=dept_candidates)
                    if subjects.count() == 1:
                        target_department = subjects.first().department
                    elif subjects.count() > 1:
                        return f"❌ Предмет '{name}' найден на нескольких кафедрах. Уточните кафедру."

                subjects_query = Subject.objects.filter(name__icontains=name)
                if target_department:
                    subjects_query = subjects_query.filter(department=target_department)

                count = subjects_query.count()
                if count == 0:
                    msg = f"❌ Предмет '{name}' не найден"
                    if target_department: msg += f" на кафедре {target_department.name}"
                    return msg + "."
                if count > 1 and not target_department:
                    return f"❌ Найдено {count} предметов с похожим названием. Уточните кафедру."
                deleted_names = list(subjects_query.values_list('name', flat=True))
                subjects_query.delete()

                return f"🗑️ Удален предмет: {', '.join(deleted_names)} (Кафедра: {target_department.name if target_department else 'не уточнена'})."

            except Exception as e:
                return f"❌ Ошибка удаления: {str(e)}"

    return "Команда не распознана или нет прав."
