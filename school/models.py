from django.db import models
from django.conf import settings


# Типове учебни зали — ползват се и от предмета (подходяща зала),
# и от модела Room в приложението timetable.
ROOM_TYPE_CHOICES = [
    ('standard', 'Стандартна класна стая'),
    ('computer', 'Компютърен кабинет'),
    ('gym', 'Физкултурен салон'),
    ('lab', 'Лаборатория'),
]


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Наименование')
    required_room_type = models.CharField(
        max_length=20, choices=ROOM_TYPE_CHOICES, blank=True,
        verbose_name='Подходящ тип зала',
        help_text='Ако е зададен, часовете по предмета се провеждат само в зала от този тип.',
    )
    # Чуждите езици не са твърдо зададени в кода — отбелязват се тук и
    # всеки клас избира кои два от тях изучава.
    is_foreign_language = models.BooleanField(default=False, verbose_name='Чужд език')
    # Предмети, участващи в разписание, не се изтриват физически, а се деактивират.
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        verbose_name = 'Учебен предмет'
        verbose_name_plural = 'Учебни предмети'
        ordering = ['name']

    def __str__(self):
        return self.name


class Class(models.Model):
    name = models.CharField(max_length=10, unique=True, verbose_name='Клас')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    homeroom_teacher = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'teacher'},
        related_name='homeroom_class',
        verbose_name='Класен ръководител',
    )

    class Meta:
        verbose_name = 'Клас'
        verbose_name_plural = 'Класове'
        ordering = ['name']

    def __str__(self):
        return self.name


class TeacherClassSubject(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='assignments',
        verbose_name='Учител',
    )
    school_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Клас',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Предмет',
    )

    class Meta:
        verbose_name = 'Назначение'
        verbose_name_plural = 'Назначения'
        unique_together = ('teacher', 'school_class', 'subject')

    def __str__(self):
        return f'{self.teacher} — {self.subject} ({self.school_class})'
