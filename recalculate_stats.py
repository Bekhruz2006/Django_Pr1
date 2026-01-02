"""
ПОЛНОЕ УДАЛЕНИЕ И ПЕРЕСОЗДАНИЕ БАЗЫ ДАННЫХ

⚠️ ВНИМАНИЕ: ВСЕ ДАННЫЕ БУДУТ БЕЗВОЗВРАТНО УДАЛЕНЫ!

Запуск: python reset_database.py
"""

import os
import sys
import shutil
from pathlib import Path

print("=" * 70)
print("⚠️  ПОЛНОЕ УДАЛЕНИЕ БАЗЫ ДАННЫХ")
print("=" * 70)

print("""
ВНИМАНИЕ! Эта операция удалит:
- ❌ Всех пользователей
- ❌ Все группы
- ❌ Всё расписание
- ❌ Все оценки и журнал
- ❌ Все новости и чаты
- ❌ ВСЕ ДАННЫЕ БЕЗ ВОЗМОЖНОСТИ ВОССТАНОВЛЕНИЯ!

Вы УВЕРЕНЫ, что хотите продолжить?
""")

confirm1 = input("Напишите 'DELETE' чтобы продолжить: ")
if confirm1 != 'DELETE':
    print("Отменено.")
    sys.exit(0)

confirm2 = input("Вы ТОЧНО уверены? Напишите 'YES' для подтверждения: ")
if confirm2 != 'YES':
    print("Отменено.")
    sys.exit(0)

print("\n" + "=" * 70)
print("🗑️  УДАЛЕНИЕ БАЗЫ ДАННЫХ...")
print("=" * 70)

# Путь к базе данных
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / 'db.sqlite3'

# Удаляем файл базы данных
if DB_FILE.exists():
    try:
        os.remove(DB_FILE)
        print(f"✅ Удалён файл: {DB_FILE}")
    except Exception as e:
        print(f"❌ Ошибка при удалении: {e}")
        sys.exit(1)
else:
    print(f"ℹ️  Файл базы данных не найден: {DB_FILE}")

# Удаляем папку миграций в каждом приложении
apps = ['accounts', 'journal', 'schedule', 'news', 'chat', 'core']

print("\n🔄 УДАЛЕНИЕ МИГРАЦИЙ...")
for app in apps:
    migrations_dir = BASE_DIR / app / 'migrations'
    if migrations_dir.exists():
        # Удаляем все файлы миграций, кроме __init__.py
        for file in migrations_dir.glob('*.py'):
            if file.name != '__init__.py':
                try:
                    os.remove(file)
                    print(f"✅ Удалён: {app}/migrations/{file.name}")
                except Exception as e:
                    print(f"❌ Ошибка: {e}")
        
        # Удаляем __pycache__
        pycache_dir = migrations_dir / '__pycache__'
        if pycache_dir.exists():
            try:
                shutil.rmtree(pycache_dir)
                print(f"✅ Удалён: {app}/migrations/__pycache__")
            except Exception as e:
                print(f"❌ Ошибка: {e}")

print("\n" + "=" * 70)
print("✅ БАЗА ДАННЫХ ПОЛНОСТЬЮ УДАЛЕНА!")
print("=" * 70)

print("""
📝 СЛЕДУЮЩИЕ ШАГИ:

1️⃣ Создайте новые миграции:
   python manage.py makemigrations

2️⃣ Примените миграции:
   python manage.py migrate

3️⃣ Создайте первого пользователя:
   python fix_create_first_user.py
   
   ИЛИ:
   
   python manage.py createsuperuser

4️⃣ Запустите сервер:
   python manage.py runserver

5️⃣ Войдите в систему:
   http://localhost:8000/accounts/login/
""")

print("=" * 70)
print("🎉 ГОТОВО! Теперь у вас чистая база данных")
print("=" * 70)