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
            self.stdout.write(self.style.ERROR(f'Пользователь {username} уже существует!'))
            return
        
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
            role='DEAN'
        )
        
        Dean.objects.create(user=user)
        
        self.stdout.write(self.style.SUCCESS(f'Декан {username} успешно создан!'))