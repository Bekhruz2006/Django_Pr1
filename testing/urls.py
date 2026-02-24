from django.urls import path
from . import views

app_name = 'testing'

urlpatterns = [
    path('module/<int:module_id>/', views.quiz_info, name='quiz_info'),
    path('attempt/<int:attempt_id>/', views.quiz_attempt, name='quiz_attempt'),
    path('attempt/<int:attempt_id>/submit/', views.quiz_submit, name='quiz_submit'),
    path('attempt/<int:attempt_id>/result/', views.quiz_result, name='quiz_result'),
]