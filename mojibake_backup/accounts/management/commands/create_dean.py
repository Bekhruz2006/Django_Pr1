from django.core.management.base import BaseCommand
from accounts.models import User, Dean

class Command(BaseCommand):
    help = 'РЎРѕР·РґР°РЅРёРµ РїРµСЂРІРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ-РґРµРєР°РЅР°'

    def handle(self, *args, **options):
        username = input("Р’РІРµРґРёС‚Рµ Р»РѕРіРёРЅ: ")
        first_name = input("Р’РІРµРґРёС‚Рµ РёРјСЏ: ")
        last_name = input("Р’РІРµРґРёС‚Рµ С„Р°РјРёР»РёСЋ: ")
        password = input("Р’РІРµРґРёС‚Рµ РїР°СЂРѕР»СЊ: ")
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {username} СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚!'))
            return
        
        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
            role='DEAN'
        )
        
        Dean.objects.create(user=user)
        
        self.stdout.write(self.style.SUCCESS(f'Р”РµРєР°РЅ {username} СѓСЃРїРµС€РЅРѕ СЃРѕР·РґР°РЅ!'))