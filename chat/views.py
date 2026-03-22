from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Max
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from accounts.models import User
from .models import ChatRoom, ChatMessage
import mimetypes

@login_required
def chat_list(request):
    rooms = ChatRoom.objects.filter(
        participants=request.user
    ).annotate(
        last_message_time=Max('messages__created_at')
    ).order_by('-last_message_time')

    for room in rooms:
        room.unread = room.get_unread_count(request.user)
        room.last_msg = room.get_last_message()
        room.other = room.participants.exclude(id=request.user.id).first()

    return render(request, 'chat/chat_list.html', {'rooms': rooms})


@login_required
def chat_room(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id, participants=request.user)
    messages_list = room.messages.select_related('sender').order_by('created_at')
    room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    other_participants = room.participants.exclude(id=request.user.id)

    return render(request, 'chat/chat_room.html', {
        'room': room,
        'messages': messages_list,
        'other_participants': other_participants,
    })


@login_required
@require_POST
def send_message(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id, participants=request.user)
    content = request.POST.get('content', '').strip()
    file = request.FILES.get('file')

    if not content and not file:
        return JsonResponse({'error': 'empty'}, status=400)

    msg = ChatMessage(room=room, sender=request.user, content=content)

    if file:
        msg.file = file
        msg.file_name = file.name
        msg.file_type = file.content_type or mimetypes.guess_type(file.name)[0] or ''

    msg.save()
    room.save()

    data = {
        'id': msg.id,
        'sender_id': request.user.id,
        'sender_name': request.user.get_full_name(),
        'sender_initials': (request.user.first_name[:1] + request.user.last_name[:1]).upper(),
        'content': msg.content,
        'created_at': msg.created_at.strftime('%H:%M'),
        'is_mine': True,
        'has_file': bool(msg.file),
        'file_url': msg.file.url if msg.file else None,
        'file_name': msg.file_name,
        'file_type': msg.file_type,
        'is_image': msg.is_image() if msg.file else False,
    }
    return JsonResponse({'message': data})


@login_required
def start_chat(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        recipient = get_object_or_404(User, id=user_id)

        existing_room = ChatRoom.objects.filter(
            room_type='PRIVATE', participants=request.user
        ).filter(participants=recipient).first()

        if existing_room:
            return redirect('chat:room', room_id=existing_room.id)

        room = ChatRoom.objects.create(room_type='PRIVATE')
        room.participants.add(request.user, recipient)
        return redirect('chat:room', room_id=room.id)

    users = User.objects.exclude(id=request.user.id).select_related(
        'student_profile', 'teacher_profile', 'dean_profile'
    ).order_by('last_name', 'first_name')

    return render(request, 'chat/start_chat.html', {'users': users})


@login_required
def delete_message(request, message_id):
    message = get_object_or_404(ChatMessage, id=message_id, sender=request.user)
    room_id = message.room.id
    if message.file:
        message.file.delete(save=False)
    message.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('chat:room', room_id=room_id)


@login_required
def get_new_messages(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id, participants=request.user)
    last_id = request.GET.get('last_id', 0)

    new_msgs = room.messages.filter(id__gt=last_id).select_related('sender').order_by('created_at')

    new_msgs.exclude(sender=request.user).update(is_read=True)

    read_ids = list(
        room.messages.filter(sender=request.user, is_read=True)
        .values_list('id', flat=True)
    )

    data = []
    for msg in new_msgs:
        data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'sender_name': msg.sender.get_full_name(),
            'sender_initials': (msg.sender.first_name[:1] + msg.sender.last_name[:1]).upper(),
            'content': msg.content,
            'created_at': msg.created_at.strftime('%H:%M'),
            'is_mine': msg.sender == request.user,
            'has_file': bool(msg.file),
            'file_url': msg.file.url if msg.file else None,
            'file_name': msg.file_name,
            'file_type': msg.file_type,
            'is_image': msg.is_image() if msg.file else False,
        })

    return JsonResponse({'messages': data, 'read_ids': read_ids})


@login_required
@require_POST
def mark_read_api(request, room_id):
    import json
    room = get_object_or_404(ChatRoom, id=room_id, participants=request.user)
    try:
        body = json.loads(request.body)
        ids  = body.get('ids', [])
        if ids:
            room.messages.filter(id__in=ids).exclude(sender=request.user).update(is_read=True)
        else:
            room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    except Exception:
        room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    return JsonResponse({'status': 'ok'})


@login_required
def get_unread_count(request):
    from .models import ChatMessage
    count = ChatMessage.objects.filter(
        room__participants=request.user,
        is_read=False
    ).exclude(sender=request.user).count()
    return JsonResponse({'count': count})