from django.urls import path
from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('', views.chat_view, name='chat'),  
    path('api/', views.chat_api, name='api'),
]