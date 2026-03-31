from django.utils import timezone
from datetime import timedelta
from accounts.models import Order
from chat.models import ChatMessage
from news.models import News
from django.db.models import Q
from django.utils.translation import gettext as _


def academic_context(request):
    d = timezone.now().date()
    m, y = d.month, d.year
    if m >= 9:
        ay = f"{y}-{y + 1}"
        term = _("1-е полугодие %(years)s") % {"years": ay}
    elif m == 1:
        ay = f"{y - 1}-{y}"
        term = _("1-е полугодие %(years)s") % {"years": ay}
    else:
        ay = f"{y - 1}-{y}"
        term = _("2-е полугодие %(years)s") % {"years": ay}
        
    context = {"current_date": d, "current_term": term}
    
    if request.user.is_authenticated and hasattr(request.user, 'student_profile'):
        from schedule.models import Semester
        sem = Semester.get_current()
        if sem and sem.start_date:
            days_passed = (d - sem.start_date).days
            current_week = (days_passed // 7) + 1
            
            target = None
            days_left = 0
            
            if current_week <= 8:
                target_date = sem.start_date + timedelta(weeks=7)
                days_left = (target_date - d).days
                target = _("Рейтинга 1")
            elif current_week <= 16:
                target_date = sem.start_date + timedelta(weeks=15)
                days_left = (target_date - d).days
                target = _("Рейтинга 2")
            elif current_week <= 18:
                target_date = sem.start_date + timedelta(weeks=16)
                days_left = (target_date - d).days
                target = _("Экзаменационной сессии")
                
            if target and 0 <= days_left <= 14:
                context['rating_banner'] = {
                    'target': target,
                    'days_left': days_left,
                    'urgent': days_left <= 3
                }
                
    return context


def global_notifications(request):
    if not request.user.is_authenticated:
        return {}

    counts = {
        'orders': 0,
        'chat': 0,
        'news': 0,
        'total': 0
    }

    user = request.user
    counts['chat'] = ChatMessage.objects.filter(
        room__participants=user,
        is_read=False
    ).exclude(sender=user).count()

    if user.is_superuser or user.role in ['RECTOR', 'PRO_RECTOR', 'DIRECTOR']:
        counts['orders'] = Order.objects.filter(status='DRAFT').count()

    three_days_ago = timezone.now() - timedelta(days=3)
    counts['news'] = News.objects.filter(
        is_published=True,
        created_at__gte=three_days_ago
    ).count()

    counts['total'] = counts['orders'] + counts['chat']

    return {'notification_counts': counts}