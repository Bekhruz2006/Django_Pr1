from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from datetime import datetime
from django.db.models import Avg, Count
from .models import News

from .models import ChatRoom, ChatMessage
from django.db.models import Q



def is_dean(user):
    return user.is_authenticated and user.role == 'DEAN'

@login_required
def home(request):
    """Р“Р»Р°РІРЅР°СЏ СЃС‚СЂР°РЅРёС†Р° СЃ РЅРѕРІРѕСЃС‚СЏРјРё РґР»СЏ РІСЃРµС… СЂРѕР»РµР№"""
    
    # РџРѕР»СѓС‡Р°РµРј РЅРѕРІРѕСЃС‚Рё
    news_list = News.objects.filter(is_published=True)[:10]
    
    # РЎС‚Р°С‚РёСЃС‚РёРєР° РґР»СЏ Р±С‹СЃС‚СЂРѕРіРѕ РґРѕСЃС‚СѓРїР°
    context = {
        'news_list': news_list,
        'user': request.user,
    }
    
    # Р”РѕР±Р°РІР»СЏРµРј СЃРїРµС†РёС„РёС‡РЅС‹Рµ РґР»СЏ СЂРѕР»Рё РґР°РЅРЅС‹Рµ
    if request.user.role == 'STUDENT':
        context['profile'] = request.user.student_profile
        
    elif request.user.role == 'TEACHER':
        context['profile'] = request.user.teacher_profile
        
    elif request.user.role == 'DEAN':
        context['profile'] = request.user.dean_profile
        
        # РњРёРЅРё-СЃС‚Р°С‚РёСЃС‚РёРєР° РґР»СЏ РґРµРєР°РЅР°
        from accounts.models import Student, Teacher, Group
        context['total_students'] = Student.objects.count()
        context['total_teachers'] = Teacher.objects.count()
        context['total_groups'] = Group.objects.count()
    
    return render(request, 'core/home.html', context)


@login_required
def dashboard(request):
    """Р”Р°С€Р±РѕСЂРґС‹ РїРѕ СЂРѕР»СЏРј (СЃС‚Р°СЂР°СЏ Р»РѕРіРёРєР°)"""
    user = request.user
    
    template_map = {
        'STUDENT': 'core/dashboard_student.html',
        'TEACHER': 'core/dashboard_teacher.html',
        'DEAN': 'core/dashboard_dean.html',
    }
    
    template = template_map.get(user.role, 'core/dashboard.html')
    
    context = {
        'user': user
    }
    
    if user.role == 'STUDENT':
        context['profile'] = user.student_profile
    elif user.role == 'TEACHER':
        context['profile'] = user.teacher_profile
    elif user.role == 'DEAN':
        context['profile'] = user.dean_profile
        
        # РЎС‚Р°С‚РёСЃС‚РёРєР° РґР»СЏ РґРµРєР°РЅР°
        from accounts.models import Student, Teacher, Group
        from journal.models import StudentStatistics
        
        # РћР±С‰РёРµ СЃС‡РµС‚С‡РёРєРё
        context['total_students'] = Student.objects.count()
        context['total_teachers'] = Teacher.objects.count()
        context['total_groups'] = Group.objects.count()
        
        # РЎСЂРµРґРЅРёР№ Р±Р°Р»Р» РїРѕ РІСЃРµРј СЃС‚СѓРґРµРЅС‚Р°Рј
        all_stats = StudentStatistics.objects.all()
        if all_stats.exists():
            context['avg_gpa'] = all_stats.aggregate(Avg('overall_gpa'))['overall_gpa__avg']
        else:
            context['avg_gpa'] = 0
        
        # РЎС‚Р°С‚РёСЃС‚РёРєР° РїРѕ РєСѓСЂСЃР°Рј
        course_stats = []
        for course_num in range(1, 6):
            groups = Group.objects.filter(course=course_num)
            students = Student.objects.filter(group__course=course_num)
            
            if students.exists():
                stats = StudentStatistics.objects.filter(student__in=students)
                course_stats.append({
                    'course': course_num,
                    'groups_count': groups.count(),
                    'students_count': students.count(),
                    'avg_gpa': stats.aggregate(Avg('overall_gpa'))['overall_gpa__avg'] or 0,
                    'avg_attendance': stats.aggregate(Avg('attendance_percentage'))['attendance_percentage__avg'] or 0,
                })
        
        context['course_stats'] = course_stats
    
    # Р”РѕР±Р°РІР»СЏРµРј РґР°РЅРЅС‹Рµ РґР»СЏ РІРёРґР¶РµС‚Р° "РЎРµРіРѕРґРЅСЏ"
    try:
        from schedule.models import ScheduleSlot
        from accounts.models import Student, Teacher
        
        today = datetime.now()
        day_of_week = today.weekday()
        current_time = today.time()
        
        classes = []
        
        if user.role == 'STUDENT':
            try:
                student = user.student_profile
                if student.group:
                    classes = ScheduleSlot.objects.filter(
                        group=student.group,
                        day_of_week=day_of_week,
                        is_active=True
                    ).select_related('subject', 'teacher').order_by('start_time')
            except Student.DoesNotExist:
                pass
        
        elif user.role == 'TEACHER':
            try:
                teacher = user.teacher_profile
                classes = ScheduleSlot.objects.filter(
                    teacher=teacher,
                    day_of_week=day_of_week,
                    is_active=True
                ).select_related('subject', 'group').order_by('start_time')
            except Teacher.DoesNotExist:
                pass
        
        context['classes'] = classes
        context['current_time'] = current_time
        context['today'] = today
        
    except Exception as e:
        context['classes'] = []
        context['current_time'] = datetime.now().time()
        context['today'] = datetime.now()
    
    return render(request, template, context)


@login_required
def news_detail(request, news_id):
    """Р”РµС‚Р°Р»СЊРЅС‹Р№ РїСЂРѕСЃРјРѕС‚СЂ РЅРѕРІРѕСЃС‚Рё"""
    news = get_object_or_404(News, id=news_id, is_published=True)
    news.increment_views()
    
    return render(request, 'core/news_detail.html', {
        'news': news
    })


@login_required
@user_passes_test(is_dean)
def news_management(request):
    """РЈРїСЂР°РІР»РµРЅРёРµ РЅРѕРІРѕСЃС‚СЏРјРё (С‚РѕР»СЊРєРѕ РґРµРєР°РЅ)"""
    news_list = News.objects.all()
    
    return render(request, 'core/news_management.html', {
        'news_list': news_list
    })


@login_required
@user_passes_test(is_dean)
def add_news(request):
    """Р”РѕР±Р°РІР»РµРЅРёРµ РЅРѕРІРѕСЃС‚Рё"""
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        category = request.POST.get('category')
        is_pinned = request.POST.get('is_pinned') == 'on'
        image = request.FILES.get('image')
        
        news = News.objects.create(
            title=title,
            content=content,
            category=category,
            is_pinned=is_pinned,
            image=image,
            created_by=request.user
        )
        
        messages.success(request, 'РќРѕРІРѕСЃС‚СЊ СѓСЃРїРµС€РЅРѕ РґРѕР±Р°РІР»РµРЅР°')
        return redirect('core:news_management')
    
    return render(request, 'core/add_news.html', {
        'categories': News.CATEGORY_CHOICES
    })


@login_required
@user_passes_test(is_dean)
def edit_news(request, news_id):
    """Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ РЅРѕРІРѕСЃС‚Рё"""
    news = get_object_or_404(News, id=news_id)
    
    if request.method == 'POST':
        news.title = request.POST.get('title')
        news.content = request.POST.get('content')
        news.category = request.POST.get('category')
        news.is_pinned = request.POST.get('is_pinned') == 'on'
        
        if 'image' in request.FILES:
            news.image = request.FILES['image']
        
        news.save()
        
        messages.success(request, 'РќРѕРІРѕСЃС‚СЊ РѕР±РЅРѕРІР»РµРЅР°')
        return redirect('core:news_management')
    
    return render(request, 'core/edit_news.html', {
        'news': news,
        'categories': News.CATEGORY_CHOICES
    })


@login_required
@user_passes_test(is_dean)
def delete_news(request, news_id):
    """РЈРґР°Р»РµРЅРёРµ РЅРѕРІРѕСЃС‚Рё"""
    news = get_object_or_404(News, id=news_id)
    news.delete()
    messages.success(request, 'РќРѕРІРѕСЃС‚СЊ СѓРґР°Р»РµРЅР°')
    return redirect('core:news_management')






@login_required
def chat_list(request):
    """РЎРїРёСЃРѕРє С‡Р°С‚РѕРІ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ"""
    
    # РџРѕР»СѓС‡Р°РµРј РІСЃРµ С‡Р°С‚С‹, РіРґРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓС‡Р°СЃС‚РЅРёРє
    chats = ChatRoom.objects.filter(
        participants=request.user
    ).prefetch_related('messages', 'participants')
    
    return render(request, 'core/chat_list.html', {
        'chats': chats
    })



@login_required
def chat_room(request, room_id):
    """РљРѕРЅРєСЂРµС‚РЅР°СЏ РєРѕРјРЅР°С‚Р° С‡Р°С‚Р°"""
    
    room = get_object_or_404(ChatRoom, id=room_id)
    
    # РџСЂРѕРІРµСЂРєР° РїСЂР°РІ РґРѕСЃС‚СѓРїР°
    if request.user not in room.participants.all():
        messages.error(request, 'РЈ РІР°СЃ РЅРµС‚ РґРѕСЃС‚СѓРїР° Рє СЌС‚РѕРјСѓ С‡Р°С‚Сѓ')
        return redirect('core:chat_list')
    
    # РћС‚РїСЂР°РІРєР° СЃРѕРѕР±С‰РµРЅРёСЏ
    if request.method == 'POST':
        message_text = request.POST.get('message')
        file = request.FILES.get('file')
        
        if message_text or file:
            ChatMessage.objects.create(
                room=room,
                sender=request.user,
                message=message_text or '',
                file=file
            )
            return redirect('core:chat_room', room_id=room_id)
    
    # РџРѕР»СѓС‡Р°РµРј СЃРѕРѕР±С‰РµРЅРёСЏ
    messages_list = room.messages.select_related('sender').order_by('created_at')
    
    # РћС‚РјРµС‡Р°РµРј РєР°Рє РїСЂРѕС‡РёС‚Р°РЅРЅС‹Рµ
    messages_list.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    
    return render(request, 'core/chat_room.html', {
        'room': room,
        'messages_list': messages_list
    })


@login_required
def start_chat(request, user_id):
    """РќР°С‡Р°С‚СЊ Р»РёС‡РЅС‹Р№ С‡Р°С‚ СЃ РїРѕР»СЊР·РѕРІР°С‚РµР»РµРј"""
    
    other_user = get_object_or_404(User, id=user_id)
    
    # РџСЂРѕРІРµСЂСЏРµРј, СЃСѓС‰РµСЃС‚РІСѓРµС‚ Р»Рё СѓР¶Рµ С‡Р°С‚ РјРµР¶РґСѓ СЌС‚РёРјРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏРјРё
    existing_room = ChatRoom.objects.filter(
        room_type='PERSONAL'
    ).filter(
        Q(user1=request.user, user2=other_user) |
        Q(user1=other_user, user2=request.user)
    ).first()
    
    if existing_room:
        return redirect('core:chat_room', room_id=existing_room.id)
    
    # РЎРѕР·РґР°РµРј РЅРѕРІС‹Р№ С‡Р°С‚
    room = ChatRoom.objects.create(
        name=f"Р§Р°С‚: {request.user.get_full_name()} - {other_user.get_full_name()}",
        room_type='PERSONAL',
        user1=request.user,
        user2=other_user,
        created_by=request.user
    )
    room.participants.add(request.user, other_user)
    
    return redirect('core:chat_room', room_id=room.id)