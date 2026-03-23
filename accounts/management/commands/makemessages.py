from django.core.management.commands import makemessages

class Command(makemessages.Command):
    help = "Кастомная команда makemessages, которая автоматически игнорирует виртуальные окружения и мусорные папки."

    def handle(self, *args, **options):
        ignore_patterns = options.get('ignore_patterns',[])
        
        default_ignores =[
            'env/*', 
            'venv/*', 
            '.venv/*', 
            'ENV/*', 
            'node_modules/*', 
            'logs/*', 
            'media/*',
            'staticfiles/*',
            'build/*',
            'dist/*'
        ]
        
        ignore_patterns.extend(default_ignores)
        options['ignore_patterns'] = list(set(ignore_patterns))  
        
        super().handle(*args, **options)