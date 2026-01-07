from django import template

register = template.Library()

@register.filter(name='get_slot')
def get_slot(dictionary, key):
    """Получить значение из словаря по ключу"""
    if dictionary is None:
        return None
    return dictionary.get(key)