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
