import re
from typing import Union

from datetime import timedelta
from schedule.models import ScheduleSlot
from django.db.models import Count

def calculate_semester_hours(group, semester):
    if not semester or not semester.start_date or not semester.end_date:
        return {}

    slots = ScheduleSlot.objects.filter(group=group, semester=semester, is_active=True)
    vacation_weeks =[int(w.strip()) for w in semester.vacation_weeks.split(',')] if semester.vacation_weeks else[]
    
    total_weeks = ((semester.end_date - semester.start_date).days // 7) + 1
    active_weeks = total_weeks - len(vacation_weeks)

    hours_report = {}
    for slot in slots:
        subject_name = slot.subject.name
        if subject_name not in hours_report:
            hours_report[subject_name] = {'pairs': 0, 'academic_hours': 0, 'teacher': slot.teacher}

        if slot.week_type == 'EVERY':
            multiplier = active_weeks
            multiplier = active_weeks // 2 

        hours_report[subject_name]['pairs'] += multiplier
        hours_report[subject_name]['academic_hours'] += (multiplier * 2)

    return hours_report

_EMPTY_STRINGS = frozenset({
    '', 'none', 'null', '-', '—', 'н/д', 'нет', 'n/a', 'нб',
})

_NUMBER_RE = re.compile(r'(\d+(?:[.,]\d+)?)')


def safe_int(val) -> int:
    if val is None:
        return 0
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    try:
        s = str(val).strip()
        if s.lower() in _EMPTY_STRINGS:
            return 0
        try:
            return int(float(s.replace(',', '.')))
        except ValueError:
            pass
        m = _NUMBER_RE.search(s)
        if m:
            return int(float(m.group(1).replace(',', '.')))
        return 0
    except (ValueError, TypeError, AttributeError):
        return 0


def safe_float(val, decimals: int = 2) -> float:
    if val is None:
        return 0.0
    if isinstance(val, bool):
        return float(int(val))
    if isinstance(val, (int, float)):
        return round(float(val), decimals)
    try:
        s = str(val).strip()
        if s.lower() in _EMPTY_STRINGS:
            return 0.0
        try:
            return round(float(s.replace(',', '.')), decimals)
        except ValueError:
            pass
        m = _NUMBER_RE.search(s)
        if m:
            return round(float(m.group(1).replace(',', '.')), decimals)
        return 0.0
    except (ValueError, TypeError, AttributeError):
        return 0.0


def safe_str(val, default: str = '') -> str:
    if val is None:
        return default
    s = str(val).strip()
    return default if s.lower() in ('none', 'null') else s