from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from .models import Quiz, Question, AnswerOption, QuizAttempt, AttemptResponse
from lms.models import CourseModule
from .forms import QuizForm, QuestionForm, AnswerOptionFormSet

@login_required
def quiz_info(request, module_id):
    module = get_object_or_404(CourseModule, id=module_id)
    quiz = get_object_or_404(Quiz, module=module)

    attempts = QuizAttempt.objects.filter(quiz=quiz, user=request.user).order_by('-start_time')

    if request.method == 'POST':
        if quiz.max_attempts > 0 and attempts.count() >= quiz.max_attempts:
            return render(request, 'core/error.html', {'message': 'Вы исчерпали лимит попыток.'})

        attempt = QuizAttempt.objects.create(
            quiz=quiz,
            user=request.user,
            state='IN_PROGRESS'
        )
        return redirect('testing:quiz_attempt', attempt_id=attempt.id)

    return render(request, 'testing/quiz_info.html', {
        'module': module,
        'quiz': quiz,
        'attempts': attempts
    })

@login_required
def quiz_attempt(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)

    if attempt.state != 'IN_PROGRESS':
        return redirect('testing:quiz_result', attempt_id=attempt.id)

    quiz = attempt.quiz

    if quiz.time_limit_minutes > 0:
        time_elapsed = (timezone.now() - attempt.start_time).total_seconds() / 60
        if time_elapsed > quiz.time_limit_minutes:
            return redirect('testing:quiz_submit', attempt_id=attempt.id) # Авто-сабмит

    questions = quiz.questions.prefetch_related('options').all()
    if quiz.shuffle_questions:
        questions = list(questions)
        import random
        random.shuffle(questions)

    return render(request, 'testing/quiz_attempt.html', {
        'attempt': attempt,
        'quiz': quiz,
        'questions': questions
    })

@login_required
def quiz_submit(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)

    if attempt.state != 'IN_PROGRESS':
        return redirect('testing:quiz_result', attempt_id=attempt.id)

    if request.method == 'POST':
        total_score = 0
        questions = attempt.quiz.questions.all()

        for q in questions:
            if q.q_type in ['SINGLE', 'MULTI']:
                selected_option_ids = request.POST.getlist(f'question_{q.id}')
                options = AnswerOption.objects.filter(id__in=selected_option_ids)

                q_score = sum([opt.fraction * q.default_mark for opt in options])
                q_score = max(0, q_score)
                total_score += q_score

                resp = AttemptResponse.objects.create(
                    attempt=attempt, question=q, earned_mark=q_score
                )
                resp.selected_options.set(options)

            elif q.q_type in ['TEXT', 'ESSAY']:
                text_ans = request.POST.get(f'question_{q.id}', '')
                AttemptResponse.objects.create(
                    attempt=attempt, question=q, text_answer=text_ans, earned_mark=0
                )
                if q.q_type == 'ESSAY':
                    attempt.state = 'NEEDS_GRADING'

        attempt.total_score = total_score
        if attempt.state != 'NEEDS_GRADING':
            attempt.state = 'FINISHED'
            attempt.is_passed = (total_score >= attempt.quiz.passing_score)

        attempt.end_time = timezone.now()
        attempt.save()

        return redirect('testing:quiz_result', attempt_id=attempt.id)

    return redirect('testing:quiz_attempt', attempt_id=attempt.id)

@login_required
def quiz_result(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    return render(request, 'testing/quiz_result.html', {'attempt': attempt})

@login_required
def quiz_edit(request, module_id):
    module = get_object_or_404(CourseModule, id=module_id)
    quiz, created = Quiz.objects.get_or_create(module=module, defaults={'description': 'Новый тест'})
    
    if request.method == 'POST':
        from .forms import QuizForm 
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            messages.success(request, 'Настройки теста сохранены')
            return redirect('testing:quiz_edit', module_id=module.id)
    else:
        from .forms import QuizForm
        form = QuizForm(instance=quiz)
        
    questions = quiz.questions.all()
    return render(request, 'testing/quiz_edit.html', {'module': module, 'quiz': quiz, 'form': form, 'questions': questions})

@login_required
def question_edit(request, quiz_id=None, question_id=None):
    if question_id:
        question = get_object_or_404(Question, id=question_id)
        quiz = question.quiz
    else:
        quiz = get_object_or_404(Quiz, id=quiz_id)
        question = Question(quiz=quiz)

    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question)
        formset = AnswerOptionFormSet(request.POST, instance=question)
        if form.is_valid() and formset.is_valid():
            q = form.save()
            formset.instance = q
            formset.save()
            messages.success(request, 'Вопрос сохранен')
            return redirect('testing:quiz_edit', module_id=quiz.module.id)
    else:
        form = QuestionForm(instance=question)
        formset = AnswerOptionFormSet(instance=question)

    return render(request, 'testing/question_form.html', {'form': form, 'formset': formset, 'quiz': quiz})

@login_required
def question_delete(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    quiz_module_id = question.quiz.module.id
    question.delete()
    messages.success(request, 'Вопрос удален')
    return redirect('testing:quiz_edit', module_id=quiz_module_id)
