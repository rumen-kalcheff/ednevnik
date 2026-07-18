from django.db import models
from django.conf import settings
from school.models import Subject, Class
from students.models import StudentProfile


class Grade(models.Model):
    GRADE_TYPE_CHOICES = [
        ('oral', 'Устно изпитване'),
        ('written', 'Контролно'),
        ('current', 'Текуща'),
        ('term1', 'Срочна – 1 срок'),
        ('term2', 'Срочна – 2 срок'),
        ('annual', 'Годишна'),
    ]
    # Срочни и годишни оценки — обобщаващи, по една на ученик/предмет
    FINAL_TYPES = ('term1', 'term2', 'annual')
    GRADE_VALUES = [(i, str(i)) for i in range(2, 7)]

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE,
        related_name='grades', verbose_name='Ученик',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE,
        related_name='grades', verbose_name='Предмет',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='given_grades', verbose_name='Учител',
    )
    value = models.PositiveSmallIntegerField(choices=GRADE_VALUES, verbose_name='Оценка')
    grade_type = models.CharField(
        max_length=10, choices=GRADE_TYPE_CHOICES,
        default='current', verbose_name='Вид',
    )
    date = models.DateField(verbose_name='Дата')
    note = models.CharField(max_length=200, blank=True, verbose_name='Забележка')

    class Meta:
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'
        ordering = ['-date']

    def __str__(self):
        return f'{self.student} — {self.subject}: {self.value}'


class Absence(models.Model):
    ABSENCE_TYPE_CHOICES = [
        ('unexcused', 'Неизвинено'),
        ('excused', 'Извинено'),
    ]

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE,
        related_name='absences', verbose_name='Ученик',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE,
        related_name='absences', verbose_name='Предмет',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='given_absences', verbose_name='Учител',
    )
    date = models.DateField(verbose_name='Дата')
    absence_type = models.CharField(
        max_length=10, choices=ABSENCE_TYPE_CHOICES,
        default='unexcused', verbose_name='Вид',
    )

    class Meta:
        verbose_name = 'Отсъствие'
        verbose_name_plural = 'Отсъствия'
        ordering = ['-date']

    def __str__(self):
        return f'{self.student} — {self.subject} ({self.date})'
