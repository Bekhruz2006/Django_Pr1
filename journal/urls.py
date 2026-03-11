from django.urls import path
from . import views

app_name = 'journal'

urlpatterns = [
    
    path('', views.journal_view, name='journal_view'),
    path('entry/<int:entry_id>/update/', views.update_entry, name='update_entry'),
    path('bulk-update/', views.bulk_update, name='bulk_update'),
    path('changelog/', views.change_log_view, name='change_log'),

    path('student/', views.student_journal_view, name='student_view'),
    path('api/update-cell/', views.update_journal_cell, name='update_journal_cell'),
    path('dean/', views.dean_journal_view, name='dean_view'),
    path('report/', views.department_report, name='department_report'),  
    path('report/group/<int:group_id>/', views.group_detailed_report, name='group_detail'),  
    path('performance/', views.performance_journal_view, name='performance_journal'),
    path('api/update-matrix/', views.update_matrix_cell, name='update_matrix_cell'),
    path('api/update-weekly-score/', views.update_weekly_score, name='update_weekly_score'),
    path('matrix-constructor/', views.matrix_constructor, name='matrix_constructor'),
    path('api/student-trend/<int:student_id>/', views.api_student_trend, name='api_student_trend'),
]