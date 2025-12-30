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

    path('slot/<int:slot_id>/exceptions/', views.manage_exceptions, name='manage_exceptions'),
    path('exception/<int:exception_id>/delete/', views.delete_exception, name='delete_exception'),

    path('academic-week/', views.manage_academic_week, name='manage_academic_week'),

    path('groups/', views.group_list, name='group_list'),
]