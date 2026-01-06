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


    path('groups/', views.group_management, name='group_management'),
    path('groups/add/', views.add_group, name='add_group'),
    path('groups/edit/<int:group_id>/', views.edit_group, name='edit_group'),
    path('profile/view/<int:user_id>/', views.view_user_profile, name='view_user_profile'),
    path('groups/delete/<int:group_id>/', views.delete_group, name='delete_group'),
]