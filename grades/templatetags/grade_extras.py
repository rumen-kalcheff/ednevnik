from django import template

register = template.Library()


@register.filter
def grade_name(value):
    """Връща словесната оценка по средна стойност (скала на МОН)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ''
    if v >= 5.50:
        return 'Отличен'
    if v >= 4.50:
        return 'Мн. добър'
    if v >= 3.50:
        return 'Добър'
    if v >= 3.00:
        return 'Среден'
    return 'Слаб'
