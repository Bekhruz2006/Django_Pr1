from django.urls import path
from . import views, views_api

app_name = 'lms'

urlpatterns = [
    path('my-courses/', views.course_list, name='course_list'),
    path('course/<int:course_id>/', views.course_detail, name='course_detail'),
    
    path('api/module/add/', views_api.add_course_module, name='api_add_module'),
]