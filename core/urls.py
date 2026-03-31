from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('search/', views.global_search, name='global_search'),
    path('backup/export/', views.export_database, name='export_db'),
    path('backup/import/', views.import_database, name='import_db'),
]