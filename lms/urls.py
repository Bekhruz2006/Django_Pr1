from django.urls import path
from . import views

app_name = 'lms'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('courses/', views.course_list, name='course_list'),

    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:category_id>/edit/', views.category_edit, name='category_edit'),
    path('modules/<int:module_id>/toggle-visibility/', views.module_toggle_visibility, name='module_toggle_visibility'),

    path('courses/create/', views.course_create, name='course_create'),
    path('courses/<int:course_id>/', views.course_detail, name='course_detail'),
    path('courses/<int:course_id>/edit/', views.course_edit, name='course_edit'),
    path('courses/<int:course_id>/delete/', views.course_delete, name='course_delete'),

    path('courses/<int:course_id>/sections/create/', views.section_create, name='section_create'),
    path('sections/<int:section_id>/edit/', views.section_edit, name='section_edit'),
    path('sections/<int:section_id>/delete/', views.section_delete, name='section_delete'),

    path('sections/<int:section_id>/modules/create/', views.module_create, name='module_create'),
    path('modules/<int:module_id>/', views.module_detail, name='module_detail'),
    path('modules/<int:module_id>/edit/', views.module_edit, name='module_edit'),
    path('modules/<int:module_id>/delete/', views.module_delete, name='module_delete'),

    path('modules/<int:module_id>/submit/', views.assignment_submit, name='assignment_submit'),
    path('submissions/<int:submission_id>/grade/', views.assignment_grade, name='assignment_grade'),

    path('modules/<int:module_id>/forum/thread/create/', views.forum_thread_create, name='forum_thread_create'),
    path('forum/threads/<int:thread_id>/', views.forum_thread_detail, name='forum_thread'),

    path('modules/<int:module_id>/glossary/add/', views.glossary_entry_add, name='glossary_entry_add'),

    path('modules/<int:module_id>/folder/add/', views.folder_file_add, name='folder_file_add'),
    path('folder-files/<int:file_id>/delete/', views.folder_file_delete, name='folder_file_delete'),

    path('courses/<int:course_id>/gradebook/', views.gradebook, name='gradebook'),
    path('courses/<int:course_id>/grades/add/', views.grade_item_manage, name='grade_item_manage'),
    path('grades/<int:item_id>/student/<int:student_id>/save/', views.grade_entry_save, name='grade_entry_save'),

    path('courses/<int:course_id>/enrolments/', views.enrolment_manage, name='enrolment_manage'),
    path('enrolments/<int:enrolment_id>/remove/', views.enrolment_remove, name='enrolment_remove'),

    path('courses/<int:course_id>/reorder-sections/', views.reorder_sections, name='reorder_sections'),
    path('sections/<int:section_id>/reorder-modules/', views.reorder_modules, name='reorder_modules'),
    path('courses/<int:course_id>/sync-schedule/', views.sync_schedule, name='sync_schedule'),
]