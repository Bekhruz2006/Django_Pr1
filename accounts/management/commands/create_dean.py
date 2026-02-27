from django.core.management.base import BaseCommand
from accounts.models import User, Dean

class Command(BaseCommand):
    help = 'Создание первого пользователя-декана'

    def handle(self, *args, **options):
        username = input("Введите логин: ")
        first_name = input("Введите имя: ")
        last_name = input("Введите фамилию: ")
        password = input("Введите пароль: ")
        if User.objects.filter(username=username).exists():
            existing_user = User.objects.get(username=username)
            if hasattr(existing_user, 'dean_profile'):
                self.stdout.write(self.style.ERROR(
                    f'Пользователь {username} уже является деканом!'
                ))
                return
            existing_user.role = 'DEAN'
            existing_user.set_password(password)
            existing_user.save()
            Dean.objects.get_or_create(user=existing_user)
            self.stdout.write(self.style.SUCCESS(
                f'Пользователь {username} назначен деканом!'
            ))
            return
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
            role='DEAN'
        )
        if hasattr(user, 'dean_profile'):
            self.stdout.write(self.style.SUCCESS(
                f'Декан {username} успешно создан! Профиль создан автоматически.'
            ))
        else:
            Dean.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(
                f'Декан {username} успешно создан! Профиль создан вручную.'
            ))