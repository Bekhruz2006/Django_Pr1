# schedule/ai_timetabling.py
import math
import uuid
import random
import copy
from collections import defaultdict
from django.db import transaction
from .models import ScheduleSlot, Subject, Classroom, TimeSlot, TeacherUnavailableSlot

class AutoScheduleEngine:
    def __init__(self, semester, target_groups=None, target_teachers=None, target_rooms=None, 
                 avoid_gaps=True, overflow_mode=1, strict_room_types=False, iterations=50):
        self.semester = semester
        self.target_groups = target_groups
        self.target_teachers = target_teachers
        self.target_rooms = target_rooms
        
        self.avoid_gaps = avoid_gaps
        self.overflow_mode = overflow_mode 
        self.strict_room_types = strict_room_types 
        self.iterations = iterations
        
        self.time_slots = list(TimeSlot.objects.filter(shift=semester.shift).order_by('start_time'))
        self.days = [0, 1, 2, 3, 4, 5] # Пн-Сб
        self.week_types = ['EVERY', 'RED', 'BLUE']

        self.base_teacher_busy = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(bool))))
        self.base_group_busy = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(bool))))
        self.base_room_busy = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(bool))))
        
        # НОВОЕ: Хранилище недоступного времени преподавателей
        self.teacher_unavailable = defaultdict(lambda: defaultdict(lambda: defaultdict(bool)))
        
        self._load_existing_schedule()
        self._load_teacher_unavailability()

    def _load_teacher_unavailability(self):
        """Загружаем дни и часы, когда преподаватели не могут вести занятия"""
        unavailables_qs = TeacherUnavailableSlot.objects.all()
        if self.target_teachers:
            unavailables_qs = unavailables_qs.filter(teacher_id__in=self.target_teachers)
            
        for u in unavailables_qs:
            self.teacher_unavailable[u.teacher_id][u.day_of_week][u.time_slot_id] = True

    def _load_existing_schedule(self):
        existing_slots = ScheduleSlot.objects.filter(semester=self.semester, is_active=True)
        for slot in existing_slots:
            t_id = slot.teacher_id
            g_ids = [slot.group_id]
            if slot.stream_id:
                g_ids = list(ScheduleSlot.objects.filter(stream_id=slot.stream_id).values_list('group_id', flat=True))
            
            w_types = ['RED', 'BLUE'] if slot.week_type == 'EVERY' else [slot.week_type]
            for wt in w_types:
                if t_id: self.base_teacher_busy[t_id][slot.day_of_week][slot.time_slot_id][wt] = True
                if slot.classroom_id: self.base_room_busy[slot.classroom_id][slot.day_of_week][slot.time_slot_id][wt] = True
                for g_id in g_ids:
                    self.base_group_busy[g_id][slot.day_of_week][slot.time_slot_id][wt] = True

    def _is_free(self, state, t_id, g_ids, r_id, day, ts_id, week_type):
        # НОВОЕ: Проверка, не поставил ли декан выходной на этот час
        if t_id and self.teacher_unavailable[t_id][day][ts_id]: 
            return False

        t_busy, g_busy, r_busy = state
        w_types = ['RED', 'BLUE'] if week_type == 'EVERY' else [week_type]
        for wt in w_types:
            if t_id and t_busy[t_id][day][ts_id][wt]: return False
            if r_id and r_busy[r_id][day][ts_id][wt]: return False
            for g_id in g_ids:
                if g_busy[g_id][day][ts_id][wt]: return False
        return True

    def _mark_busy(self, state, t_id, g_ids, r_id, day, ts_id, week_type):
        t_busy, g_busy, r_busy = state
        w_types = ['RED', 'BLUE'] if week_type == 'EVERY' else[week_type]
        for wt in w_types:
            if t_id: t_busy[t_id][day][ts_id][wt] = True
            if r_id: r_busy[r_id][day][ts_id][wt] = True
            for g_id in g_ids:
                g_busy[g_id][day][ts_id][wt] = True

    def _evaluate_slot_quality(self, state, t_id, g_ids, day, ts_index):
        if not self.avoid_gaps:
            return 0
            
        t_busy, g_busy, _ = state
        score = 0
        ts_id = self.time_slots[ts_index].id
        
        prev_ts_id = self.time_slots[ts_index-1].id if ts_index > 0 else None
        next_ts_id = self.time_slots[ts_index+1].id if ts_index < len(self.time_slots)-1 else None

        for g_id in g_ids:
            has_prev = prev_ts_id and any(g_busy[g_id][day][prev_ts_id].values())
            has_next = next_ts_id and any(g_busy[g_id][day][next_ts_id].values())
            
            if has_prev or has_next:
                score += 15 
            else:
                day_is_empty = True
                for slot in self.time_slots:
                    if any(g_busy[g_id][day][slot.id].values()):
                        day_is_empty = False
                        break
                if day_is_empty:
                    score += 5 
                else:
                    score -= 30 
        return score

    def generate(self):
        rooms_qs = Classroom.objects.filter(is_active=True)
        if self.target_rooms: rooms_qs = rooms_qs.filter(id__in=self.target_rooms)
        available_rooms = list(rooms_qs)

        subjects_qs = Subject.objects.filter(groups__in=self.target_groups).distinct()
        if self.target_teachers: subjects_qs = subjects_qs.filter(teacher_id__in=self.target_teachers)
            
        base_tasks =[]
        for subject in subjects_qs:
            needed_slots = subject.get_weekly_slots_needed()
            groups = list(subject.groups.filter(id__in=[g.id for g in self.target_groups]))
            if not groups: continue
            
            if subject.is_stream_subject and subject.groups.count() > 1:
                total_students = sum([g.students.count() for g in groups])
                for l_type, count in needed_slots.items():
                    for _ in range(count):
                        base_tasks.append({
                            'subject': subject, 'groups': groups, 'type': l_type,
                            'teacher': subject.teacher, 'is_stream': True,
                            'total_students': total_students, 'pref_room': subject.preferred_room_type
                        })
            else:
                for group in groups:
                    total_students = group.students.count()
                    for l_type, count in needed_slots.items():
                        existing = ScheduleSlot.objects.filter(subject=subject, group=group, lesson_type=l_type, semester=self.semester).count()
                        for _ in range(max(0, count - existing)):
                            base_tasks.append({
                                'subject': subject, 'groups': [group], 'type': l_type,
                                'teacher': subject.teacher, 'is_stream': False,
                                'total_students': total_students, 'pref_room': subject.preferred_room_type
                            })

        best_schedule =[]
        best_unassigned =[]
        best_score = -float('inf')

        for iteration in range(self.iterations):
            current_state = (
                copy.deepcopy(self.base_teacher_busy),
                copy.deepcopy(self.base_group_busy),
                copy.deepcopy(self.base_room_busy)
            )
            
            tasks = copy.copy(base_tasks)
            tasks.sort(key=lambda x: (not x['is_stream'], -x['total_students'], random.random()))

            current_schedule = []
            current_unassigned =[]
            iteration_score = 0

            for task in tasks:
                assigned = False
                t_id = task['teacher'].id if task['teacher'] else None
                g_ids = [g.id for g in task['groups']]
                
                best_slot_choice = None
                best_slot_score = -float('inf')

                for week_type in ['EVERY']:
                    for day in self.days:
                        for ts_index, ts in enumerate(self.time_slots):
                            for room in available_rooms:
                                cap_ratio = task['total_students'] / max(1, room.capacity)
                                if self.overflow_mode == 0 and cap_ratio > 1.0: continue
                                if self.overflow_mode == 1 and cap_ratio > 1.25: continue
                                if self.overflow_mode == 2 and cap_ratio > 1.50: continue
                                
                                type_penalty = 0
                                if self.strict_room_types:
                                    if task['type'] == 'LECTURE' and room.room_type not in ['LECTURE', 'SPORT']: continue
                                    if task['type'] == 'LAB' and room.room_type != 'LAB': continue
                                    if task['pref_room'] and room.room_type != task['pref_room']: continue
                                else:
                                    if task['type'] == 'LECTURE' and room.room_type not in['LECTURE', 'SPORT']:
                                        type_penalty -= 50
                                    if task['type'] == 'LAB' and room.room_type != 'LAB':
                                        type_penalty -= 50
                                    if task['pref_room'] and room.room_type != task['pref_room']:
                                        type_penalty -= 30

                                cap_penalty = 0
                                if cap_ratio > 1.0:
                                    cap_penalty -= (cap_ratio - 1.0) * 100
                                elif cap_ratio < 0.3:
                                    cap_penalty -= 20 

                                if self._is_free(current_state, t_id, g_ids, room.id, day, ts.id, week_type):
                                    time_score = self._evaluate_slot_quality(current_state, t_id, g_ids, day, ts_index)
                                    total_score = time_score + type_penalty + cap_penalty - (ts_index * 2)

                                    if total_score > best_slot_score:
                                        best_slot_score = total_score
                                        best_slot_choice = (room, day, ts, week_type)

                if best_slot_choice:
                    room, day, ts, week_type = best_slot_choice
                    self._mark_busy(current_state, t_id, g_ids, room.id, day, ts.id, week_type)
                    iteration_score += best_slot_score
                    
                    stream_id = uuid.uuid4() if task['is_stream'] else None
                    for group in task['groups']:
                        current_schedule.append(ScheduleSlot(
                            group=group, subject=task['subject'], teacher=task['teacher'],
                            semester=self.semester, day_of_week=day, time_slot=ts,
                            start_time=ts.start_time, end_time=ts.end_time,
                            classroom=room, room=room.number, lesson_type=task['type'],
                            week_type=week_type, stream_id=stream_id, is_active=True
                        ))
                    assigned = True
                
                if not assigned:
                    current_unassigned.append(task)
                    iteration_score -= 2000 

            if iteration_score > best_score:
                best_score = iteration_score
                best_schedule = current_schedule
                best_unassigned = current_unassigned

        with transaction.atomic():
            ScheduleSlot.objects.bulk_create(best_schedule)

        return {
            'success': True,
            'created': len(best_schedule),
            'unassigned_count': len(best_unassigned),
            'unassigned_details': [f"{t['subject'].name} ({t['type']}) - {', '.join([g.name for g in t['groups']])}" for t in best_unassigned]
        }