# â ÐÐ¡ÐÐ ÐÐÐÐÐÐ: ÑÐ±ÑÐ°Ð½Ð° Ð½ÐµÑÑÑÐµÑÑÐ²ÑÑÑÐ°Ñ ÑÑÐ½ÐºÑÐ¸Ñ home_page
# Ð­ÑÐ¾Ñ ÑÐ°Ð¹Ð» Ð´Ð¾Ð»Ð¶ÐµÐ½ Ð·Ð°Ð¼ÐµÐ½Ð¸ÑÑ Ð²Ð°Ñ ÑÐµÐ°Ð»ÑÐ½ÑÐ¹ department_platform/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('schedule/', include('schedule.urls')),
    path('journal/', include('journal.urls')),
    path('', include('core.urls')),  # â ÐÐ ÐÐÐÐÐ¬ÐÐ - ÑÐµÐ´Ð¸ÑÐµÐºÑ Ð½Ð° dashboard
]

# Ð¡ÑÐ°ÑÐ¸ÑÐµÑÐºÐ¸Ðµ ÑÐ°Ð¹Ð»Ñ Ð¸ Ð¼ÐµÐ´Ð¸Ð° (ÑÐ¾Ð»ÑÐºÐ¾ Ð´Ð»Ñ DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)