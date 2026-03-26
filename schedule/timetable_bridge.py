from __future__ import annotations

import json
import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import List, Optional
import os
from django.db import transaction
from django.db.models import Count, Prefetch
from .models import (
    ScheduleSlot, Subject, Classroom, TimeSlot,
    TeacherUnavailableSlot, Semester,
)
from accounts.models import Group, Teacher
import logging

logger = logging.getLogger(__name__)

_bin_dir = Path(__file__).parent / "bin"
BINARY_PATH = _bin_dir / ("timetable_engine.exe" if os.name == "nt" else "timetable_engine")

if not BINARY_PATH.exists():
    if (_bin_dir / "timetable_engine.exe").exists():
        BINARY_PATH = _bin_dir / "timetable_engine.exe"
    elif (_bin_dir / "timetable_engine").exists():
        BINARY_PATH = _bin_dir / "timetable_engine"


class TimetableError(Exception):
    pass


def _weekly_slots(subj: Subject) -> dict[str, float]:
    actual_weeks = subj.get_actual_semester_weeks() or 16

    lec_h = subj.lecture_hours
    prac_h = subj.practice_hours
    lab_h = subj.lab_hours
    srsp_h = subj.control_hours

    if lec_h == 0 and prac_h == 0 and lab_h == 0 and srsp_h == 0 and subj.credits > 0:
        total_auditory = (subj.credits * 24) * 2 // 3
        lec_h = total_auditory // 3
        prac_h = total_auditory // 3
        srsp_h = total_auditory - lec_h - prac_h

    def pairs(h: int) -> float:
        if not h or h <= 0:
            return 0.0
        return float(subj.get_hours_in_pairs(h))

    return {
        "LECTURE": round(pairs(lec_h) / actual_weeks, 4),
        "PRACTICE": round(pairs(prac_h) / actual_weeks, 4),
        "LAB": round(pairs(lab_h) / actual_weeks, 4),
        "SRSP": round(pairs(srsp_h) / actual_weeks, 4),
    }


class TimetableBridge:
    def __init__(self, binary: Path = BINARY_PATH):
        self.binary = binary

    def build_payload(
        self,
        semester: Semester,
        target_groups,
        target_teachers: Optional[List[int]] = None,
        target_rooms: Optional[List[int]] = None,
        avoid_gaps: bool = True,
        overflow_mode: int = 1,
        strict_room_types: bool = False,
        sa_restarts: int = 6,
        sa_steps: int = 400000,
        max_seconds: int = 90,
        institute=None,
    ) -> dict:
        logger.info(
            "TimetableBridge.build_payload: semester=%s overflow_mode=%s strict_room_types=%s avoid_gaps=%s",
            semester, overflow_mode, strict_room_types, avoid_gaps
        )

        ts_qs = TimeSlot.objects.filter(shift=semester.shift)
        if institute:
            inst_ts = ts_qs.filter(institute=institute)
            ts_qs = inst_ts if inst_ts.exists() else ts_qs.filter(institute__isnull=True)
        else:
            ts_qs = ts_qs.filter(institute__isnull=True)
        time_slots = list(ts_qs.order_by("start_time"))

        ts_id_to_idx = {ts.id: i for i, ts in enumerate(time_slots)}

        slots_json = [
            {
                "id": ts.id,
                "index": i,
                "number": i + 1,
                "start_time": ts.start_time.strftime("%H:%M"),
                "end_time": ts.end_time.strftime("%H:%M"),
            }
            for i, ts in enumerate(time_slots)
        ]

        room_qs = Classroom.objects.filter(is_active=True)
        if target_rooms:
            room_qs = room_qs.filter(id__in=target_rooms)

        rooms_json = [
            {
                "id": r.id,
                "number": r.number,
                "capacity": r.capacity,
                "room_type": r.room_type,
            }
            for r in room_qs
        ]

        target_groups_qs = (
            target_groups
            if hasattr(target_groups, "annotate")
            else Group.objects.filter(id__in=[g.id for g in target_groups])
        )
        target_groups_qs = target_groups_qs.annotate(
            student_count=Count("students", distinct=True)
        )

        groups_list = list(target_groups_qs)
        group_ids_set = {g.id for g in groups_list}

        groups_json = [
            {
                "id": g.id,
                "name": g.name,
                "student_count": g.student_count,
            }
            for g in groups_list
        ]

        subjects_qs = (
            Subject.objects
            .filter(groups__in=group_ids_set)
            .prefetch_related(
                Prefetch(
                    "groups",
                    queryset=Group.objects.annotate(student_count=Count("students", distinct=True)),
                    to_attr="all_groups",
                )
            )
            .select_related("teacher")
            .distinct()
        )
        if target_teachers:
            subjects_qs = subjects_qs.filter(teacher_id__in=target_teachers)

        subjects_list = list(subjects_qs)

        teacher_ids = {
            subj.teacher_id
            for subj in subjects_list
            if subj.teacher_id
        }
        if target_teachers:
            teacher_ids.update(target_teachers)

        unavail_map: dict[int, list] = {}
        for u in TeacherUnavailableSlot.objects.filter(teacher_id__in=teacher_ids):
            unavail_map.setdefault(u.teacher_id, []).append(
                {
                    "teacher_id": u.teacher_id,
                    "day_of_week": u.day_of_week,
                    "time_slot_id": u.time_slot_id,
                }
            )

        teachers_json = []
        for t in Teacher.objects.filter(id__in=teacher_ids).select_related("user"):
            teachers_json.append(
                {
                    "id": t.id,
                    "name": t.user.get_full_name(),
                }
            )

        teacher_unavail_json = [
            entry
            for entries in unavail_map.values()
            for entry in entries
        ]

        group_unavailable_json = []
        if group_ids_set and time_slots:
            valid_ts_ids = set(ts_id_to_idx.keys())
            existing_slots_qs = ScheduleSlot.objects.filter(
                semester=semester,
                group_id__in=group_ids_set,
                is_active=True,
                time_slot_id__in=valid_ts_ids,
            ).values("group_id", "day_of_week", "time_slot_id", "week_type", "is_military")

            seen = set()
            for slot in existing_slots_qs:
                wt = slot["week_type"]
                week_types_to_block = ["RED", "BLUE"] if wt == "EVERY" else [wt]
                for block_wt in week_types_to_block:
                    key = (slot["group_id"], slot["day_of_week"], slot["time_slot_id"], block_wt)
                    if key not in seen:
                        seen.add(key)
                        group_unavailable_json.append({
                            "group_id": slot["group_id"],
                            "day_of_week": slot["day_of_week"],
                            "time_slot_id": slot["time_slot_id"],
                            "week_type": block_wt,
                        })

        def _students(grp) -> int:
            return getattr(grp, "student_count", 0) or 0

        tasks_json = []
        for subj in subjects_list:
            all_groups_for_subj = getattr(subj, "all_groups", [])
            if not all_groups_for_subj:
                continue

            if not any(g.id in group_ids_set for g in all_groups_for_subj):
                continue

            slot_map = _weekly_slots(subj)

            if subj.is_stream_subject and len(all_groups_for_subj) > 1:
                total_students = sum(_students(g) for g in all_groups_for_subj)
                for lt, weekly in slot_map.items():
                    if weekly <= 0:
                        continue
                    tasks_json.append(
                        {
                            "subject_id": subj.id,
                            "subject_name": subj.name,
                            "teacher_id": subj.teacher_id or -1,
                            "group_ids": [g.id for g in all_groups_for_subj],
                            "lesson_type": lt,
                            "is_stream": True,
                            "stream_tag": subj.id,
                            "students": total_students,
                            "preferred_room_type": subj.preferred_room_type or "",
                            "weekly_slots": weekly,
                        }
                    )
            else:
                for grp in all_groups_for_subj:
                    if grp.id not in group_ids_set:
                        continue
                    total_students = _students(grp)
                    for lt, weekly in slot_map.items():
                        if weekly <= 0:
                            continue
                        tasks_json.append(
                            {
                                "subject_id": subj.id,
                                "subject_name": subj.name,
                                "teacher_id": subj.teacher_id or -1,
                                "group_ids": [grp.id],
                                "lesson_type": lt,
                                "is_stream": False,
                                "stream_tag": -1,
                                "students": total_students,
                                "preferred_room_type": subj.preferred_room_type or "",
                                "weekly_slots": weekly,
                            }
                        )

        logger.debug(
            "TimetableBridge.build_payload: tasks=%s rooms=%s groups=%s teachers=%s "
            "teacher_unavail=%s group_unavail=%s",
            len(tasks_json), len(rooms_json), len(groups_json),
            len(teachers_json), len(teacher_unavail_json), len(group_unavailable_json)
        )

        return {
            "time_slots": slots_json,
            "rooms": rooms_json,
            "groups": groups_json,
            "tasks": tasks_json,
            "teachers": teachers_json,
            "teacher_unavailable": teacher_unavail_json,
            "group_unavailable": group_unavailable_json,
            "sa_t0": 1200.0,
            "sa_cooling": 0.99985,
            "sa_reheat": 1.5,
            "sa_restarts": sa_restarts,
            "sa_steps": sa_steps,
            "max_seconds": max_seconds,
            "overflow_mode": overflow_mode,
            "strict_room_types": strict_room_types,
            "avoid_gaps": avoid_gaps,
        }

    def run(self, payload: dict) -> dict:
        if not self.binary.exists():
            logger.error("Timetable engine binary not found at: %s", self.binary)
            raise TimetableError(
                f"Engine binary not found: {self.binary}\n"
                "Compile with:\n"
                "  g++ -O3 -std=c++17 -pthread "
                "-o schedule/bin/timetable_engine schedule/timetable_engine.cpp"
            )

        logger.info(
            "TimetableBridge.run: launching binary=%s payload_tasks=%s payload_rooms=%s",
            self.binary.name,
            len(payload.get('tasks', [])),
            len(payload.get('rooms', []))
        )

        proc = subprocess.run(
            [str(self.binary)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if proc.stderr:
            for line in proc.stderr.strip().splitlines():
                logger.debug("timetable_engine stderr: %s", line)

        if proc.returncode != 0:
            logger.error(
                "TimetableBridge.run: engine exited with code=%s stderr=%s",
                proc.returncode, proc.stderr[:500]
            )
            raise TimetableError(
                f"Engine exited with code {proc.returncode}.\n"
                f"stderr: {proc.stderr[:2000]}"
            )

        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            logger.error(
                "TimetableBridge.run: invalid JSON from engine: %s | stdout[:200]=%s",
                exc, proc.stdout[:200]
            )
            raise TimetableError(
                f"Engine output is not valid JSON: {exc}\n"
                f"{proc.stdout[:500]}"
            ) from exc

        if not result.get("success", False):
            logger.error("TimetableBridge.run: engine returned success=false error=%s", result.get("error"))
            raise TimetableError(result.get("error", "Unknown engine error"))

        logger.info(
            "TimetableBridge.run: engine success placed=%s unplaced=%s score=%s elapsed_ms=%s",
            result.get('placed_count'), result.get('unplaced_count'),
            result.get('score'), result.get('elapsed_ms')
        )

        return result

    @transaction.atomic
    def save_result(self, result: dict, semester: Semester) -> dict:
        slots_data = result.get("schedule", [])

        logger.info(
            "TimetableBridge.save_result: saving %s slots for semester=%s",
            len(slots_data), semester
        )

        if not slots_data:
            logger.warning("TimetableBridge.save_result: empty schedule returned from engine")
            return self._summary(result, created=0)

        ts_ids = set()
        grp_ids = set()
        sub_ids = set()
        tch_ids = set()
        cls_ids = set()

        for item in slots_data:
            ts_ids.add(item["time_slot_id"])
            grp_ids.add(item["group_id"])
            sub_ids.add(item["subject_id"])
            tid = item.get("teacher_id")
            if tid and tid != -1:
                tch_ids.add(tid)
            cid = item.get("classroom_id")
            if cid:
                cls_ids.add(cid)

        ts_map = TimeSlot.objects.in_bulk(ts_ids)
        grp_map = Group.objects.in_bulk(grp_ids)
        sub_map = Subject.objects.in_bulk(sub_ids)
        tch_map = Teacher.objects.in_bulk(tch_ids)
        cls_map = Classroom.objects.in_bulk(cls_ids)

        missing_ts = ts_ids - set(ts_map.keys())
        missing_grp = grp_ids - set(grp_map.keys())
        missing_sub = sub_ids - set(sub_map.keys())

        if missing_ts:
            logger.warning("TimetableBridge.save_result: missing TimeSlot ids=%s", missing_ts)
        if missing_grp:
            logger.warning("TimetableBridge.save_result: missing Group ids=%s", missing_grp)
        if missing_sub:
            logger.warning("TimetableBridge.save_result: missing Subject ids=%s", missing_sub)

        created_slots: list[ScheduleSlot] = []
        stream_key_to_uuid: dict[str, uuid.UUID] = {}
        skipped = 0

        for item in slots_data:
            ts_id = item["time_slot_id"]
            group_id = item["group_id"]
            subject_id = item["subject_id"]
            teacher_id = item.get("teacher_id")
            cls_id = item.get("classroom_id")
            day = item["day_of_week"]
            lt = item["lesson_type"]
            wt = item["week_type"]
            is_stream = item.get("is_stream", False)
            room_num = item.get("room_number", "")

            ts = ts_map.get(ts_id)
            grp = grp_map.get(group_id)
            sub = sub_map.get(subject_id)

            if not (ts and grp and sub):
                logger.warning(
                    "TimetableBridge.save_result: skipping slot — missing FK "
                    "ts_id=%s(found=%s) group_id=%s(found=%s) subject_id=%s(found=%s)",
                    ts_id, ts is not None,
                    group_id, grp is not None,
                    subject_id, sub is not None
                )
                skipped += 1
                continue

            teacher = tch_map.get(teacher_id) if teacher_id and teacher_id != -1 else None
            classroom = cls_map.get(cls_id) if cls_id else None

            if cls_id and not classroom:
                logger.warning(
                    "TimetableBridge.save_result: classroom_id=%s not found for subject=%s group=%s",
                    cls_id, sub.name, grp.name
                )

            stream_id = None
            if is_stream:
                key = f"{subject_id}_{day}_{ts_id}_{wt}"
                if key not in stream_key_to_uuid:
                    stream_key_to_uuid[key] = uuid.uuid4()
                stream_id = stream_key_to_uuid[key]

            created_slots.append(
                ScheduleSlot(
                    group=grp,
                    subject=sub,
                    teacher=teacher,
                    semester=semester,
                    day_of_week=day,
                    time_slot=ts,
                    start_time=ts.start_time,
                    end_time=ts.end_time,
                    classroom=classroom,
                    room=room_num,
                    lesson_type=lt,
                    week_type=wt,
                    stream_id=stream_id,
                    is_active=True,
                )
            )

        if skipped:
            logger.error(
                "TimetableBridge.save_result: skipped %s slot(s) due to missing FK references",
                skipped
            )

        ScheduleSlot.objects.bulk_create(created_slots)

        logger.info(
            "TimetableBridge.save_result: bulk_created=%s slots, skipped=%s",
            len(created_slots), skipped
        )

        return self._summary(result, created=len(created_slots))

    def generate(self, semester, target_groups, **kwargs) -> dict:
        payload = self.build_payload(semester, target_groups, **kwargs)
        result = self.run(payload)
        return self.save_result(result, semester)

    @staticmethod
    def _summary(result: dict, created: int) -> dict:
        return {
            "success": True,
            "created": created,
            "unplaced_count": result.get("unplaced_count", 0),
            "score": result.get("score", 0),
            "elapsed_ms": result.get("elapsed_ms", 0),
            "unassigned": result.get("unassigned_details", []),
        }


class AutoScheduleEngineCpp:
    def __init__(
        self,
        semester,
        target_groups=None,
        target_teachers=None,
        target_rooms=None,
        avoid_gaps=True,
        overflow_mode=1,
        strict_room_types=False,
        iterations=6,
        institute=None,
    ):
        self.semester = semester
        self.target_groups = target_groups
        self.target_teachers = list(target_teachers) if target_teachers else None
        self.target_rooms = list(target_rooms) if target_rooms else None
        self.avoid_gaps = avoid_gaps
        self.overflow_mode = overflow_mode
        self.strict_room_types = strict_room_types
        self.sa_restarts = max(2, min(iterations, 12))
        self.institute = institute
        self._bridge = TimetableBridge()

    def generate(self) -> dict:
        logger.info(
            "AutoScheduleEngineCpp.generate: semester=%s groups=%s teachers=%s rooms=%s "
            "sa_restarts=%s overflow_mode=%s strict_room_types=%s avoid_gaps=%s institute=%s",
            self.semester,
            [g.id for g in (self.target_groups or [])],
            self.target_teachers,
            self.target_rooms,
            self.sa_restarts,
            self.overflow_mode,
            self.strict_room_types,
            self.avoid_gaps,
            self.institute
        )
        try:
            payload = self._bridge.build_payload(
                semester=self.semester,
                target_groups=self.target_groups,
                target_teachers=self.target_teachers,
                target_rooms=self.target_rooms,
                avoid_gaps=self.avoid_gaps,
                overflow_mode=self.overflow_mode,
                strict_room_types=self.strict_room_types,
                sa_restarts=self.sa_restarts,
                sa_steps=400000,
                max_seconds=90,
                institute=self.institute,
            )
            result = self._bridge.run(payload)
            saved = self._bridge.save_result(result, self.semester)

            logger.info(
                "AutoScheduleEngineCpp.generate finished: created=%s unplaced=%s score=%s elapsed_ms=%s",
                saved['created'], saved['unplaced_count'],
                result.get('score'), result.get('elapsed_ms')
            )

            return {
                "success": saved["success"],
                "created": saved["created"],
                "unassigned_count": saved["unplaced_count"],
                "unassigned_details": saved["unassigned"],
            }
        except Exception as e:
            logger.exception(
                "AutoScheduleEngineCpp.generate failed for semester=%s: %s",
                self.semester, e
            )
            raise