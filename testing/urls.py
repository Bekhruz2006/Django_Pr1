from django.urls import path
from . import views

app_name = 'testing'

urlpatterns = [
    path('module/<int:module_id>/', views.quiz_info, name='quiz_info'),
    path('attempt/<int:attempt_id>/', views.quiz_attempt, name='quiz_attempt'),
    path('attempt/<int:attempt_id>/submit/', views.quiz_submit, name='quiz_submit'),
    path('attempt/<int:attempt_id>/result/', views.quiz_result, name='quiz_result'),
    path('module/<int:module_id>/edit/', views.quiz_edit, name='quiz_edit'),
    path('quiz/<int:quiz_id>/question/add/', views.question_edit, name='question_add'),
    path('question/<int:question_id>/edit/', views.question_edit, name='question_edit'),
    path('question/<int:question_id>/delete/', views.question_delete, name='question_delete'),
]