from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Администратор'),
        ('teacher', 'Учител'),
        ('student', 'Ученик'),
        ('parent', 'Родител'),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    def is_admin(self):
        return self.role == 'admin'

    def is_teacher(self):
        return self.role == 'teacher'

    def is_student(self):
        return self.role == 'student'

    def is_parent(self):
        return self.role == 'parent'

    def __str__(self):
        return f'{self.get_full_name()} ({self.get_role_display()})'
