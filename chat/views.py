from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Max
from django.http import JsonResponse
from accounts.models import User
from .models import ChatRoom, ChatMessage
from .forms import ChatMessageForm

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
    
    return render(request, 'chat/chat_list.html', {
        'rooms': rooms,
    })

@login_required
def chat_room(request, room_id):
    
    room = get_object_or_404(ChatRoom, id=room_id, participants=request.user)

    messages_list = room.messages.select_related('sender').order_by('created_at')

    room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    if request.method == 'POST':
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.room = room
            message.sender = request.user
            message.save()

            room.save()
            
            return redirect('chat:room', room_id=room_id)
    else:
        form = ChatMessageForm()

    other_participants = room.participants.exclude(id=request.user.id)
    
    return render(request, 'chat/chat_room.html', {
        'room': room,
        'messages': messages_list,
        'form': form,
        'other_participants': other_participants,
    })

@login_required
def start_chat(request):
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        recipient = get_object_or_404(User, id=user_id)

        existing_room = ChatRoom.objects.filter(
            room_type='PRIVATE',
            participants=request.user
        ).filter(
            participants=recipient
        ).first()
        
        if existing_room:
            return redirect('chat:room', room_id=existing_room.id)

        room = ChatRoom.objects.create(room_type='PRIVATE')
        room.participants.add(request.user, recipient)
        
        messages.success(request, f'Чат с {recipient.get_full_name()} создан')
        return redirect('chat:room', room_id=room.id)

    users = User.objects.exclude(id=request.user.id).select_related(
        'student_profile', 'teacher_profile', 'dean_profile'
    )
    
    return render(request, 'chat/start_chat.html', {
        'users': users,
    })

@login_required
def delete_message(request, message_id):
    
    message = get_object_or_404(ChatMessage, id=message_id, sender=request.user)
    room_id = message.room.id
    message.delete()
    messages.success(request, 'Сообщение удалено')
    return redirect('chat:room', room_id=room_id)

@login_required
def get_new_messages(request, room_id):
    
    room = get_object_or_404(ChatRoom, id=room_id, participants=request.user)
    last_message_id = request.GET.get('last_id', 0)
    
    new_messages = room.messages.filter(
        id__gt=last_message_id
    ).select_related('sender').order_by('created_at')
    
    messages_data = []
    for msg in new_messages:
        messages_data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'sender_name': msg.sender.get_full_name(),
            'content': msg.content,
            'created_at': msg.created_at.strftime('%H:%M'),
            'is_mine': msg.sender == request.user,
        })
    
    return JsonResponse({'messages': messages_data})