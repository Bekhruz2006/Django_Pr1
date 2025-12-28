from django.urls import path
from . import views

app_name = 'journal'

urlpatterns = [
    # Преподаватель
    path('', views.journal_view, name='journal_view'),
    path('entry/<int:entry_id>/update/', views.update_entry, name='update_entry'),
    path('bulk-update/', views.bulk_update, name='bulk_update'),
    path('changelog/', views.change_log_view, name='change_log'),
    
    # Студент
    path('student/', views.student_journal_view, name='student_view'),
    
    # Декан
    path('dean/', views.dean_journal_view, name='dean_view'),
    path('report/', views.department_report, name='department_report'),  # ДОБАВЛЕНО
    path('report/group/<int:group_id>/', views.group_detailed_report, name='group_detail'),  # ДОБАВЛЕНО
]