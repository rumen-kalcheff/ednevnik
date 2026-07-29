"""Примерни данни за разписанието: зали, смени по класове, седмичен хорариум
и попълнено разписание за наличните класове.

Използване:
    python manage.py seed_timetable
    python manage.py seed_timetable --reset   # изтрива старите разписания за годината
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from school.models import Class, Subject, TeacherClassSubject
from timetable import services
from timetable.models import (
    ClassYearSetting, CurriculumEntry, Room, SchoolYear, Shift,
    TimetableVersion,
)


# Зали по подразбиране: (наименование, капацитет, тип)
ROOMS = [
    ('101', 26, 'standard'), ('102', 26, 'standard'), ('103', 26, 'standard'),
    ('201', 30, 'standard'), ('202', 30, 'standard'),
    ('Компютърен кабинет', 20, 'computer'),
    ('Физкултурен салон', 60, 'gym'),
    ('Лаборатория', 18, 'lab'),
]

# Предмети с изискване за тип зала.
ROOM_REQUIREMENTS = {
    'Физическо възпитание': 'gym',
    'Информационни технологии': 'computer',
}

# Седмичен хорариум по предмет (без чуждите езици).
HOURS = {
    'Български език': 3,
    'Математика': 3,
    'История': 2,
    'География': 2,
    'Биология': 2,
    'Физика': 2,
    'Химия': 2,
    'Философия': 1,
    'Физическо възпитание': 2,
    'Информационни технологии': 2,
}
FIRST_LANGUAGE_HOURS = 5
SECOND_LANGUAGE_HOURS = 4

# Първата смяна е по подразбиране; тези класове тръгват втора смяна.
# Разпределението е само начално — променя се от администратора.
SECOND_SHIFT_GRADES = {9, 11}


class Command(BaseCommand):
    help = 'Създава примерни данни за учебното разписание.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Изтрива съществуващите разписания за учебната година.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        year = SchoolYear.current()
        if year is None:
            self.stderr.write('Няма учебна година. Изпълнете първо: python manage.py migrate')
            return

        first_shift = Shift.objects.filter(order=1).first()
        second_shift = Shift.objects.filter(order=2).first() or first_shift
        if first_shift is None:
            self.stderr.write('Няма създадени смени. Изпълнете първо: python manage.py migrate')
            return

        if options['reset']:
            deleted, _ = TimetableVersion.objects.filter(school_year=year).delete()
            self.stdout.write(f'Изтрити стари версии на разписанието: {deleted}')

        self._create_rooms()
        self._mark_subjects()

        # Всеки клас получава своя класна стая; специализираните зали се
        # ползват само от предметите, които ги изискват.
        standard_rooms = list(Room.objects.filter(is_active=True, room_type='standard'))
        classes = list(Class.objects.filter(is_active=True))
        for index, school_class in enumerate(classes):
            home_room = standard_rooms[index % len(standard_rooms)] if standard_rooms else None
            self._seed_class(year, school_class, first_shift, second_shift, home_room)

        self.stdout.write(self.style.SUCCESS('Готово.'))

    # ── Помощни стъпки ────────────────────────────────────────

    def _create_rooms(self):
        created = 0
        for name, capacity, room_type in ROOMS:
            _, was_created = Room.objects.get_or_create(
                name=name, defaults={'capacity': capacity, 'room_type': room_type})
            created += was_created
        self.stdout.write(f'Зали: {created} нови, общо {Room.objects.count()}.')

    def _mark_subjects(self):
        for name, room_type in ROOM_REQUIREMENTS.items():
            Subject.objects.filter(name=name, required_room_type='').update(
                required_room_type=room_type)

    def _grade_number(self, school_class):
        digits = ''.join(ch for ch in school_class.name if ch.isdigit())
        return int(digits) if digits else 0

    def _seed_class(self, year, school_class, first_shift, second_shift, home_room):
        shift = (second_shift if self._grade_number(school_class) in SECOND_SHIFT_GRADES
                 else first_shift)

        subjects = list(Subject.objects.filter(
            is_active=True, assignments__school_class=school_class).distinct())
        languages = [s for s in subjects if s.is_foreign_language]
        if len(languages) < 2:
            self.stdout.write(self.style.WARNING(
                f'{school_class}: няма два чужди езика с назначени преподаватели — пропуснат.'))
            return

        # Английският е първи език, ако класът го изучава.
        languages.sort(key=lambda s: (s.name != 'Английски език', s.name))
        first_language, second_language = languages[0], languages[1]

        ClassYearSetting.objects.update_or_create(
            school_year=year, school_class=school_class,
            defaults={'shift': shift, 'first_language': first_language,
                      'second_language': second_language},
        )

        plan = {first_language: FIRST_LANGUAGE_HOURS, second_language: SECOND_LANGUAGE_HOURS}
        for subject in subjects:
            if subject.is_foreign_language:
                continue
            hours = HOURS.get(subject.name)
            if hours:
                plan[subject] = hours

        CurriculumEntry.objects.filter(school_year=year, school_class=school_class).exclude(
            subject__in=plan.keys()).delete()
        for subject, hours in plan.items():
            CurriculumEntry.objects.update_or_create(
                school_year=year, school_class=school_class, subject=subject,
                defaults={'hours_per_week': hours},
            )

        total = sum(plan.values())
        self.stdout.write(
            f'{school_class}: {shift}, {first_language} / {second_language}, '
            f'хорариум {total} часа.')

        if services.published_version(year, school_class):
            self.stdout.write(f'  {school_class} вече има публикувано разписание — пропуснато.')
            return

        version = services.get_or_create_draft(year, school_class, None)
        placed, missing = self._fill(version, plan, shift, home_room)
        self.stdout.write(f'  Поставени часове: {placed} от {total}.')

        if missing:
            self.stdout.write(self.style.WARNING(
                f'  Не бяха поставени: {", ".join(missing)}'))
            return

        errors = services.publish(version, None)
        if errors:
            self.stdout.write(self.style.WARNING(f'  Не е публикувано: {errors[0]}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'  Разписанието на {school_class} е публикувано.'))

    def _fill(self, version, plan, shift, home_room):
        """Просто последователно попълване: за всеки час се търси първият
        свободен ден и период, който минава всички проверки."""
        from timetable.models import Lesson

        periods = list(shift.periods.all())
        all_rooms = list(Room.objects.filter(is_active=True))
        assignments = {
            a.subject_id: a.teacher
            for a in TeacherClassSubject.objects.filter(
                school_class=version.school_class).select_related('teacher')
        }

        placed = 0
        missing = []
        # Предметите с най-много часове се разполагат първи — по-лесно се събират.
        for subject, hours in sorted(plan.items(), key=lambda item: -item[1]):
            teacher = assignments.get(subject.pk)
            if teacher is None:
                missing.append(subject.name)
                continue

            rooms = self._rooms_for(subject, home_room, all_rooms)
            left = hours
            for period in periods:
                if left == 0:
                    break
                for day in services.DAYS:
                    if left == 0:
                        break
                    for room in rooms:
                        errors = services.check_lesson(
                            version, day, period, subject, teacher, room)
                        if errors:
                            continue
                        Lesson.objects.create(
                            version=version, day_of_week=day, period=period,
                            subject=subject, teacher=teacher, room=room)
                        placed += 1
                        left -= 1
                        break
            if left:
                missing.append(f'{subject.name} ({left} ч.)')
        return placed, missing

    def _rooms_for(self, subject, home_room, all_rooms):
        """Подходящите зали за предмета — първо изискваният тип, иначе
        класната стая на класа."""
        if subject.required_room_type:
            matching = [r for r in all_rooms if r.room_type == subject.required_room_type]
            return matching or all_rooms

        standard = [r for r in all_rooms if r.room_type == 'standard']
        if home_room is None:
            return standard or all_rooms
        return [home_room] + [r for r in standard if r.pk != home_room.pk]
