import os
from django.core.exceptions import ValidationError

def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1]  # получаем расширение
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.avi']
    if not ext.lower() in valid_extensions:
        raise ValidationError(f'Неподдерживаемый тип файла. Разрешены: {", ".join(valid_extensions)}')

def validate_image_only(value):
    ext = os.path.splitext(value.name)[1]
    valid_extensions = ['.jpg', '.jpeg', '.png']
    if not ext.lower() in valid_extensions:
        raise ValidationError('Пожалуйста, загрузите только изображение (JPG, PNG).')