"""
ИСПРАВЛЕНИЕ: Скрипт для создания первого пользователя-декана

Запуск:
1. python manage.py migrate
2. python fix_create_first_user.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'department_platform.settings')
django.setup()

from accounts.models import User, Dean

print("=" * 50)
print("СОЗДАНИЕ ПЕРВОГО ПОЛЬЗОВАТЕЛЯ-ДЕКАНА")
print("=" * 50)

# Проверяем, есть ли уже пользователи
if User.objects.exists():
    print("\n⚠️  В базе уже есть пользователи:")
    for u in User.objects.all()[:5]:
        print(f"  - {u.username} ({u.get_role_display()})")
    
    choice = input("\nСоздать нового декана? (yes/no): ")
    if choice.lower() != 'yes':
        print("Отменено.")
        exit()

print("\n📝 Введите данные для нового декана:")
username = input("Логин: ").strip()
first_name = input("Имя: ").strip()
last_name = input("Фамилия: ").strip()
password = input("Пароль: ").strip()

if not all([username, first_name, last_name, password]):
    print("❌ Все поля обязательны!")
    exit()

if User.objects.filter(username=username).exists():
    print(f"❌ Пользователь '{username}' уже существует!")
    exit()

try:
    # Создаем пользователя
    user = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=password,
        role='DEAN',
        is_staff=True,  # Доступ в админку
        is_superuser=True  # Суперпользователь
    )
    
    # Создаем профиль декана
    Dean.objects.create(user=user)
    
    print("\n✅ УСПЕШНО!")
    print(f"   Логин: {username}")
    print(f"   Пароль: {password}")
    print(f"   Роль: Декан")
    print(f"\n🌐 Войдите на сайт: http://localhost:8000/accounts/login/")
    print(f"🔧 Админка: http://localhost:8000/admin/")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")