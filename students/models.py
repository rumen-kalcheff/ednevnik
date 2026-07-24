from django.db import models
from django.conf import settings
from school.models import Class


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='student_profile',
        verbose_name='Потребител',
    )
    school_class = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        verbose_name='Клас',
    )
    date_of_birth = models.DateField(null=True, blank=True, verbose_name='Дата на раждане')
    egn = models.CharField(max_length=10, blank=True, verbose_name='ЕГН')

    class Meta:
        verbose_name = 'Ученик'
        verbose_name_plural = 'Ученици'
        ordering = ['school_class', 'user__first_name', 'user__last_name']

    def __str__(self):
        return f'{self.user.get_full_name()} — {self.school_class}'


class ParentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'parent'},
        related_name='parent_profile',
        verbose_name='Потребител',
    )
    children = models.ManyToManyField(
        StudentProfile,
        blank=True,
        related_name='parents',
        verbose_name='Деца',
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')

    class Meta:
        verbose_name = 'Родител'
        verbose_name_plural = 'Родители'

    def __str__(self):
        return self.user.get_full_name()
