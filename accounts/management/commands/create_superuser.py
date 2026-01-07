from django.core.management.base import BaseCommand
from accounts.models import User, Dean

class Command(BaseCommand):
    help = 'Создание суперпользователя с ролью декана'

    def handle(self, *args, **options):
        username = input("Введите логин суперпользователя: ")
        email = input("Введите email: ")
        password = input("Введите пароль: ")
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(
                f'Пользователь {username} уже существует!'
            ))
            return
        
        # Создаем суперпользователя с ролью DEAN
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name='Администратор',
            last_name='Системы',
            role='DEAN'  # ✅ Обязательно указываем роль
        )
        
        # ✅ ИСПРАВЛЕНО: НЕ создаем профиль вручную!
        # Профиль Dean уже создан автоматически через сигнал post_save
        if hasattr(user, 'dean_profile'):
            self.stdout.write(self.style.SUCCESS(
                f'Суперпользователь {username} (декан) успешно создан! Профиль создан автоматически.'
            ))
        else:
            # На случай если сигнал не сработал - создаем вручную
            Dean.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(
                f'Суперпользователь {username} (декан) успешно создан! Профиль создан вручную.'
            ))