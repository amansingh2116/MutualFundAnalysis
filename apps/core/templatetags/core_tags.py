from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Splits a string into a list based on the given argument."""
    return value.split(arg)

@register.filter
def get_item(dictionary, key):
    """Gets an item from a dictionary dynamically."""
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None
