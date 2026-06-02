from django.db import models
from django.conf import settings
from school.models import Subject, Class


class Material(models.Model):
    title = models.CharField(max_length=200, verbose_name='Заглавие')
    file = models.FileField(upload_to='materials/', verbose_name='Файл')
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE,
        related_name='materials', verbose_name='Предмет',
    )
    school_class = models.ForeignKey(
        Class, on_delete=models.CASCADE,
        related_name='materials', verbose_name='Клас',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='materials', verbose_name='Учител',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Качен на')
    description = models.TextField(blank=True, verbose_name='Описание')

    class Meta:
        verbose_name = 'Учебен материал'
        verbose_name_plural = 'Учебни материали'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.title} — {self.subject} ({self.school_class})'
