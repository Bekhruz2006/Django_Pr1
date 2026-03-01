from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('password/change/', views.change_password, name='change_password'),

    path('management/', views.user_management, name='user_management'),
    path('management/add/', views.add_user, name='add_user'),
    path('management/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('management/reset-password/<int:user_id>/', views.reset_password, name='reset_password'),
    path('management/toggle-active/<int:user_id>/', views.toggle_user_active, name='toggle_user_active'),
    path('management/transfer/<int:student_id>/', views.transfer_student, name='transfer_student'),
    path('groups/<int:group_id>/view/', views.view_group, name='view_group'),
    path('groups/', views.group_management, name='group_management'),
    path('groups/add/', views.add_group, name='add_group'),
    path('groups/edit/<int:group_id>/', views.edit_group, name='edit_group'),
    path('groups/delete/<int:group_id>/', views.delete_group, name='delete_group'),
    path('profile/view/<int:user_id>/', views.view_user_profile, name='view_user_profile'),

    path('structure/', views.manage_structure, name='manage_structure'),
    
    path('management/import/', views.import_students, name='import_students'),


    path('structure/institute/add/', views.add_institute, name='add_institute'),
    path('structure/institute/edit/<int:pk>/', views.edit_institute, name='edit_institute'),
    path('structure/institute/delete/<int:pk>/', views.delete_institute, name='delete_institute'),
    
    path('structure/faculty/add/', views.add_faculty, name='add_faculty'),
    path('structure/faculty/edit/<int:pk>/', views.edit_faculty, name='edit_faculty'),
    path('structure/faculty/delete/<int:pk>/', views.delete_faculty, name='delete_faculty'),
    
    path('structure/department/add/', views.add_department, name='add_department'),
    path('structure/department/edit/<int:pk>/', views.edit_department, name='edit_department'),
    path('structure/department/delete/<int:pk>/', views.delete_department, name='delete_department'),
    
    path('structure/specialty/add/', views.add_specialty, name='add_specialty'),
    path('structure/specialty/edit/<int:pk>/', views.edit_specialty, name='edit_specialty'),
    path('structure/specialty/delete/<int:pk>/', views.delete_specialty, name='delete_specialty'),
    path('payment/', views.payment_list, name='payment_list'),
    path('student/<int:student_id>/orders/', views.student_orders, name='student_orders'),
    path('orders/all/', views.all_orders_list, name='all_orders'),
    path('orders/approve/<int:order_id>/', views.approve_order, name='approve_order'),
    path('management/unassigned/', views.unassigned_students, name='unassigned_students'),
    path('documents/generate/<int:template_id>/<int:object_id>/', views.download_generated_document, name='generate_document'),
    path('documents/templates/', views.document_templates_list, name='document_templates'),
    path('documents/templates/<int:template_id>/delete/', views.delete_document_template, name='delete_document_template'),
    path('archives/alumni/', views.archive_alumni, name='archive_alumni'),
    path('archives/expelled/', views.archive_expelled, name='archive_expelled'),
    path('reports/contingent/download/', views.download_contingent_report, name='download_contingent_report'),
    path('orders/mass-create/', views.mass_order_create, name='mass_order_mass_create'),
    path('structure/specialization/add/', views.add_specialization, name='add_specialization'),
    path('structure/specialization/edit/<int:pk>/', views.edit_specialization, name='edit_specialization'),
    path('structure/specialization/delete/<int:pk>/', views.delete_specialization, name='delete_specialization'),

]