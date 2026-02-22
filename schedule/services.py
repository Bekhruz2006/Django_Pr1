import re
import openpyxl
from django.db import transaction
from django.db.models import Q
from datetime import datetime, time
from .models import ScheduleSlot, Subject, Classroom, TimeSlot, PlanDiscipline, SubjectTemplate, AcademicPlan
from accounts.models import Group, Teacher, User, Department

class ScheduleImporter:
    DAYS_MAP = {
        'душанбе': 0, 'понедельник': 0, 'monday': 0,
        'сешанбе': 1, 'вторник': 1, 'tuesday': 1,
        'чоршанбе': 2, 'среда': 2, 'wednesday': 2,
        'панҷшанбе': 3, 'четверг': 3, 'thursday': 3,
        'ҷумъа': 4, 'пятница': 4, 'friday': 4,
        'шанбе': 5, 'суббота': 5, 'saturday': 5,
    }

    def __init__(self, file=None):
        self.file = file
        self.preview_data = []
        self.default_dept = Department.objects.first()
        self.all_groups = list(Group.objects.all())

    def parse_for_preview(self, default_group=None):
        filename = self.file.name.lower()
        self.default_group = default_group

        try:
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                self._process_pdf()
            else:
                return []
        except Exception as e:
            import traceback
            traceback.print_exc()
            return []
        return self.preview_data


    def _process_excel(self):
        wb = openpyxl.load_workbook(self.file, data_only=True)
        sheet = wb.active
        rows = []
        for row in sheet.iter_rows(values_only=True):
            clean = [str(c).strip() if c is not None else "" for c in row]
            if any(clean): rows.append(clean)
        self._parse_grid_rows(rows, source="Excel")

    def _parse_grid_rows(self, rows, source=""):
        if len(rows) < 2: return

        header_map = {}
        start_row_idx = 0

        for row_idx, row in enumerate(rows[:20]):
            for col_idx, cell_val in enumerate(row):
                if not cell_val: continue
                group = self._match_group(cell_val)
                if group:
                    header_map[col_idx] = group
            if header_map:
                start_row_idx = row_idx + 1
                break

        if not header_map and self.default_group:
            header_map[2] = self.default_group
            start_row_idx = 0

        current_day = 0

        for row in rows[start_row_idx:]:
            row_text = " ".join([str(x).lower() for x in row if x])

            for d_name, d_val in self.DAYS_MAP.items():
                if d_name in row_text[:30]:
                    current_day = d_val
                    break

            is_military_row = 'ҳарбӣ' in row_text or 'военная' in row_text

            current_time_slot = None
            time_str_raw = ""
            for c_val in row[:4]:
                ts = self._extract_time_slot(c_val)
                if ts:
                    current_time_slot = ts
                    time_str_raw = c_val
                    break

            if not current_time_slot and not is_military_row:
                continue

            for col_idx, group in header_map.items():
                if col_idx >= len(row): continue

                raw_val = row[col_idx]
                if not raw_val and not is_military_row: continue
                if raw_val and len(raw_val) < 2 and not is_military_row: continue

                room = ""
                if col_idx + 1 < len(row):
                    pot_room = row[col_idx + 1]
                    if pot_room and len(pot_room) < 10 and any(c.isdigit() for c in pot_room):
                        room = pot_room

                if is_military_row:
                    if not current_time_slot:
                        times = ["08:00-08:50", "09:00-09:50", "10:00-10:50"]
                        for t in times:
                            self.preview_data.append({
                                'group_id': group.id,
                                'group_name': group.name,
                                'day': current_day,
                                'start_time': t.split('-')[0],
                                'end_time': t.split('-')[1],
                                'subject': "Кафедраи ҳарбӣ",
                                'teacher': "",
                                'room': "",
                                'type': "PRACTICE",
                                'is_military': True
                            })
                        continue
                    else:
                        raw_val = "Кафедраи ҳарбӣ"

                parsed_data = self._parse_cell_text(raw_val)

                self.preview_data.append({
                    'group_id': group.id,
                    'group_name': group.name,
                    'day': current_day,
                    'start_time': current_time_slot.start_time.strftime("%H:%M"),
                    'end_time': current_time_slot.end_time.strftime("%H:%M"),
                    'subject': parsed_data['subject'],
                    'teacher': parsed_data['teacher'],
                    'room': room,
                    'type': parsed_data['type'],
                    'is_military': is_military_row
                })

    def save_data_from_preview(self, clean_data, semester):
        stats = {'slots': 0, 'subjects': 0, 'teachers': 0}

        for item in clean_data:
            if not item.get('subject'): continue

            try:
                with transaction.atomic():
                    group = Group.objects.get(id=item['group_id'])

                    institute = None
                    if group.specialty and group.specialty.department.faculty:
                        institute = group.specialty.department.faculty.institute

                    start_str = item['start_time']
                    t_slot = None

                    if institute:
                        t_slot = TimeSlot.objects.filter(
                            institute=institute,
                            start_time__startswith=start_str[:5]
                        ).first()

                    if not t_slot:
                        t_slot = TimeSlot.objects.filter(start_time__startswith=start_str[:5]).first()

                    if not t_slot:
                        continue

                    dept = group.specialty.department if group.specialty else self.default_dept

                    is_mil = item.get('is_military') == 'on' or item.get('subject') == 'Кафедраи ҳарбӣ'

                    subj_name = item['subject'].strip()
                    subject, created = Subject.objects.get_or_create(
                        name__iexact=subj_name,
                        defaults={
                            'name': subj_name,
                            'code': f"IMP{hash(subj_name)}",
                            'department': dept,
                            'type': item['type'],
                            'is_stream_subject': False
                        }
                    )
                    if created: stats['subjects'] += 1
                    subject.groups.add(group)

                    teacher_obj = None
                    t_name = item['teacher'].strip()
                    if t_name and len(t_name) > 2 and not is_mil:
                        tsplit = t_name.split()
                        surname = tsplit[0]
                        teacher_qs = Teacher.objects.filter(
                            Q(user__last_name__icontains=surname) |
                            Q(user__first_name__icontains=surname)
                        )
                        if teacher_qs.exists():
                            teacher_obj = teacher_qs.first()
                        else:
                            try:
                                base_u = f"imp_{datetime.now().microsecond}_{surname[:5]}"
                                u = User.objects.create_user(username=base_u, password='123', role='TEACHER', last_name=surname, first_name=t_name[:100])
                                teacher_obj = Teacher.objects.create(user=u, department=dept)
                                stats['teachers'] += 1
                            except: pass

                    if teacher_obj and not subject.teacher:
                        subject.teacher = teacher_obj
                        subject.save()

                    room_obj = None
                    if item['room']:
                        room_clean = item['room'].strip()
                        if room_clean:
                            room_obj, _ = Classroom.objects.get_or_create(number=room_clean, defaults={'floor': 1})

                    ScheduleSlot.objects.filter(
                        group=group, semester=semester,
                        day_of_week=item['day'], time_slot=t_slot
                    ).delete()

                    ScheduleSlot.objects.create(
                        group=group,
                        semester=semester,
                        day_of_week=item['day'],
                        time_slot=t_slot,
                        subject=subject,
                        teacher=teacher_obj if not is_mil else None,
                        classroom=room_obj,
                        room=item['room'],
                        lesson_type=item['type'],
                        is_military=is_mil,
                        is_active=True,
                        start_time=t_slot.start_time,
                        end_time=t_slot.end_time
                    )
                    stats['slots'] += 1

            except Exception as e:
                print(f"Ошибка при сохранении слота: {e}")
                continue

        return stats

    def _extract_time_slot(self, val):
        clean = re.sub(r'[^\d]', '', str(val))
        if len(clean) >= 4:
            try:
                h, m = int(clean[:2]), int(clean[2:4])
                return TimeSlot.objects.filter(start_time__hour=h, start_time__minute=m).first()
            except: pass
        return None

    def _match_group(self, text):
        t = str(text).lower().replace(" ", "")
        for g in self.all_groups:
            if g.name.lower().replace(" ", "") in t: return g
            if re.search(r'\d-\d{5,}', t):
                if t.startswith(g.name.lower()[:5]): return g
        return None

    def _parse_cell_text(self, text):
        text = str(text).replace('\n', ' ').strip()

        l_type = 'LECTURE'
        low = text.lower()
        if any(x in low for x in ['(а)', '(амалӣ)', 'pr']): l_type = 'PRACTICE'
        elif any(x in low for x in ['(к)', '(кмро)', 'srsp']): l_type = 'SRSP'

        subj = text
        teach = ""

        titles = ['Дот', 'Асс', 'Проф', 'Омузгор', 'Муаллим']

        for title in titles:
            if title in text:
                parts = text.split(title)
                if len(parts) > 1:
                    subj = parts[0]
                    teach = title + parts[1]
                break

        if not teach and ')' in text:
            parts = text.split(')')
            subj = parts[0] + ')'
            if len(parts) > 1 and len(parts[1].strip()) > 3:
                teach = parts[1]

        subj = re.sub(r'\(.*?\)', '', subj).strip()
        if not subj: subj = "Нераспознанный предмет"

        teach = re.sub(r'[^\w\s\.]', '', teach).strip()

        return {'subject': subj, 'teacher': teach, 'type': l_type}

class RupImporter:
    @staticmethod
    def import_from_excel(file, plan_id, semester_number):
        plan = AcademicPlan.objects.get(id=plan_id)
        wb = openpyxl.load_workbook(file, data_only=True)
        sheet = wb.active
        
        stats = {'created': 0, 'updated': 0, 'errors': []}

        def to_int(val):
            if val is None:
                return 0
            val_str = str(val).strip()
            match = re.search(r'\d+', val_str)
            if match:
                return int(match.group())
            return 0

        current_disc_type = 'REQUIRED'

        for row_idx, row in enumerate(sheet.iter_rows(min_row=1, values_only=True), start=1):
            subj_name = str(row[0] or '').strip()

            if not subj_name or subj_name.lower() == 'none':
                continue

            lower_name = subj_name.lower()
            if 'ҳатмӣ' in lower_name or 'обязательн' in lower_name:
                current_disc_type = 'REQUIRED'
                continue
            if 'интихобӣ' in lower_name or 'ихтиёрӣ' in lower_name or 'выбор' in lower_name:
                current_disc_type = 'ELECTIVE'
                continue
            if 'номгӯйи' in lower_name or 'наименование' in lower_name or 'семестр' in lower_name:
                continue 

            try:
                with transaction.atomic():
                    template, _ = SubjectTemplate.objects.get_or_create(name=subj_name)

                    credits = to_int(row[1]) if len(row) > 1 else 0
                    lec = to_int(row[4]) if len(row) > 4 else 0
                    prac = to_int(row[5]) if len(row) > 5 else 0
                    srsp = to_int(row[6]) if len(row) > 6 else 0
                    srs = to_int(row[7]) if len(row) > 7 else 0

                    if lec == 0 and prac == 0 and srsp == 0 and srs == 0:
                        total_h = to_int(row[3]) if len(row) > 3 else 0
                        if total_h > 0:
                            srs = total_h 

                    discipline, created = PlanDiscipline.objects.update_or_create(
                        plan=plan,
                        subject_template=template,
                        semester_number=semester_number,
                        defaults={
                            'discipline_type': current_disc_type,
                            'credits': credits,
                            'lecture_hours': lec,
                            'practice_hours': prac,
                            'lab_hours': 0, 
                            'control_hours': srsp,
                            'independent_hours': srs,
                            'control_type': 'EXAM', 
                            'cycle': 'OTHER' 
                        }
                    )

                    if created:
                        stats['created'] += 1
                    else:
                        stats['updated'] += 1

            except Exception as e:
                stats['errors'].append(f"Строка {row_idx} ({subj_name}): {str(e)}")

        return stats
