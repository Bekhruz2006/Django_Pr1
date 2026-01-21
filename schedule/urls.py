from django.urls import path
from . import views

app_name = 'schedule'

urlpatterns = [
    path('', views.schedule_view, name='view'),
    
    path('today/', views.today_classes, name='today'),
    
    path('export/', views.export_schedule, name='export'),
    
    path('constructor/', views.schedule_constructor, name='constructor'),
    
    path('constructor/create/', views.create_schedule_slot, name='create_slot'),
    path('constructor/update-room/<int:slot_id>/', views.update_schedule_room, name='update_room'),
    path('constructor/delete/<int:slot_id>/', views.delete_schedule_slot, name='delete_slot'),
    
    path('subjects/', views.manage_subjects, name='manage_subjects'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    path('subjects/<int:subject_id>/edit/', views.edit_subject, name='edit_subject'),
    path('subjects/<int:subject_id>/delete/', views.delete_subject, name='delete_subject'),
    
    path('semesters/', views.manage_semesters, name='manage_semesters'),
    path('semesters/add/', views.add_semester, name='add_semester'),
    path('semesters/<int:semester_id>/edit/', views.edit_semester, name='edit_semester'),
    path('semesters/<int:semester_id>/toggle/', views.toggle_semester_active, name='toggle_semester'),
    
    path('academic-week/', views.manage_academic_week, name='manage_academic_week'),
    
    path('classrooms/', views.manage_classrooms, name='manage_classrooms'),
    path('classrooms/add/', views.add_classroom, name='add_classroom'),
    path('classrooms/bulk-add/', views.bulk_add_classrooms, name='bulk_add_classrooms'),
    path('classrooms/<int:classroom_id>/delete/', views.delete_classroom, name='delete_classroom'),
    
    path('groups/', views.group_list, name='group_list'),
    
    path('import/', views.import_schedule_view, name='import_schedule'),
    
    path('plans/', views.manage_plans, name='manage_plans'),
    path('plans/create/', views.create_plan, name='create_plan'),
    path('plans/<int:plan_id>/', views.plan_detail, name='plan_detail'),
    path('plans/generate/', views.generate_subjects_from_rup, name='generate_subjects'),
]