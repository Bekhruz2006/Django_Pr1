from datetime import timedelta


def _week_bounds(semester_start, bologna_week_index):
    ws = semester_start + timedelta(weeks=bologna_week_index - 1)
    we = ws + timedelta(days=6)
    return ws, we


def slot_applies_week_type(bologna_week_index, week_type):
    if week_type == 'EVERY':
        return True
    is_red = (bologna_week_index % 2) == 1
    if week_type == 'RED':
        return is_red
    if week_type == 'BLUE':
        return not is_red
    return True


def date_for_slot_in_bologna_week(semester_start, bologna_week_index, day_of_week):
    ws, we = _week_bounds(semester_start, bologna_week_index)
    d = ws
    while d <= we:
        if d.weekday() == day_of_week:
            return d
        d += timedelta(days=1)
    return None


def get_bologna_week(for_date, semester=None):
    from schedule.models import Semester

    if semester is None:
        semester = Semester.get_current(for_date)
    if not semester or not semester.start_date:
        return {'week': None, 'kind': 'unknown', 'semester': semester}
    if for_date < semester.start_date:
        return {'week': 0, 'kind': 'before', 'semester': semester}
    if for_date > semester.end_date:
        return {'week': None, 'kind': 'after', 'semester': semester}
    days = (for_date - semester.start_date).days
    w = days // 7 + 1
    kind = 'regular'
    if w == 8:
        kind = 'p1'
    elif w == 16:
        kind = 'p2'
    elif w >= 17:
        kind = 'exam'
    return {'week': w, 'kind': kind, 'semester': semester}


def format_rating_week_alerts(student, target_weeks, today):
    from schedule.models import ScheduleSlot, Semester

    if not student or not student.group:
        return []
    sem = Semester.get_current(today)
    if not sem or not sem.start_date:
        return []
    alerts = []
    seen = set()
    for tw in target_weeks:
        slots = ScheduleSlot.objects.filter(
            group=student.group,
            semester=sem,
            is_active=True,
        ).select_related('subject', 'classroom')
        for slot in slots:
            if not slot_applies_week_type(tw, slot.week_type):
                continue
            lesson_date = date_for_slot_in_bologna_week(sem.start_date, tw, slot.day_of_week)
            if not lesson_date:
                continue
            key = (slot.subject_id, lesson_date)
            if key in seen:
                continue
            seen.add(key)
            room = slot.classroom.number if slot.classroom else (slot.room or '—')
            days_left = (lesson_date - today).days
            alerts.append({
                'subject': slot.subject.name,
                'date': lesson_date.strftime('%d.%m.%Y'),
                'room': room,
                'days_left': max(0, days_left),
            })
    return alerts
