from django.db import models
from django.conf import settings


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='teacher_profile',
        verbose_name='Потребител',
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')

    class Meta:
        verbose_name = 'Учител'
        verbose_name_plural = 'Учители'
        ordering = ['user__last_name']

    def __str__(self):
        return self.user.get_full_name()
