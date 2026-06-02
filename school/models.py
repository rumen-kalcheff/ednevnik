from django.db import models
from django.conf import settings


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Наименование')

    class Meta:
        verbose_name = 'Учебен предмет'
        verbose_name_plural = 'Учебни предмети'
        ordering = ['name']

    def __str__(self):
        return self.name


class Class(models.Model):
    name = models.CharField(max_length=10, unique=True, verbose_name='Клас')
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


class Timetable(models.Model):
    DAY_CHOICES = [
        (1, 'Понеделник'), (2, 'Вторник'), (3, 'Сряда'),
        (4, 'Четвъртък'), (5, 'Петък'),
    ]
    HOUR_CHOICES = [
        (1, '1-ви час'), (2, '2-ри час'), (3, '3-ти час'), (4, '4-ти час'),
        (5, '5-ти час'), (6, '6-ти час'), (7, '7-ми час'), (8, '8-ми час'),
    ]

    assignment = models.ForeignKey(
        TeacherClassSubject, on_delete=models.CASCADE,
        related_name='timetable_entries', verbose_name='Назначение',
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES, verbose_name='Ден')
    hour_number = models.PositiveSmallIntegerField(choices=HOUR_CHOICES, verbose_name='Час')

    class Meta:
        verbose_name = 'Разписание'
        verbose_name_plural = 'Разписания'
        unique_together = ('assignment', 'day_of_week', 'hour_number')
        ordering = ['day_of_week', 'hour_number']

    def __str__(self):
        return f'{self.get_day_of_week_display()} {self.hour_number}ч — {self.assignment}'
