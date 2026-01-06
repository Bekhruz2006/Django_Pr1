from django.urls import path
from . import views

app_name = 'schedule'

urlpatterns = [
    path('', views.schedule_view, name='view'),
    path('today/', views.today_classes, name='today'),
    path('export/', views.export_schedule, name='export'),
    
    path('constructor/', views.schedule_constructor, name='constructor'),
    path('slot/add/', views.add_schedule_slot, name='add_slot'),
    path('slot/<int:slot_id>/edit/', views.edit_schedule_slot, name='edit_slot'),
    path('slot/<int:slot_id>/delete/', views.delete_schedule_slot, name='delete_slot'),
    path('slot/check-conflicts/', views.check_slot_conflicts, name='check_conflicts'),
    
    path('slot/<int:slot_id>/exceptions/', views.manage_exceptions, name='manage_exceptions'),
    path('exception/<int:exception_id>/delete/', views.delete_exception, name='delete_exception'),
    
    path('subjects/', views.manage_subjects, name='manage_subjects'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    path('subjects/<int:subject_id>/edit/', views.edit_subject, name='edit_subject'),
    path('subjects/<int:subject_id>/delete/', views.delete_subject, name='delete_subject'),
    
    path('semesters/', views.manage_semesters, name='manage_semesters'),
    path('semesters/add/', views.add_semester, name='add_semester'),
    path('semesters/<int:semester_id>/edit/', views.edit_semester, name='edit_semester'),
    path('semesters/<int:semester_id>/toggle/', views.toggle_semester_active, name='toggle_semester'),
    
    path('classrooms/', views.manage_classrooms, name='manage_classrooms'),
    path('classrooms/add/', views.add_classroom, name='add_classroom'),
    path('classrooms/bulk-add/', views.bulk_add_classrooms, name='bulk_add_classrooms'),
    path('classrooms/<int:classroom_id>/delete/', views.delete_classroom, name='delete_classroom'),
    
    path('groups/', views.group_list, name='group_list'),
]