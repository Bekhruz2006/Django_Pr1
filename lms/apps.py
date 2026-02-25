from django.apps import AppConfig

class LmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lms'
    verbose_name = 'LMS (Обучение)'

    def ready(self):
        import lms.signals  