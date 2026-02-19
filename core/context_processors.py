from django.utils import timezone
from datetime import timedelta
from accounts.models import StudentOrder
from chat.models import ChatMessage
from news.models import News
from django.db.models import Q

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
        counts['orders'] = StudentOrder.objects.filter(status='DRAFT').count()

    three_days_ago = timezone.now() - timedelta(days=3)
    counts['news'] = News.objects.filter(
        is_published=True,
        created_at__gte=three_days_ago
    ).count()

    counts['total'] = counts['orders'] + counts['chat']

    return {'notification_counts': counts}