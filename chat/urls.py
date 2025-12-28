from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_list, name='list'),
    path('room/<int:room_id>/', views.chat_room, name='room'),
    path('start/', views.start_chat, name='start'),
    path('message/<int:message_id>/delete/', views.delete_message, name='delete_message'),
    path('room/<int:room_id>/new-messages/', views.get_new_messages, name='new_messages'),
]
