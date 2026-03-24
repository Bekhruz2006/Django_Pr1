from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.http import JsonResponse
from accounts.models import Student, Teacher, Group, Institute, Department, Order, User
from news.models import News
from journal.models import StudentStatistics
from schedule.models import ScheduleSlot
import json
from datetime import datetime
from schedule.models import Semester, SubjectMaterial, AcademicPlan, Classroom, Subject
from lms.models import Course
import logging
logger = logging.getLogger(__name__)

def get_ai_report_status():
    active_sems = Semester.objects.filter(is_active=True)
    ai_report_ready = False
    days_until_report = 30
    
    for sem in active_sems:
        if sem.start_date:
            days_passed = (timezone.now().date() - sem.start_date).days
            if days_passed >= 30:
                ai_report_ready = True
                days_until_report = 0
                break
            else:
                if 30 - days_passed < days_until_report:
                    days_until_report = 30 - days_passed
                    
    return ai_report_ready, max(1, days_until_report)


def get_missing_rup_groups(faculty=None, institute=None):
    groups = Group.objects.all().select_related('specialty', 'specialty__department__faculty')
    if faculty:
        groups = groups.filter(specialty__department__faculty=faculty)
    elif institute:
        groups = groups.filter(specialty__department__faculty__institute=institute)

    active_plans = AcademicPlan.objects.filter(is_active=True)
    group_plans_ids = set(active_plans.exclude(group__isnull=True).values_list('group_id', flat=True))
    specialty_plans_ids = set(active_plans.exclude(specialty__isnull=True).values_list('specialty_id', flat=True))

    missing = []
    for g in groups:
        if g.id not in group_plans_ids and (not g.specialty_id or g.specialty_id not in specialty_plans_ids):
            missing.append(g)
    return missing


def get_algorithmic_risk_report(faculty=None, limit=5):
    qs = StudentStatistics.objects.filter(student__status='ACTIVE').select_related('student__user', 'student__group')
    
    if faculty:
        qs = qs.filter(student__group__specialty__department__faculty=faculty)
        
    problematic = qs.filter(
        Q(overall_gpa__lt=3.0) | 
        Q(attendance_percentage__lt=70.0, total_lessons__gt=0) | 
        Q(total_absent__gt=8)
    )
    
    risk_list = []
    for stat in problematic:
        reasons = []
        risk_score = 0
        
        if stat.overall_gpa < 2.5:
            reasons.append(f"Критический средний балл: {stat.overall_gpa:.1f}")
            risk_score += 3
        elif stat.overall_gpa < 3.0:
            reasons.append(f"Низкий средний балл: {stat.overall_gpa:.1f}")
            risk_score += 1
            
        if stat.total_lessons > 0:
            if stat.attendance_percentage < 50.0:
                reasons.append(f"Критическая посещаемость: {stat.attendance_percentage:.0f}%")
                risk_score += 3
            elif stat.attendance_percentage < 70.0:
                reasons.append(f"Низкая посещаемость: {stat.attendance_percentage:.0f}%")
                risk_score += 1
            
        if stat.total_absent > 15:
            reasons.append(f"Слишком много прогулов: {stat.total_absent} (НБ)")
            risk_score += 2
        elif stat.total_absent > 8:
            reasons.append(f"Частые пропуски: {stat.total_absent} (НБ)")
            risk_score += 1
            
        if risk_score >= 3:
            level = 'HIGH'
            level_display = 'Высокий риск'
            color = 'danger'
        elif risk_score > 0:
            level = 'MEDIUM'
            level_display = 'Средний риск'
            color = 'warning'
        else:
            continue
            
        risk_list.append({
            'student': stat.student,
            'gpa': stat.overall_gpa,
            'level': level,
            'level_display': level_display,
            'color': color,
            'reasons': reasons,
            'score': risk_score
        })
        
    risk_list.sort(key=lambda x: x['score'], reverse=True)
    return risk_list[:limit]


@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}

    context['news_list'] = News.objects.filter(is_published=True).order_by('-is_pinned', '-created_at')[:5]

    ai_report_ready, days_until_report = get_ai_report_status()
    context['ai_report_ready'] = ai_report_ready
    context['days_until_report'] = days_until_report

    if hasattr(user, 'director_profile') or hasattr(user, 'prorector_profile'):
        selected_institute_id = request.GET.get('institute_id')
        selected_institute = None
        institutes = Institute.objects.prefetch_related('faculties').all()

        students_qs = Student.objects.filter(status='ACTIVE')
        teachers_qs = Teacher.objects.all()
        groups_qs = Group.objects.all()
        orders_qs = Order.objects.filter(status='DRAFT').select_related('created_by').prefetch_related('items__student__user', 'items__student__group').order_by('date')


        if selected_institute_id:
            try:
                selected_institute = institutes.get(id=selected_institute_id)
                faculties_ids = selected_institute.faculties.values_list('id', flat=True)
                students_qs = students_qs.filter(group__specialty__department__faculty__in=faculties_ids)
                teachers_qs = teachers_qs.filter(department__faculty__in=faculties_ids)
                groups_qs = groups_qs.filter(specialty__department__faculty__in=faculties_ids)
                orders_qs = orders_qs.filter(
                    items__student__group__specialty__department__faculty__in=faculties_ids
                ).distinct()
            except Institute.DoesNotExist:
                pass

        context.update({
            'institutes': institutes,
            'selected_institute': selected_institute,
            'total_students': students_qs.count(),
            'total_teachers': teachers_qs.count(),
            'total_debtors': students_qs.filter(financing_type='CONTRACT').count(),
            'total_groups': groups_qs.count(),
            'pending_orders': orders_qs[:10],
            'pending_count': orders_qs.count(),
            'risk_report': get_algorithmic_risk_report(limit=5),
            'missing_rup_groups': get_missing_rup_groups(institute=selected_institute)
        })
        return render(request, 'core/dashboard_rector.html', context)

    elif user.is_superuser:
            selected_institute_id = request.GET.get('institute_id')
            selected_institute = None
            institutes = Institute.objects.prefetch_related('faculties').all()

            students_qs = Student.objects.filter(status='ACTIVE')
            teachers_qs = Teacher.objects.all()
            groups_qs = Group.objects.all()
            departments_qs = Department.objects.all()
            active_semesters = Semester.objects.filter(is_active=True).select_related('faculty')

            if selected_institute_id:
                try:
                    selected_institute = institutes.get(id=selected_institute_id)
                    faculties_ids = selected_institute.faculties.values_list('id', flat=True)
                    
                    students_qs = students_qs.filter(group__specialty__department__faculty__in=faculties_ids)
                    teachers_qs = teachers_qs.filter(department__faculty__in=faculties_ids)
                    groups_qs = groups_qs.filter(specialty__department__faculty__in=faculties_ids)
                    departments_qs = departments_qs.filter(faculty__in=faculties_ids)
                    active_semesters = active_semesters.filter(faculty__institute=selected_institute)
                except Institute.DoesNotExist:
                    pass

            context.update({
                'institutes': institutes,
                'selected_institute': selected_institute,
                'total_students': students_qs.count(),
                'total_groups': groups_qs.count(),
                'total_teachers': teachers_qs.count(),
                'total_departments': departments_qs.count(),
                'total_users': User.objects.count(),
                'latest_orders': Order.objects.all().order_by('-created_at')[:5],
                'active_semesters': active_semesters,
                'risk_report': get_algorithmic_risk_report(limit=5),
                'missing_rup_groups': get_missing_rup_groups(institute=selected_institute)
            })
            return render(request, 'core/dashboard_admin.html', context)
            
    elif hasattr(user, 'hr_profile'):
        context['total_students'] = Student.objects.filter(status='ACTIVE').count()
        context['unassigned_students'] = Student.objects.filter(group__isnull=True, status='ACTIVE').count()
        context['total_teachers'] = Teacher.objects.count()
        context['latest_users'] = User.objects.order_by('-date_joined')[:10]
        
        return render(request, 'core/dashboard_hr.html', context)

    elif hasattr(user, 'dean_profile') or hasattr(user, 'vicedean_profile'):
        profile = getattr(user, 'dean_profile', None) or getattr(user, 'vicedean_profile', None)
        faculty = profile.faculty if profile else None
        context['profile'] = profile
        context['faculty'] = faculty

        if not Semester.objects.filter(is_active=True).exists():
            messages.warning(request, "Внимание! Активный семестр не выбран. Расписание может не работать.")

        if faculty:
            students_count = Student.objects.filter(group__specialty__department__faculty=faculty).count()
            groups_count = Group.objects.filter(specialty__department__faculty=faculty).count()
            teachers_count = Teacher.objects.filter(department__faculty=faculty).count()

            context.update({
                'students_count': students_count,
                'groups_count': groups_count,
                'teachers_count': teachers_count,
                'departments': Department.objects.filter(faculty=faculty).prefetch_related('specialties'),
                'my_drafts': Order.objects.filter(created_by=user, status='DRAFT').count(),
                'risk_report': get_algorithmic_risk_report(faculty=faculty, limit=5),
                'missing_rup_groups': get_missing_rup_groups(faculty=faculty)
            })

            course_stats = []
            chart_courses = []
            chart_gpa = []
            chart_attendance = []

            for course_num in range(1, 6):
                students = Student.objects.filter(
                    group__course=course_num,
                    group__specialty__department__faculty=faculty
                )
                if students.exists():
                    stats = StudentStatistics.objects.filter(student__in=students)
                    avg_gpa = stats.aggregate(Avg('overall_gpa'))['overall_gpa__avg'] or 0
                    avg_att = stats.aggregate(Avg('attendance_percentage'))['attendance_percentage__avg'] or 0

                    course_stats.append({
                        'course': course_num,
                        'students_count': students.count(),
                        'avg_gpa': avg_gpa,
                        'avg_attendance': avg_att,
                    })

                    chart_courses.append(f"{course_num} курс")
                    chart_gpa.append(round(avg_gpa, 2))
                    chart_attendance.append(round(avg_att, 1))

            context['course_stats'] = course_stats
            context['json_courses'] = json.dumps(chart_courses)
            context['json_gpa'] = json.dumps(chart_gpa)
            context['json_attendance'] = json.dumps(chart_attendance)

        return render(request, 'core/dashboard_dean.html', context)

    elif hasattr(user, 'teacher_profile') or hasattr(user, 'head_of_dept_profile'):
            if hasattr(user, 'teacher_profile'):
                context['profile'] = user.teacher_profile
                
                context['my_materials'] = SubjectMaterial.objects.filter(
                    subject__teacher=user.teacher_profile
                ).order_by('-uploaded_at')[:10]
            elif hasattr(user, 'head_of_dept_profile'):
                context['profile'] = user.head_of_dept_profile
            return render(request, 'core/dashboard_teacher.html', context)

    elif hasattr(user, 'student_profile'):
        context['profile'] = user.student_profile
    else:
        context['profile'] = None

    try:
        today = datetime.now()
        day_of_week = today.weekday()
        current_time = today.time()
        classes =[]

        active_semester = Semester.objects.filter(is_active=True).first()

        if active_semester:
            base_slots = ScheduleSlot.objects.filter(
                semester=active_semester, is_active=True
            ).select_related('subject', 'teacher__user', 'classroom')

            if hasattr(user, 'student_profile') and user.student_profile.group:
                base_slots = base_slots.filter(group=user.student_profile.group)
            elif hasattr(user, 'teacher_profile'):
                base_slots = base_slots.filter(teacher=user.teacher_profile)
            else:
                base_slots = base_slots.none()

            from schedule.models import ScheduleException
            exceptions_today = ScheduleException.objects.filter(
                schedule_slot__in=base_slots, exception_date=today.date()
            ).values_list('schedule_slot_id', flat=True)

            rescheduled_to_today = ScheduleException.objects.filter(
                schedule_slot__in=base_slots, new_date=today.date()
            ).select_related('schedule_slot__subject', 'schedule_slot__teacher__user', 'schedule_slot__group')

            regular_classes = list(base_slots.filter(day_of_week=day_of_week).exclude(id__in=exceptions_today))
            
            for exc in rescheduled_to_today:
                exc.schedule_slot.start_time = exc.new_start_time or exc.schedule_slot.start_time
                exc.schedule_slot.end_time = exc.new_end_time or exc.schedule_slot.end_time
                if exc.new_classroom:
                    exc.schedule_slot.classroom = exc.new_classroom
                    exc.schedule_slot.room = exc.new_classroom.number
                regular_classes.append(exc.schedule_slot)

            classes = sorted(regular_classes, key=lambda x: x.start_time)

        context['classes'] = classes
        context['current_time'] = current_time
        context['today'] = today

    except Exception as e:
            logger.exception("Dashboard classes error")
            context['classes'] =[]

    return render(request, 'core/dashboard_student.html', context)


@login_required
def global_search(request):
    query = request.GET.get('q', '').strip()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        if not query or len(query) < 2:
            return JsonResponse({'results':[]})
        
        user = request.user
        institute = None
        is_management = False
        
        if hasattr(user, 'dean_profile') and user.dean_profile.faculty:
            institute = user.dean_profile.faculty.institute
            is_management = True
        elif hasattr(user, 'vicedean_profile') and user.vicedean_profile.faculty:
            institute = user.vicedean_profile.faculty.institute
            is_management = True
        elif hasattr(user, 'director_profile') and user.director_profile.institute:
            institute = user.director_profile.institute
            is_management = True
        elif hasattr(user, 'prorector_profile') and user.prorector_profile.institute:
            institute = user.prorector_profile.institute
            is_management = True
        elif hasattr(user, 'head_of_dept_profile') and user.head_of_dept_profile.department:
            institute = user.head_of_dept_profile.department.faculty.institute
            is_management = True
        elif user.is_superuser:
            is_management = True
        elif hasattr(user, 'teacher_profile') and user.teacher_profile.department:
            institute = user.teacher_profile.department.faculty.institute
        elif hasattr(user, 'student_profile') and user.student_profile.group and user.student_profile.group.specialty:
            institute = user.student_profile.group.specialty.department.faculty.institute

        students_qs = Student.objects.select_related('user', 'group')
        teachers_qs = Teacher.objects.select_related('user', 'department')
        groups_qs = Group.objects.all()
        courses_qs = Course.objects.select_related('category')
        subjects_qs = Subject.objects.select_related('department')
        classrooms_qs = Classroom.objects.select_related('building')

        if not user.is_superuser and institute:
            students_qs = students_qs.filter(group__specialty__department__faculty__institute=institute)
            teachers_qs = teachers_qs.filter(department__faculty__institute=institute)
            groups_qs = groups_qs.filter(specialty__department__faculty__institute=institute)
            courses_qs = courses_qs.filter(
                Q(allowed_faculty__institute=institute) | 
                Q(category__faculty__institute=institute) | 
                Q(category__institute=institute) |
                Q(enrolments__user=user)
            ).distinct()
            subjects_qs = subjects_qs.filter(department__faculty__institute=institute)
            classrooms_qs = classrooms_qs.filter(building__institute=institute)

        results =[]

        students = students_qs.filter(
            Q(user__first_name__icontains=query) | 
            Q(user__last_name__icontains=query) | 
            Q(student_id__icontains=query)
        )[:5]
        for s in students:
            results.append({
                'title': s.user.get_full_name(),
                'subtitle': f"Студент | {s.group.name if s.group else 'Без группы'}",
                'url': f"/accounts/profile/view/{s.user.id}/",
                'icon': 'bi-mortarboard text-primary'
            })

        teachers = teachers_qs.filter(
            Q(user__first_name__icontains=query) | 
            Q(user__last_name__icontains=query)
        )[:5]
        for t in teachers:
            results.append({
                'title': t.user.get_full_name(),
                'subtitle': f"Преподаватель | {t.department.name if t.department else ''}",
                'url': f"/accounts/profile/view/{t.user.id}/",
                'icon': 'bi-person-video3 text-success'
            })

        groups = groups_qs.filter(name__icontains=query)[:5]
        for g in groups:
            results.append({
                'title': g.name,
                'subtitle': f"Группа | {g.course} курс",
                'url': f"/accounts/groups/{g.id}/view/",
                'icon': 'bi-people text-warning'
            })

        courses = courses_qs.filter(
            Q(full_name__icontains=query) | Q(short_name__icontains=query)
        )[:5]
        for c in courses:
            results.append({
                'title': c.short_name,
                'subtitle': f"Курс (LMS) | {c.category.name}",
                'url': f"/lms/courses/{c.id}/",
                'icon': 'bi-laptop text-info'
            })

        if is_management or hasattr(user, 'teacher_profile'):
            subjects = subjects_qs.filter(
                Q(name__icontains=query) | Q(code__icontains=query)
            )[:5]
            for sub in subjects:
                url = f"/schedule/subjects/{sub.id}/edit/" if is_management else f"/schedule/subject/{sub.id}/materials/"
                results.append({
                    'title': sub.name,
                    'subtitle': f"Предмет | {sub.department.name if sub.department else ''}",
                    'url': url,
                    'icon': 'bi-book text-secondary'
                })

        if is_management:
            classrooms = classrooms_qs.filter(number__icontains=query)[:5]
            for room in classrooms:
                results.append({
                    'title': f"Аудитория {room.number}",
                    'subtitle': f"Кабинет | {room.building.name if room.building else ''} ({room.get_room_type_display()})",
                    'url': f"/schedule/classrooms/{room.id}/edit/",
                    'icon': 'bi-door-open text-danger'
                })

        return JsonResponse({'results': results})

    return render(request, 'core/search_results.html', {'query': query})
