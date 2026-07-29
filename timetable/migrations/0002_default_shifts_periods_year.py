from datetime import date, time

from django.db import migrations


# Часовете по подразбиране от изискванията — администраторът може да ги промени.
FIRST_SHIFT_PERIODS = [
    (1, time(7, 30), time(8, 10)),
    (2, time(8, 20), time(9, 0)),
    (3, time(9, 10), time(9, 50)),
    (4, time(10, 10), time(10, 50)),
    (5, time(11, 0), time(11, 40)),
    (6, time(11, 50), time(12, 30)),
    (7, time(12, 40), time(13, 20)),
]

SECOND_SHIFT_PERIODS = [
    (1, time(13, 30), time(14, 10)),
    (2, time(14, 20), time(15, 0)),
    (3, time(15, 10), time(15, 50)),
    (4, time(16, 10), time(16, 50)),
    (5, time(17, 0), time(17, 40)),
    (6, time(17, 50), time(18, 30)),
    (7, time(18, 40), time(19, 20)),
]


def current_year_name():
    """Учебната година започва през септември."""
    today = date.today()
    start = today.year if today.month >= 9 else today.year - 1
    return f'{start}/{start + 1}'


def create_defaults(apps, schema_editor):
    SchoolYear = apps.get_model('timetable', 'SchoolYear')
    Shift = apps.get_model('timetable', 'Shift')
    Period = apps.get_model('timetable', 'Period')

    if not SchoolYear.objects.exists():
        SchoolYear.objects.create(name=current_year_name(), is_current=True)

    for name, order, periods in [
        ('Първа смяна', 1, FIRST_SHIFT_PERIODS),
        ('Втора смяна', 2, SECOND_SHIFT_PERIODS),
    ]:
        shift, _ = Shift.objects.get_or_create(name=name, defaults={'order': order})
        for number, start_time, end_time in periods:
            Period.objects.get_or_create(
                shift=shift, number=number,
                defaults={'start_time': start_time, 'end_time': end_time},
            )


def remove_defaults(apps, schema_editor):
    Shift = apps.get_model('timetable', 'Shift')
    Shift.objects.filter(name__in=['Първа смяна', 'Втора смяна']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_defaults, remove_defaults),
    ]
