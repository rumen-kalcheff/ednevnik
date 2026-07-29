from django.db import models
from django.conf import settings
from school.models import Class, Subject, ROOM_TYPE_CHOICES


# ── Учебна година ─────────────────────────────────────────────

class SchoolYear(models.Model):
    """Учебна година — всички настройки на разписанието се водят по година,
    за да могат смените и хорариумът да се променят от година на година."""

    name = models.CharField(max_length=20, unique=True, verbose_name='Учебна година')
    is_current = models.BooleanField(default=False, verbose_name='Текуща')

    class Meta:
        verbose_name = 'Учебна година'
        verbose_name_plural = 'Учебни години'
        ordering = ['-name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Текущата учебна година е само една.
        if self.is_current:
            SchoolYear.objects.exclude(pk=self.pk).update(is_current=False)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first() or cls.objects.first()


# ── Смени и учебни периоди ────────────────────────────────────

class Shift(models.Model):
    """Смяна (първа/втора). Класовете се разпределят по смени от
    администратора — разпределението не е зададено в програмния код."""

    name = models.CharField(max_length=50, unique=True, verbose_name='Наименование')
    order = models.PositiveSmallIntegerField(default=1, verbose_name='Пореден номер')
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        verbose_name = 'Смяна'
        verbose_name_plural = 'Смени'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Period(models.Model):
    """Учебен период (пореден час) в рамките на една смяна.
    Часовете се редактират от администратора."""

    shift = models.ForeignKey(
        Shift, on_delete=models.CASCADE,
        related_name='periods', verbose_name='Смяна',
    )
    number = models.PositiveSmallIntegerField(verbose_name='Пореден час')
    start_time = models.TimeField(verbose_name='Начален час')
    end_time = models.TimeField(verbose_name='Краен час')

    class Meta:
        verbose_name = 'Учебен период'
        verbose_name_plural = 'Учебни периоди'
        ordering = ['shift__order', 'number']
        unique_together = ('shift', 'number')

    def __str__(self):
        return f'{self.number}. час ({self.start_time:%H:%M}–{self.end_time:%H:%M})'


# ── Учебни зали ───────────────────────────────────────────────

class Room(models.Model):
    # Типовете зали са общи с подходящия тип зала на предмета.
    ROOM_TYPE_CHOICES = ROOM_TYPE_CHOICES

    name = models.CharField(max_length=50, unique=True, verbose_name='Номер / наименование')
    capacity = models.PositiveSmallIntegerField(default=26, verbose_name='Капацитет')
    room_type = models.CharField(
        max_length=20, choices=ROOM_TYPE_CHOICES,
        default='standard', verbose_name='Тип на залата',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        verbose_name = 'Учебна зала'
        verbose_name_plural = 'Учебни зали'
        ordering = ['name']

    def __str__(self):
        return self.name


# ── Настройки на клас за учебна година ────────────────────────

class ClassYearSetting(models.Model):
    """Смяна и чужди езици на клас за конкретна учебна година.
    Разпределението по смени се задава тук, а не в кода."""

    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE,
        related_name='class_settings', verbose_name='Учебна година',
    )
    school_class = models.ForeignKey(
        Class, on_delete=models.CASCADE,
        related_name='year_settings', verbose_name='Клас',
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT,
        related_name='class_settings', verbose_name='Смяна',
    )
    first_language = models.ForeignKey(
        Subject, on_delete=models.PROTECT, null=True, blank=True,
        related_name='first_language_classes', verbose_name='Първи чужд език',
    )
    second_language = models.ForeignKey(
        Subject, on_delete=models.PROTECT, null=True, blank=True,
        related_name='second_language_classes', verbose_name='Втори чужд език',
    )

    class Meta:
        verbose_name = 'Настройка на клас'
        verbose_name_plural = 'Настройки на класове'
        ordering = ['school_class__name']
        unique_together = ('school_year', 'school_class')

    def __str__(self):
        return f'{self.school_class} — {self.shift} ({self.school_year})'


# ── Седмичен хорариум ─────────────────────────────────────────

class CurriculumEntry(models.Model):
    """Брой учебни часове седмично по предмет за клас.
    При публикуване разписанието се сверява точно с този брой."""

    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE,
        related_name='curriculum', verbose_name='Учебна година',
    )
    school_class = models.ForeignKey(
        Class, on_delete=models.CASCADE,
        related_name='curriculum', verbose_name='Клас',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT,
        related_name='curriculum', verbose_name='Предмет',
    )
    hours_per_week = models.PositiveSmallIntegerField(verbose_name='Часове седмично')

    class Meta:
        verbose_name = 'Хорариум'
        verbose_name_plural = 'Седмичен хорариум'
        ordering = ['school_class__name', 'subject__name']
        unique_together = ('school_year', 'school_class', 'subject')

    def __str__(self):
        return f'{self.school_class} — {self.subject}: {self.hours_per_week} ч.'


# ── Разписание: версии (чернова / публикувано) ────────────────

class TimetableVersion(models.Model):
    """Версия на седмичното разписание на един клас.

    Черновата се вижда само от администратора. При редакция на публикувано
    разписание се създава нова чернова (копие), а учителите, учениците и
    родителите продължават да виждат публикуваната версия."""

    DRAFT = 'draft'
    PUBLISHED = 'published'
    ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (DRAFT, 'Чернова'),
        (PUBLISHED, 'Публикувано'),
        (ARCHIVED, 'Архивирано'),
    ]

    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE,
        related_name='versions', verbose_name='Учебна година',
    )
    school_class = models.ForeignKey(
        Class, on_delete=models.CASCADE,
        related_name='timetable_versions', verbose_name='Клас',
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default=DRAFT, verbose_name='Състояние',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Създадено на')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_timetables', verbose_name='Създадено от',
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Публикувано на')
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='published_timetables', verbose_name='Публикувано от',
    )

    class Meta:
        verbose_name = 'Версия на разписанието'
        verbose_name_plural = 'Версии на разписанието'
        ordering = ['school_class__name', '-created_at']
        constraints = [
            # Само по една чернова и по едно публикувано разписание на клас за година.
            models.UniqueConstraint(
                fields=['school_year', 'school_class'],
                condition=models.Q(status='draft'),
                name='unique_draft_per_class',
            ),
            models.UniqueConstraint(
                fields=['school_year', 'school_class'],
                condition=models.Q(status='published'),
                name='unique_published_per_class',
            ),
        ]

    def __str__(self):
        return f'{self.school_class} — {self.get_status_display()} ({self.school_year})'

    @property
    def is_draft(self):
        return self.status == self.DRAFT


class Lesson(models.Model):
    """Един учебен час в седмичното разписание на клас."""

    DAY_CHOICES = [
        (1, 'Понеделник'), (2, 'Вторник'), (3, 'Сряда'),
        (4, 'Четвъртък'), (5, 'Петък'),
    ]

    version = models.ForeignKey(
        TimetableVersion, on_delete=models.CASCADE,
        related_name='lessons', verbose_name='Версия',
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=DAY_CHOICES, verbose_name='Учебен ден',
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT,
        related_name='lessons', verbose_name='Пореден час',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT,
        related_name='lessons', verbose_name='Предмет',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        limit_choices_to={'role': 'teacher'},
        related_name='lessons', verbose_name='Преподавател',
    )
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT,
        related_name='lessons', verbose_name='Учебна зала',
    )

    class Meta:
        verbose_name = 'Час от разписанието'
        verbose_name_plural = 'Часове от разписанието'
        ordering = ['day_of_week', 'period__number']
        unique_together = ('version', 'day_of_week', 'period')

    def __str__(self):
        return (f'{self.version.school_class} — {self.get_day_of_week_display()}, '
                f'{self.period.number}. час: {self.subject}')

    @property
    def school_class(self):
        return self.version.school_class


# ── Тема на урока (за конкретна дата) ─────────────────────────

class LessonTopic(models.Model):
    """Тема на проведен урок. Свързва се с календарна дата, а не със
    седмичния шаблон — всяка седмица темата е различна."""

    date = models.DateField(verbose_name='Дата')
    school_class = models.ForeignKey(
        Class, on_delete=models.CASCADE,
        related_name='lesson_topics', verbose_name='Клас',
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT,
        related_name='lesson_topics', verbose_name='Пореден час',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT,
        related_name='lesson_topics', verbose_name='Предмет',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        limit_choices_to={'role': 'teacher'},
        related_name='lesson_topics', verbose_name='Преподавател',
    )
    topic = models.CharField(max_length=255, verbose_name='Тема на урока')
    note = models.TextField(blank=True, verbose_name='Забележка')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Въведена на')

    class Meta:
        verbose_name = 'Тема на урок'
        verbose_name_plural = 'Теми на уроци'
        ordering = ['-date', 'period__number']
        unique_together = ('date', 'school_class', 'period')

    def __str__(self):
        return f'{self.school_class} — {self.date:%d.%m.%Y}, {self.subject}: {self.topic}'


# ── Отсъствия на преподаватели ────────────────────────────────

class TeacherAbsence(models.Model):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    STATUS_CHOICES = [
        (PENDING, 'Заявено'),
        (APPROVED, 'Потвърдено'),
        (REJECTED, 'Отказано'),
    ]

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='teacher_absences', verbose_name='Преподавател',
    )
    start_date = models.DateField(verbose_name='Начална дата')
    end_date = models.DateField(verbose_name='Крайна дата')
    reason = models.CharField(max_length=200, blank=True, verbose_name='Причина')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default=PENDING, verbose_name='Статус',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Регистрирано на')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='registered_teacher_absences', verbose_name='Регистрирано от',
    )

    class Meta:
        verbose_name = 'Отсъствие на преподавател'
        verbose_name_plural = 'Отсъствия на преподаватели'
        ordering = ['-start_date']

    def __str__(self):
        return (f'{self.teacher.get_full_name()} — '
                f'{self.start_date:%d.%m.%Y} до {self.end_date:%d.%m.%Y}')

    def covers(self, day):
        return self.start_date <= day <= self.end_date


# ── Заместване за конкретна дата ──────────────────────────────

class Substitution(models.Model):
    """Заместване или отменен час за конкретна дата и учебен час.
    Не променя постоянното седмично разписание."""

    date = models.DateField(verbose_name='Дата')
    school_class = models.ForeignKey(
        Class, on_delete=models.CASCADE,
        related_name='substitutions', verbose_name='Клас',
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT,
        related_name='substitutions', verbose_name='Пореден час',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT,
        related_name='substitutions', verbose_name='Предмет',
    )
    original_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        limit_choices_to={'role': 'teacher'},
        related_name='substituted_lessons', verbose_name='Основен преподавател',
    )
    substitute_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        limit_choices_to={'role': 'teacher'},
        related_name='substitutions', verbose_name='Заместник',
    )
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, null=True, blank=True,
        related_name='substitutions', verbose_name='Учебна зала',
    )
    is_cancelled = models.BooleanField(default=False, verbose_name='Отменен час')
    note = models.CharField(max_length=200, blank=True, verbose_name='Забележка')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Създадено на')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_substitutions', verbose_name='Създадено от',
    )

    class Meta:
        verbose_name = 'Заместване'
        verbose_name_plural = 'Замествания'
        ordering = ['-date', 'period__number']
        unique_together = ('date', 'school_class', 'period')

    def __str__(self):
        if self.is_cancelled:
            return f'{self.school_class} — {self.date:%d.%m.%Y}, {self.period.number}. час: отменен'
        return (f'{self.school_class} — {self.date:%d.%m.%Y}, {self.period.number}. час: '
                f'{self.substitute_teacher.get_full_name() if self.substitute_teacher else "—"}')


# ── История на действията ─────────────────────────────────────

class TimetableLog(models.Model):
    ACTION_CHOICES = [
        ('lesson_create', 'Създаване на час'),
        ('lesson_update', 'Промяна на час'),
        ('lesson_delete', 'Изтриване на час'),
        ('publish', 'Публикуване на разписание'),
        ('substitution', 'Назначаване или промяна на заместник'),
        ('absence', 'Отсъствие на преподавател'),
        ('settings', 'Промяна на настройки'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='timetable_logs', verbose_name='Потребител',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name='Действие')
    description = models.CharField(max_length=255, verbose_name='Описание')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата и час')

    class Meta:
        verbose_name = 'Запис в дневника'
        verbose_name_plural = 'Дневник на разписанието'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%d.%m.%Y %H:%M} — {self.get_action_display()}'

    @classmethod
    def log(cls, user, action, description):
        cls.objects.create(user=user, action=action, description=description[:255])
