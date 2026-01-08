from django.urls import path
from . import views

app_name = 'schedule'

urlpatterns = [
    # Просмотр расписания (единый формат)
    path('', views.schedule_view, name='view'),
    
    # Сегодняшние занятия (виджет)
    path('today/', views.today_classes, name='today'),
    
    # Экспорт расписания
    path('export/', views.export_schedule, name='export'),
    
    # ✅ ИСПРАВЛЕНО: Конструктор расписания (ОДИН URL)
    path('constructor/', views.schedule_constructor, name='constructor'),
    
    # AJAX endpoints для конструктора
    path('constructor/create/', views.create_schedule_slot, name='create_slot'),
    path('constructor/update-room/<int:slot_id>/', views.update_schedule_room, name='update_room'),
    path('constructor/delete/<int:slot_id>/', views.delete_schedule_slot, name='delete_slot'),
    
    # Управление предметами
    path('subjects/', views.manage_subjects, name='manage_subjects'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    path('subjects/<int:subject_id>/edit/', views.edit_subject, name='edit_subject'),
    path('subjects/<int:subject_id>/delete/', views.delete_subject, name='delete_subject'),
    
    # Управление семестрами
    path('semesters/', views.manage_semesters, name='manage_semesters'),
    path('semesters/add/', views.add_semester, name='add_semester'),
    path('semesters/<int:semester_id>/edit/', views.edit_semester, name='edit_semester'),
    path('semesters/<int:semester_id>/toggle/', views.toggle_semester_active, name='toggle_semester'),
    
    # Управление учебными неделями
    path('academic-week/', views.manage_academic_week, name='manage_academic_week'),
    
    # Управление кабинетами
    path('classrooms/', views.manage_classrooms, name='manage_classrooms'),
    path('classrooms/add/', views.add_classroom, name='add_classroom'),
    path('classrooms/bulk-add/', views.bulk_add_classrooms, name='bulk_add_classrooms'),
    path('classrooms/<int:classroom_id>/delete/', views.delete_classroom, name='delete_classroom'),
    
    # Список групп
    path('groups/', views.group_list, name='group_list'),
]