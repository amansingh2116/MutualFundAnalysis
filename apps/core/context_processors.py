"""
Template context processors — injects global data into every template.
"""
from datetime import date


def global_context(request):
    """
    Adds the following to every template context:
    - today: current date
    - current_year: current year (for footer copyright)
    - site_name: application display name
    """
    return {
        'today': date.today(),
        'current_year': date.today().year,
        'site_name': 'MF Research',
    }
