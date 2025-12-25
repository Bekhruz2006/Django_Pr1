from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('password/change/', views.change_password, name='change_password'),
    
    # Dean management
    path('management/', views.user_management, name='user_management'),
    path('management/add/', views.add_user, name='add_user'),
    path('management/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('management/reset-password/<int:user_id>/', views.reset_password, name='reset_password'),
    path('management/toggle-active/<int:user_id>/', views.toggle_user_active, name='toggle_user_active'),
    path('management/transfer/<int:student_id>/', views.transfer_student, name='transfer_student'),
]