from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.utils.translation import gettext as _
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Avg
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from accounts.models import Student, User
from lms.services import LMSManager

from .models import (
    Course, CourseCategory, CourseSection, CourseModule,
    CourseEnrolment, ModuleCompletion, PageContent, FileResource,
    FolderResource, FolderFile, UrlResource, VideoResource,
    Assignment, AssignmentSubmission, Forum, ForumThread, ForumPost,
    Glossary, GlossaryEntry, GradeItem, GradeEntry, CourseAnnouncement, 
)
from .forms import (
    CourseForm, CourseCategoryForm, CourseSectionForm, CourseModuleForm,
    PageContentForm, FileResourceForm, FolderFileForm, UrlResourceForm,
    VideoResourceForm, AssignmentForm, SubmissionForm, GradeSubmissionForm,
    ForumThreadForm, ForumPostForm, GlossaryEntryForm, EnrolUsersForm,
    GradeItemForm, GradeEntryForm,
)
from .permissions import (
    get_lms_role, is_lms_admin, is_lms_specialist, is_lms_teacher,
    can_manage_course, can_view_course, get_manageable_courses,
)



def course_access_required(manage=False):
    """Decorator factory for course access."""
    def decorator(view_func):
        @login_required
        def wrapped(request, course_id, *args, **kwargs):
            course = get_object_or_404(Course, pk=course_id)
            if manage:
                if not can_manage_course(request.user, course):
                    return HttpResponseForbidden(_("Нет прав на управление курсом"))
            else:
                if not can_view_course(request.user, course):
                    return HttpResponseForbidden(_("Нет доступа к курсу"))
            enrolment = course.get_enrolment(request.user)
            if enrolment:
                enrolment.touch()
            return view_func(request, course, *args, **kwargs)
        return wrapped
    return decorator



@login_required
def dashboard(request):
    user = request.user
    role = get_lms_role(user)

    enrolled_courses = Course.objects.filter(
        enrolments__user=user, enrolments__is_active=True
    ).prefetch_related('enrolments').order_by('full_name')

    manageable = get_manageable_courses(user).order_by('full_name') if is_lms_teacher(user) else Course.objects.none()

    upcoming_assignments = AssignmentSubmission.objects.filter(
        student=user, status='DRAFT',
        assignment__due_date__gte=timezone.now()
    ).select_related('assignment__module__section__course').order_by('assignment__due_date')[:5]

    ctx = {
        'role': role,
        'enrolled_courses': enrolled_courses,
        'manageable_courses': manageable,
        'upcoming_assignments': upcoming_assignments,
    }
    return render(request, 'lms/dashboard.html', ctx)


@login_required
def course_list(request):
    user = request.user
    role = get_lms_role(user)
    category_id = request.GET.get('category')
    search = request.GET.get('q', '').strip()

    if role in ['ADMIN', 'SPECIALIST']:
        qs = Course.objects.all() 
    else:
        qs = Course.objects.filter(is_visible=True, enrolments__user=user, enrolments__is_active=True)

    if category_id:
        qs = qs.filter(category_id=category_id)
    if search:
        qs = qs.filter(Q(full_name__icontains=search) | Q(short_name__icontains=search))

    qs = qs.select_related('category', 'created_by').order_by('full_name')
    page = Paginator(qs, 20).get_page(request.GET.get('page'))

    return render(request, 'lms/course_list.html', {
        'page_obj': page,
        'categories': CourseCategory.objects.order_by('sort_order', 'name'),
        'role': role,
        'search': search,
    })


@login_required
def course_detail(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user   = request.user

    if not can_view_course(user, course):
        return HttpResponseForbidden(_("Нет доступа к курсу"))

    enrolment  = course.get_enrolment(user)
    can_manage = can_manage_course(user, course)
    progress   = course.get_progress(user)

    if enrolment:
        enrolment.touch()

    sections = course.sections.prefetch_related('modules').filter(is_visible=True)
    if can_manage:
        sections = course.sections.prefetch_related('modules')

    completed_ids = set(
        ModuleCompletion.objects.filter(user=user, is_completed=True)
        .values_list('module_id', flat=True)
    )

    announcements = course.announcements.all()[:5]

    return render(request, 'lms/course_detail.html', {
        'course': course,
        'enrolment': enrolment,
        'can_manage': can_manage,
        'progress': progress,
        'sections': sections,
        'completed_ids': completed_ids,
        'announcements': announcements,
        'role': get_lms_role(user),
    })



@login_required
def course_create(request):
    if not is_lms_teacher(request.user):
        return HttpResponseForbidden()
    form = CourseForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        course = form.save(commit=False)
        course.created_by = request.user
        course.save()
        CourseEnrolment.objects.get_or_create(course=course, user=request.user, defaults={'role': 'TEACHER'})
        messages.success(request, _("Курс создан"))
        return redirect('lms:course_detail', course_id=course.pk)
    return render(request, 'lms/course_form.html', {'form': form, 'title': _('Создать курс')})


@login_required
def course_edit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        return HttpResponseForbidden()
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    if form.is_valid():
        form.save()
        messages.success(request, _("Курс обновлён"))
        return redirect('lms:course_detail', course_id=course.pk)
    return render(request, 'lms/course_form.html', {'form': form, 'course': course, 'title': _('Редактировать курс')})


@login_required
def course_delete(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not (can_manage_course(request.user, course) and is_lms_admin(request.user)):
        return HttpResponseForbidden()
    if request.method == 'POST':
        course.delete()
        messages.success(request, _("Курс удалён"))
        return redirect('lms:course_list')
    return render(request, 'lms/confirm_delete.html', {'obj': course, 'obj_name': course.full_name})


@login_required
def section_create(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        return HttpResponseForbidden()
    form = CourseSectionForm(request.POST or None)
    if form.is_valid():
        section = form.save(commit=False)
        section.course = course
        last = course.sections.order_by('-sequence').first()
        section.sequence = (last.sequence + 1) if last else 0
        section.save()
        messages.success(request, _("Секция добавлена"))
        return redirect('lms:course_detail', course_id=course.pk)
    return render(request, 'lms/section_form.html', {'form': form, 'course': course})


@login_required
def section_edit(request, section_id):
    section = get_object_or_404(CourseSection, pk=section_id)
    if not can_manage_course(request.user, section.course):
        return HttpResponseForbidden()
    form = CourseSectionForm(request.POST or None, instance=section)
    if form.is_valid():
        form.save()
        messages.success(request, _("Секция обновлена"))
        return redirect('lms:course_detail', course_id=section.course.pk)
    return render(request, 'lms/section_form.html', {'form': form, 'course': section.course, 'section': section})


@login_required
def section_delete(request, section_id):
    section = get_object_or_404(CourseSection, pk=section_id)
    if not can_manage_course(request.user, section.course):
        return HttpResponseForbidden()
    course = section.course
    if request.method == 'POST':
        section.delete()
        messages.success(request, _("Секция удалена"))
    return redirect('lms:course_detail', course_id=course.pk)



@login_required
def module_create(request, section_id):
    section = get_object_or_404(CourseSection, pk=section_id)
    if not can_manage_course(request.user, section.course):
        return HttpResponseForbidden()
    module_type = request.GET.get('type', 'PAGE')
    form = CourseModuleForm(request.POST or None, initial={'module_type': module_type})
    if form.is_valid():
        module = form.save(commit=False)
        module.section = section
        last = section.modules.order_by('-sequence').first()
        module.sequence = (last.sequence + 1) if last else 0
        module.save()
        _create_module_content(module)
        messages.success(request, _("Модуль добавлен"))
        return redirect('lms:module_edit', module_id=module.pk)
    return render(request, 'lms/module_form.html', {
        'form': form, 'section': section, 'course': section.course
    })


def _create_module_content(module):
    t = module.module_type
    if t == 'PAGE':
        PageContent.objects.create(module=module, content='')
    elif t == 'FOLDER':
        FolderResource.objects.create(module=module)
    elif t == 'URL':
        UrlResource.objects.create(module=module, external_url='http://')
    elif t == 'VIDEO':
        VideoResource.objects.create(module=module)
    elif t == 'ASSIGNMENT':
        Assignment.objects.create(module=module, description='')
    elif t == 'FORUM':
        Forum.objects.create(module=module)
    elif t == 'GLOSSARY':
        Glossary.objects.create(module=module)
    elif t == 'QUIZ':
        from testing.models import Quiz
        Quiz.objects.create(module=module, description='Новый тест')

@login_required
def module_edit(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id)
    if not can_manage_course(request.user, module.section.course):
        return HttpResponseForbidden()

    base_form = CourseModuleForm(request.POST or None, instance=module)
    content_form = _get_content_form(module, request)

    if base_form.is_valid() and (content_form is None or content_form.is_valid()):
        base_form.save()
        if content_form:
            content_obj = content_form.save(commit=False)
            content_obj.module = module
            content_obj.save()
        messages.success(request, _("Модуль обновлён"))
        return redirect('lms:course_detail', course_id=module.section.course.pk)

    return render(request, 'lms/module_edit.html', {
        'module': module,
        'base_form': base_form,
        'content_form': content_form,
        'course': module.section.course,
    })


def _get_content_form(module, request):
    data = request.POST or None
    files = request.FILES or None
    t = module.module_type
    if t == 'PAGE':
        inst = getattr(module, 'page_content', None)
        return PageContentForm(data, instance=inst)
    if t == 'FILE':
        inst = getattr(module, 'file_resource', None)
        return FileResourceForm(data, files, instance=inst)
    if t == 'URL':
        inst = getattr(module, 'url_resource', None)
        return UrlResourceForm(data, instance=inst)
    if t == 'VIDEO':
        inst = getattr(module, 'video_resource', None)
        return VideoResourceForm(data, files, instance=inst)
    if t == 'ASSIGNMENT':
        inst = getattr(module, 'assignment', None)
        return AssignmentForm(data, instance=inst)
    return None


@login_required
def module_delete(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id)
    if not can_manage_course(request.user, module.section.course):
        return HttpResponseForbidden()
    course_id = module.section.course.pk
    if request.method == 'POST':
        module.delete()
        messages.success(request, _("Модуль удалён"))
    return redirect('lms:course_detail', course_id=course_id)


@login_required
def module_detail(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id)
    course = module.section.course
    user   = request.user

    if not can_view_course(user, course):
        return HttpResponseForbidden()
    if not module.is_visible and not can_manage_course(user, course):
        raise Http404

    completion, _ = ModuleCompletion.objects.get_or_create(user=user, module=module)
    completion.view_count += 1
    if module.completion_required and not completion.is_completed:
        completion.is_completed = True
        completion.completed_at = timezone.now()
    completion.save()

    ctx = {
        'module': module,
        'course': course,
        'completion': completion,
        'can_manage': can_manage_course(user, course),
    }

    t = module.module_type
    if t == 'PAGE':
        ctx['page'] = getattr(module, 'page_content', None)
    elif t == 'FILE':
        ctx['resource'] = getattr(module, 'file_resource', None)
    elif t == 'FOLDER':
        fr = getattr(module, 'folder_resource', None)
        ctx['files'] = fr.files.all() if fr else []
    elif t == 'URL':
        ctx['url_res'] = getattr(module, 'url_resource', None)
    elif t == 'VIDEO':
        ctx['video'] = getattr(module, 'video_resource', None)
    elif t == 'ASSIGNMENT':
        assign = getattr(module, 'assignment', None)
        ctx['assignment'] = assign
        if assign:
            ctx['submission'] = assign.submissions.filter(student=user).first()
            if can_manage_course(user, course):
                ctx['all_submissions'] = assign.submissions.select_related('student').order_by('-submitted_at')
    elif t == 'FORUM':
        forum = getattr(module, 'forum', None)
        ctx['forum'] = forum
        if forum:
            ctx['threads'] = forum.threads.select_related('author').annotate(post_count=Count('posts'))
    elif t == 'GLOSSARY':
        glossary = getattr(module, 'glossary', None)
        ctx['glossary'] = glossary
        if glossary:
            ctx['entries'] = glossary.entries.all()

    return render(request, f'lms/modules/{t.lower()}.html', ctx)



@login_required
def assignment_submit(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id, module_type='ASSIGNMENT')
    course = module.section.course
    user   = request.user

    if not can_view_course(user, course):
        return HttpResponseForbidden()

    assignment = module.assignment
    submission, _ = AssignmentSubmission.objects.get_or_create(
        assignment=assignment, student=user
    )

    if submission.status in ('SUBMITTED', 'GRADED'):
        messages.warning(request, _("Работа уже сдана"))
        return redirect('lms:module_detail', module_id=module_id)

    form = SubmissionForm(request.POST or None, request.FILES or None, instance=submission)
    if form.is_valid():
        sub = form.save(commit=False)
        sub.status = 'SUBMITTED'
        # Check if late
        if assignment.due_date and timezone.now() > assignment.due_date:
            sub.is_late = True
        sub.save()
        messages.success(request, _("Работа отправлена на проверку"))
        return redirect('lms:module_detail', module_id=module_id)

    return render(request, 'lms/assignment_submit.html', {
        'form': form, 'module': module, 'assignment': assignment,
        'submission': submission, 'course': course,
    })


@login_required
def assignment_grade(request, submission_id):
    submission = get_object_or_404(AssignmentSubmission, pk=submission_id)
    module     = submission.assignment.module
    course     = module.section.course

    if not can_manage_course(request.user, course):
        return HttpResponseForbidden()

    form = GradeSubmissionForm(request.POST or None, initial={
        'score': submission.score, 'feedback': submission.teacher_feedback
    })
    if form.is_valid():
        submission.score = form.cleaned_data['score']
        submission.teacher_feedback = form.cleaned_data['feedback']
        submission.status = form.cleaned_data['action']
        submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()
        messages.success(request, _("Оценка сохранена"))
        return redirect('lms:module_detail', module_id=module.pk)

    return render(request, 'lms/assignment_grade.html', {
        'form': form, 'submission': submission, 'module': module, 'course': course,
    })



@login_required
def forum_thread_create(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id, module_type='FORUM')
    course = module.section.course
    if not can_view_course(request.user, course):
        return HttpResponseForbidden()

    forum = module.forum
    form  = ForumThreadForm(request.POST or None)
    if form.is_valid():
        thread = form.save(commit=False)
        thread.forum  = forum
        thread.author = request.user
        thread.save()
        # Add first post from body if provided
        body = request.POST.get('body', '').strip()
        if body:
            ForumPost.objects.create(thread=thread, author=request.user, body=body)
        return redirect('lms:forum_thread', thread_id=thread.pk)

    return render(request, 'lms/forum_thread_form.html', {
        'form': form, 'module': module, 'course': course
    })


@login_required
def forum_thread_detail(request, thread_id):
    thread = get_object_or_404(ForumThread, pk=thread_id)
    module = thread.forum.module
    course = module.section.course

    if not can_view_course(request.user, course):
        return HttpResponseForbidden()

    posts = thread.posts.select_related('author').order_by('created_at')
    form  = ForumPostForm(request.POST or None)
    if form.is_valid():
        post = form.save(commit=False)
        post.thread = thread
        post.author = request.user
        post.save()
        return redirect('lms:forum_thread', thread_id=thread.pk)

    return render(request, 'lms/forum_thread_detail.html', {
        'thread': thread, 'posts': posts, 'form': form,
        'module': module, 'course': course,
        'can_manage': can_manage_course(request.user, course),
    })



@login_required
def gradebook(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user   = request.user

    if not can_view_course(user, course):
        return HttpResponseForbidden()

    is_manager = can_manage_course(user, course)
    grade_items = course.grade_items.all()

    if is_manager:
        students = list(course.enrolments.filter(role='STUDENT', is_active=True).select_related('user'))
        student_users = [e.user for e in students]
        entries = {
            (ge.student_id, ge.grade_item_id): ge
            for ge in GradeEntry.objects.filter(grade_item__course=course)
        }
        matrix = [
            {
                'user': u,
                'grades': [entries.get((u.pk, gi.pk)) for gi in grade_items],
                'total': _calc_total(u, grade_items, entries)
            }
            for u in student_users
        ]
        ctx = {
            'course': course, 'grade_items': grade_items,
            'matrix': matrix, 'is_manager': True,
        }
    else:
        my_entries = {ge.grade_item_id: ge for ge in GradeEntry.objects.filter(
            grade_item__course=course, student=user
        )}
        ctx = {
            'course': course, 'grade_items': grade_items,
            'my_entries': my_entries, 'is_manager': False,
            'my_total': _calc_total(user, grade_items, {(user.pk, k): v for k, v in my_entries.items()}),
        }

    return render(request, 'lms/gradebook.html', ctx)


def _calc_total(user, grade_items, entries_dict):
    total_weight = sum(gi.weight for gi in grade_items if not getattr(entries_dict.get((user.pk, gi.pk)), 'is_excluded', False))
    if not total_weight:
        return None
    weighted = sum(
        (entries_dict.get((user.pk, gi.pk)).score or 0) / gi.max_score * gi.weight
        for gi in grade_items
        if entries_dict.get((user.pk, gi.pk)) and entries_dict[(user.pk, gi.pk)].score is not None
        and not entries_dict[(user.pk, gi.pk)].is_excluded
    )
    return round(weighted / total_weight * 100, 1)


@login_required
def grade_item_manage(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        return HttpResponseForbidden()
    form = GradeItemForm(request.POST or None)
    if form.is_valid():
        gi = form.save(commit=False)
        gi.course = course
        gi.save()
        messages.success(request, _("Элемент оценки добавлен"))
        return redirect('lms:gradebook', course_id=course_id)
    return render(request, 'lms/grade_item_form.html', {'form': form, 'course': course})


@login_required
def grade_entry_save(request, item_id, student_id):
    from accounts.models import User
    gi      = get_object_or_404(GradeItem, pk=item_id)
    student = get_object_or_404(User, pk=student_id)
    if not can_manage_course(request.user, gi.course):
        return HttpResponseForbidden()
    entry, _ = GradeEntry.objects.get_or_create(grade_item=gi, student=student)
    form = GradeEntryForm(request.POST or None, instance=entry)
    if form.is_valid():
        e = form.save(commit=False)
        e.graded_by = request.user
        e.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'score': e.score, 'percentage': e.percentage})
        messages.success(request, _("Оценка сохранена"))
    return redirect('lms:gradebook', course_id=gi.course_id)



@login_required
def enrolment_manage(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        return HttpResponseForbidden()

    enrolments = course.enrolments.select_related('user').order_by('role', 'user__last_name')
    form = EnrolUsersForm(request.POST or None)

    if form.is_valid():
        added = 0
        
        groups = form.cleaned_data.get('groups',[])
        for group in groups:
            students = Student.objects.filter(group=group, status='ACTIVE').select_related('user')
            for student in students:
                _, created = CourseEnrolment.objects.update_or_create(
                    course=course,
                    user=student.user,
                    defaults={'role': 'STUDENT', 'is_active': True}
                )
                if created:
                    added += 1

        teachers = form.cleaned_data.get('teachers',[])
        for teacher in teachers:
            _, created = CourseEnrolment.objects.update_or_create(
                course=course,
                user=teacher,
                defaults={'role': 'TEACHER', 'is_active': True}
            )
            if created:
                added += 1

        messages.success(request, _(f"Добавлено {added} участников"))
        return redirect('lms:enrolment_manage', course_id=course_id)

    return render(request, 'lms/enrolment_manage.html', {
        'course': course, 'enrolments': enrolments, 'form': form
    })


@login_required
def enrolment_remove(request, enrolment_id):
    enrolment = get_object_or_404(CourseEnrolment, pk=enrolment_id)
    if not can_manage_course(request.user, enrolment.course):
        return HttpResponseForbidden()
    course_id = enrolment.course_id
    enrolment.delete()
    messages.success(request, _("Участник удалён"))
    return redirect('lms:enrolment_manage', course_id=course_id)



@login_required
def folder_file_add(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id, module_type='FOLDER')
    if not can_manage_course(request.user, module.section.course):
        return HttpResponseForbidden()
    folder, _ = FolderResource.objects.get_or_create(module=module)
    form = FolderFileForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        f = form.save(commit=False)
        f.folder = folder
        f.save()
        messages.success(request, _("Файл добавлен"))
        return redirect('lms:module_detail', module_id=module_id)
    return render(request, 'lms/folder_file_form.html', {'form': form, 'module': module})


@login_required
def folder_file_delete(request, file_id):
    ff = get_object_or_404(FolderFile, pk=file_id)
    module = ff.folder.module
    if not can_manage_course(request.user, module.section.course):
        return HttpResponseForbidden()
    if request.method == 'POST':
        ff.delete()
    return redirect('lms:module_detail', module_id=module.pk)



@login_required
def glossary_entry_add(request, module_id):
    module = get_object_or_404(CourseModule, pk=module_id, module_type='GLOSSARY')
    course = module.section.course
    if not can_view_course(request.user, course):
        return HttpResponseForbidden()
    glossary, _ = Glossary.objects.get_or_create(module=module)
    form = GlossaryEntryForm(request.POST or None)
    if form.is_valid():
        entry = form.save(commit=False)
        entry.glossary = glossary
        entry.author   = request.user
        entry.save()
        return redirect('lms:module_detail', module_id=module_id)
    return render(request, 'lms/glossary_entry_form.html', {'form': form, 'module': module, 'course': course})



@login_required
@require_POST
def reorder_sections(request, course_id):
    import json as _json
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        return JsonResponse({'error': 'forbidden'}, status=403)
    data = _json.loads(request.body)
    for item in data:
        CourseSection.objects.filter(pk=item['id'], course=course).update(sequence=item['seq'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def reorder_modules(request, section_id):
    import json as _json
    section = get_object_or_404(CourseSection, pk=section_id)
    if not can_manage_course(request.user, section.course):
        return JsonResponse({'error': 'forbidden'}, status=403)
    data = _json.loads(request.body)
    for item in data:
        CourseModule.objects.filter(pk=item['id'], section=section).update(sequence=item['seq'])
    return JsonResponse({'ok': True})



@login_required
def category_list(request):
    if not is_lms_specialist(request.user):
        return HttpResponseForbidden()
    cats = CourseCategory.objects.select_related('parent', 'faculty', 'department').order_by('sort_order', 'name')
    return render(request, 'lms/category_list.html', {'categories': cats})


@login_required
def category_create(request):
    if not is_lms_specialist(request.user):
        return HttpResponseForbidden()
    form = CourseCategoryForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, _("Категория создана"))
        return redirect('lms:category_list')
    return render(request, 'lms/category_form.html', {'form': form})


@login_required
def category_edit(request, category_id):
    cat = get_object_or_404(CourseCategory, pk=category_id)
    if not is_lms_specialist(request.user):
        return HttpResponseForbidden()
    form = CourseCategoryForm(request.POST or None, instance=cat)
    if form.is_valid():
        form.save()
        messages.success(request, _("Категория обновлена"))
        return redirect('lms:category_list')
    return render(request, 'lms/category_form.html', {'form': form, 'category': cat})





@login_required
@require_POST
def sync_schedule(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        return HttpResponseForbidden()

    success, msg = LMSManager.generate_structure_from_schedule(course)
    
    if success:
        messages.success(request, msg)
    else:
        messages.error(request, msg)
        
    return redirect('lms:course_detail', course_id=course.pk)