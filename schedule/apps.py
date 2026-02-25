from django.apps import AppConfig

class ScheduleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'schedule'
    verbose_name = 'Управление расписанием'

    def ready(self):
        import schedule.signals  # Подключаем сигналы при запуске