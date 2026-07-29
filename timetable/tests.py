import datetime

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from school.models import Class, Subject, TeacherClassSubject
from students.models import ParentProfile, StudentProfile
from . import services
from .models import (
    ClassYearSetting, CurriculumEntry, Lesson, LessonTopic, Room, SchoolYear,
    Shift, Substitution, TeacherAbsence, TimetableVersion,
)


class TimetableBaseTest(TestCase):
    """Общи тестови данни: два класа, няколко предмета, зали и преподаватели."""

    def setUp(self):
        # Смените и периодите идват от миграцията с данни по подразбиране.
        self.year = SchoolYear.current()
        self.first_shift = Shift.objects.get(name='Първа смяна')
        self.second_shift = Shift.objects.get(name='Втора смяна')
        self.period1 = self.first_shift.periods.get(number=1)
        self.period2 = self.first_shift.periods.get(number=2)
        self.evening_period = self.second_shift.periods.get(number=1)

        self.class_a = Class.objects.create(name='10А')
        self.class_b = Class.objects.create(name='9Б')

        self.math = Subject.objects.create(name='Математика')
        self.english = Subject.objects.create(name='Английски език', is_foreign_language=True)
        self.german = Subject.objects.create(name='Немски език', is_foreign_language=True)
        self.pe = Subject.objects.create(name='Физическо възпитание', required_room_type='gym')

        self.room101 = Room.objects.create(name='101', capacity=26)
        self.room102 = Room.objects.create(name='102', capacity=26)
        self.gym = Room.objects.create(name='Салон', capacity=60, room_type='gym')

        self.teacher = self._create_teacher('ivan', 'Иван', 'Петров')
        self.teacher2 = self._create_teacher('maria', 'Мария', 'Иванова')

        TeacherClassSubject.objects.create(
            teacher=self.teacher, school_class=self.class_a, subject=self.math)
        TeacherClassSubject.objects.create(
            teacher=self.teacher, school_class=self.class_b, subject=self.math)
        TeacherClassSubject.objects.create(
            teacher=self.teacher2, school_class=self.class_a, subject=self.english)

        ClassYearSetting.objects.create(
            school_year=self.year, school_class=self.class_a, shift=self.first_shift,
            first_language=self.english, second_language=self.german)
        ClassYearSetting.objects.create(
            school_year=self.year, school_class=self.class_b, shift=self.first_shift)

        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_a,
            subject=self.math, hours_per_week=2)
        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_b,
            subject=self.math, hours_per_week=1)

        self.version_a = TimetableVersion.objects.create(
            school_year=self.year, school_class=self.class_a)
        self.version_b = TimetableVersion.objects.create(
            school_year=self.year, school_class=self.class_b)

    def _create_teacher(self, username, first_name, last_name):
        return User.objects.create_user(
            username=username, password='test1234', role='teacher',
            first_name=first_name, last_name=last_name)

    def _add_lesson(self, version, day=1, period=None, subject=None, teacher=None, room=None):
        return Lesson.objects.create(
            version=version, day_of_week=day, period=period or self.period1,
            subject=subject or self.math, teacher=teacher or self.teacher,
            room=room or self.room101)


class LessonConflictTests(TimetableBaseTest):

    def test_valid_lesson_has_no_errors(self):
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.math, self.teacher, self.room101)
        self.assertEqual(errors, [])

    def test_class_conflict(self):
        self._add_lesson(self.version_a)
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.math, self.teacher, self.room102)
        self.assertTrue(any('вече има час' in error for error in errors))

    def test_teacher_conflict_across_classes(self):
        self._add_lesson(self.version_b)
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.math, self.teacher, self.room102)
        self.assertTrue(any('вече води час' in error for error in errors))

    def test_room_conflict_across_classes(self):
        self._add_lesson(self.version_b, teacher=self.teacher, room=self.room101)
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.english, self.teacher2, self.room101)
        self.assertTrue(any('е заета от клас' in error for error in errors))

    def test_shift_conflict(self):
        """Час извън смяната на класа не се допуска."""
        errors = services.check_lesson(
            self.version_a, 1, self.evening_period, self.math, self.teacher, self.room101)
        self.assertTrue(any('извън' in error for error in errors))

    def test_teacher_must_be_assigned_to_subject(self):
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.english, self.teacher, self.room101)
        self.assertTrue(any('не е назначен' in error for error in errors))

    def test_room_type_must_match_subject(self):
        TeacherClassSubject.objects.create(
            teacher=self.teacher, school_class=self.class_a, subject=self.pe)
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.pe, self.teacher, self.room101)
        self.assertTrue(any('изисква' in error for error in errors))

        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.pe, self.teacher, self.gym)
        self.assertEqual(errors, [])

    def test_editing_a_lesson_ignores_itself(self):
        lesson = self._add_lesson(self.version_a)
        errors = services.check_lesson(
            self.version_a, 1, self.period1, self.math, self.teacher, self.room101,
            exclude_lesson=lesson)
        self.assertEqual(errors, [])

    def test_curriculum_capacity(self):
        self._add_lesson(self.version_a, day=1, period=self.period1)
        self._add_lesson(self.version_a, day=2, period=self.period1)
        errors = services.check_curriculum_capacity(self.version_a, self.math)
        self.assertTrue(any('запълнен' in error for error in errors))

    def test_subject_outside_curriculum(self):
        errors = services.check_curriculum_capacity(self.version_a, self.english)
        self.assertTrue(any('не е в седмичния хорариум' in error for error in errors))


class PublishTests(TimetableBaseTest):

    def _complete_class_a(self):
        """Разписание, което точно покрива хорариума на 10А."""
        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_a,
            subject=self.english, hours_per_week=3)
        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_a,
            subject=self.german, hours_per_week=2)
        TeacherClassSubject.objects.create(
            teacher=self.teacher2, school_class=self.class_a, subject=self.german)

        self._add_lesson(self.version_a, day=1, period=self.period1)
        self._add_lesson(self.version_a, day=2, period=self.period1)
        for day in (1, 2, 3):
            self._add_lesson(self.version_a, day=day, period=self.period2,
                             subject=self.english, teacher=self.teacher2, room=self.room102)
        for day in (4, 5):
            self._add_lesson(self.version_a, day=day, period=self.period2,
                             subject=self.german, teacher=self.teacher2, room=self.room102)

    def test_complete_timetable_is_valid(self):
        self._complete_class_a()
        self.assertEqual(services.validate_for_publish(self.version_a), [])

    def test_cannot_publish_with_missing_hours(self):
        self._add_lesson(self.version_a, day=1, period=self.period1)
        errors = services.validate_for_publish(self.version_a)
        self.assertTrue(any('липсват' in error for error in errors))

    def test_cannot_publish_with_extra_hours(self):
        for day in (1, 2, 3):
            self._add_lesson(self.version_a, day=day, period=self.period1)
        errors = services.validate_for_publish(self.version_a)
        self.assertTrue(any('в повече' in error for error in errors))

    def test_first_language_must_have_more_hours(self):
        self._complete_class_a()
        # Разменяме хорариума: първият език остава с по-малко часове от втория.
        CurriculumEntry.objects.filter(
            school_class=self.class_a, subject=self.english).update(hours_per_week=2)
        CurriculumEntry.objects.filter(
            school_class=self.class_a, subject=self.german).update(hours_per_week=3)
        errors = services.validate_for_publish(self.version_a)
        self.assertTrue(any('с повече часове от втория' in error for error in errors))

    def test_exactly_two_foreign_languages(self):
        self._complete_class_a()
        third = Subject.objects.create(name='Френски език', is_foreign_language=True)
        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_a,
            subject=third, hours_per_week=2)
        errors = services.validate_for_publish(self.version_a)
        self.assertTrue(any('точно два чужди езика' in error for error in errors))

    def test_publish_succeeds_and_archives_previous(self):
        self._complete_class_a()
        self.assertEqual(services.publish(self.version_a, self.teacher), [])

        self.version_a.refresh_from_db()
        self.assertEqual(self.version_a.status, TimetableVersion.PUBLISHED)
        self.assertIsNotNone(self.version_a.published_at)

        # Нова чернова — копие на публикуваното.
        draft = services.get_or_create_draft(self.year, self.class_a, self.teacher)
        self.assertEqual(draft.status, TimetableVersion.DRAFT)
        self.assertEqual(draft.lessons.count(), self.version_a.lessons.count())

        # Публикуването на черновата архивира старата версия.
        self.assertEqual(services.publish(draft, self.teacher), [])
        self.version_a.refresh_from_db()
        self.assertEqual(self.version_a.status, TimetableVersion.ARCHIVED)
        self.assertEqual(
            TimetableVersion.objects.filter(
                school_class=self.class_a, status=TimetableVersion.PUBLISHED).count(), 1)

    def test_draft_changes_are_not_visible_before_publishing(self):
        self._complete_class_a()
        services.publish(self.version_a, self.teacher)
        published_count = services.published_version(self.year, self.class_a).lessons.count()

        draft = services.get_or_create_draft(self.year, self.class_a, self.teacher)
        draft.lessons.first().delete()

        self.assertEqual(
            services.published_version(self.year, self.class_a).lessons.count(),
            published_count)


class SubstitutionTests(TimetableBaseTest):

    def setUp(self):
        super().setUp()
        # Понеделник от текущата седмица — учебен ден.
        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())

        self.version_a.status = TimetableVersion.PUBLISHED
        self.version_a.save()
        self.lesson = self._add_lesson(self.version_a, day=1, period=self.period1)

    def test_busy_teacher_cannot_substitute(self):
        self.version_b.status = TimetableVersion.PUBLISHED
        self.version_b.save()
        self._add_lesson(self.version_b, day=1, period=self.period1,
                         teacher=self.teacher2, room=self.room102)

        errors = services.check_substitute(
            self.year, self.monday, self.period1, self.teacher2,
            original_teacher=self.teacher)
        self.assertTrue(any('вече има час' in error for error in errors))

    def test_absent_teacher_cannot_substitute(self):
        TeacherAbsence.objects.create(
            teacher=self.teacher2, start_date=self.monday, end_date=self.monday,
            status=TeacherAbsence.APPROVED)
        errors = services.check_substitute(
            self.year, self.monday, self.period1, self.teacher2,
            original_teacher=self.teacher)
        self.assertTrue(any('отсъстващ' in error for error in errors))

    def test_free_teacher_can_substitute(self):
        errors = services.check_substitute(
            self.year, self.monday, self.period1, self.teacher2,
            original_teacher=self.teacher)
        self.assertEqual(errors, [])

    def test_already_assigned_substitute_can_be_saved_again(self):
        """Собственото заместване не бива да се брои за конфликт при промяна."""
        Substitution.objects.create(
            date=self.monday, school_class=self.class_a, period=self.period1,
            subject=self.math, original_teacher=self.teacher,
            substitute_teacher=self.teacher2)

        errors = services.check_substitute(
            self.year, self.monday, self.period1, self.teacher2,
            original_teacher=self.teacher, school_class=self.class_a)
        self.assertEqual(errors, [])

        candidates = services.available_substitutes(
            self.year, self.monday, self.period1, self.math,
            exclude_teacher=self.teacher, school_class=self.class_a)
        self.assertIn(self.teacher2, [row['teacher'] for row in candidates])

    def test_available_substitutes_prefers_same_subject(self):
        third = self._create_teacher('petar', 'Петър', 'Колев')
        TeacherClassSubject.objects.create(
            teacher=third, school_class=self.class_b, subject=self.math)

        candidates = services.available_substitutes(
            self.year, self.monday, self.period1, self.math,
            exclude_teacher=self.teacher)
        self.assertTrue(candidates[0]['teaches_subject'])
        self.assertEqual(candidates[0]['teacher'], third)

    def test_substitution_does_not_change_weekly_timetable(self):
        Substitution.objects.create(
            date=self.monday, school_class=self.class_a, period=self.period1,
            subject=self.math, original_teacher=self.teacher,
            substitute_teacher=self.teacher2)

        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.teacher, self.teacher)

        rows = services.lessons_on_date(self.year, self.monday, school_class=self.class_a)
        self.assertEqual(rows[0]['teacher'], self.teacher2)

    def test_affected_lessons_for_absence(self):
        absence = TeacherAbsence.objects.create(
            teacher=self.teacher, start_date=self.monday, end_date=self.monday,
            status=TeacherAbsence.APPROVED)
        rows = services.affected_lessons(absence, self.year)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['lesson'], self.lesson)

    def test_topic_only_for_own_or_substituted_lesson(self):
        self.assertIsNotNone(services.can_teach_on_date(
            self.teacher, self.class_a, self.period1, self.monday))
        self.assertIsNone(services.can_teach_on_date(
            self.teacher2, self.class_a, self.period1, self.monday))

        Substitution.objects.create(
            date=self.monday, school_class=self.class_a, period=self.period1,
            subject=self.math, original_teacher=self.teacher,
            substitute_teacher=self.teacher2)

        self.assertIsNotNone(services.can_teach_on_date(
            self.teacher2, self.class_a, self.period1, self.monday))
        self.assertIsNone(services.can_teach_on_date(
            self.teacher, self.class_a, self.period1, self.monday))

    def test_cancelled_lesson_has_no_topic(self):
        Substitution.objects.create(
            date=self.monday, school_class=self.class_a, period=self.period1,
            subject=self.math, original_teacher=self.teacher, is_cancelled=True)
        self.assertIsNone(services.can_teach_on_date(
            self.teacher, self.class_a, self.period1, self.monday))


class AccessTests(TimetableBaseTest):
    """Правата за достъп се проверяват на сървъра, а не само в интерфейса."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='admin1', password='test1234', role='admin',
            first_name='Админ', last_name='Админов')
        self.student = User.objects.create_user(
            username='student1', password='test1234', role='student',
            first_name='Ученик', last_name='Ученков')

    def test_admin_pages_open(self):
        self.client.force_login(self.admin)
        for url_name in ['timetable_dashboard', 'timetable_settings', 'room_list',
                         'timetable_class_settings', 'timetable_curriculum',
                         'timetable_grid', 'timetable_teacher_grid',
                         'teacher_absence_list', 'substitution_day', 'timetable_log']:
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_student_cannot_open_admin_pages(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('timetable_grid')).status_code, 403)
        self.assertEqual(self.client.get(reverse('substitution_day')).status_code, 403)

    def test_teacher_cannot_open_admin_pages(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('timetable_dashboard')).status_code, 403)

    def test_empty_substitute_shows_message_instead_of_error(self):
        """Натискане на „Назначи заместник“ без избран учител не бива да чупи страницата."""
        self.version_a.status = TimetableVersion.PUBLISHED
        self.version_a.save()
        lesson = self._add_lesson(self.version_a)
        monday = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())

        self.client.force_login(self.admin)
        response = self.client.post(reverse('substitution_save'), {
            'lesson': lesson.pk, 'date': monday.isoformat(),
            'action': 'assign', 'substitute_teacher': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Substitution.objects.count(), 0)

    def test_cancel_and_clear_substitution(self):
        self.version_a.status = TimetableVersion.PUBLISHED
        self.version_a.save()
        lesson = self._add_lesson(self.version_a)
        monday = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
        self.client.force_login(self.admin)

        self.client.post(reverse('substitution_save'), {
            'lesson': lesson.pk, 'date': monday.isoformat(), 'action': 'cancel'})
        self.assertTrue(Substitution.objects.get(date=monday).is_cancelled)

        self.client.post(reverse('substitution_save'), {
            'lesson': lesson.pk, 'date': monday.isoformat(), 'action': 'clear'})
        self.assertEqual(Substitution.objects.count(), 0)

    def test_empty_teacher_in_absence_form_shows_message(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('teacher_absence_list'), {
            'teacher': '', 'start_date': '2026-09-01', 'end_date': '2026-09-02',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeacherAbsence.objects.count(), 0)

    def test_lesson_add_without_class_does_not_crash(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('lesson_add'))
        self.assertEqual(response.status_code, 302)

    def test_lesson_in_published_version_cannot_be_edited(self):
        self.version_a.status = TimetableVersion.PUBLISHED
        self.version_a.save()
        lesson = self._add_lesson(self.version_a)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('lesson_edit', args=[lesson.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Lesson.objects.count(), 1)


class AdminSetupTests(TimetableBaseTest):
    """Формите за зали, смени, настройки на класове и хорариум."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='admin1', password='test1234', role='admin',
            first_name='Админ', last_name='Админов')
        self.client.force_login(self.admin)

    def test_create_room(self):
        self.client.post(reverse('room_create'), {
            'name': '305', 'capacity': 24, 'room_type': 'lab', 'is_active': 'on'})
        room = Room.objects.get(name='305')
        self.assertEqual(room.room_type, 'lab')
        self.assertTrue(room.is_active)

    def test_room_in_timetable_is_deactivated_not_deleted(self):
        self._add_lesson(self.version_a, room=self.room101)
        self.client.post(reverse('room_delete', args=[self.room101.pk]))
        self.room101.refresh_from_db()
        self.assertFalse(self.room101.is_active)

    def test_add_school_year(self):
        self.client.post(reverse('timetable_settings'), {
            'action': 'add_year', 'name': '2030/2031'})
        year = SchoolYear.objects.get(name='2030/2031')
        self.assertTrue(year.is_current)
        # Текущата учебна година е само една.
        self.assertEqual(SchoolYear.objects.filter(is_current=True).count(), 1)

    def test_edit_period_times(self):
        self.client.post(reverse('timetable_settings'), {
            'action': 'save_periods', 'shift': self.first_shift.pk,
            f'start_{self.period1.pk}': '08:00', f'end_{self.period1.pk}': '08:40'})
        self.period1.refresh_from_db()
        self.assertEqual(self.period1.start_time.strftime('%H:%M'), '08:00')

    def test_class_settings_reject_same_language_twice(self):
        self.client.post(reverse('timetable_class_settings'), {
            'school_class': self.class_b.pk, 'year': self.year.pk,
            'shift': self.first_shift.pk,
            'first_language': self.english.pk, 'second_language': self.english.pk})
        setting = ClassYearSetting.objects.get(school_class=self.class_b)
        self.assertIsNone(setting.first_language)

    def test_curriculum_entry_saved(self):
        self.client.post(reverse('timetable_curriculum'), {
            'school_class': self.class_a.pk, 'year': self.year.pk,
            'subject': self.english.pk, 'hours_per_week': 5})
        entry = CurriculumEntry.objects.get(school_class=self.class_a, subject=self.english)
        self.assertEqual(entry.hours_per_week, 5)


class NotificationTests(TimetableBaseTest):
    """Известяване по имейл при отмяна на час или назначаване на заместник."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='admin1', password='test1234', role='admin',
            first_name='Админ', last_name='Админов')

        student_user = User.objects.create_user(
            username='student1', password='test1234', role='student',
            first_name='Ученик', last_name='Ученков', email='uchenik@example.com')
        self.student_profile = StudentProfile.objects.create(
            user=student_user, school_class=self.class_a)

        parent_user = User.objects.create_user(
            username='parent1', password='test1234', role='parent',
            first_name='Родител', last_name='Родителев', email='roditel@example.com')
        parent_profile = ParentProfile.objects.create(user=parent_user)
        parent_profile.children.add(self.student_profile)

        self.version_a.status = TimetableVersion.PUBLISHED
        self.version_a.save()
        self.lesson = self._add_lesson(self.version_a, day=1, period=self.period1)

        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())
        self.client.force_login(self.admin)

    def test_cancel_sends_email_to_student_and_parent(self):
        self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(),
            'action': 'cancel', 'note': 'Болен учител',
        })
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        # Получателите са в BCC — скрити едни от други; „До“ е служебният адрес.
        self.assertIn('uchenik@example.com', sent.bcc)
        self.assertIn('roditel@example.com', sent.bcc)
        self.assertIn('отменен', sent.subject.lower())
        self.assertIn('Болен учител', sent.body)

    def test_substitution_sends_email(self):
        self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(),
            'action': 'assign', 'substitute_teacher': self.teacher2.pk,
        })
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn('uchenik@example.com', sent.bcc)
        self.assertIn('roditel@example.com', sent.bcc)
        self.assertIn(self.teacher2.get_full_name(), sent.body)

    def test_clear_does_not_send_email(self):
        """Връщането към нормалното разписание не поражда ново известие."""
        Substitution.objects.create(
            date=self.monday, school_class=self.class_a, period=self.period1,
            subject=self.math, original_teacher=self.teacher,
            substitute_teacher=self.teacher2)
        mail.outbox.clear()

        self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(), 'action': 'clear'})
        self.assertEqual(len(mail.outbox), 0)

    def test_student_without_email_still_notifies_parent(self):
        self.student_profile.user.email = ''
        self.student_profile.user.save()

        self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(), 'action': 'cancel'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, ['roditel@example.com'])

    def test_sends_a_single_batched_email_for_the_whole_class(self):
        """Съдържанието е едно и също за целия клас — трябва да е ЕДНО
        писмо с всички получатели в BCC, а не по едно писмо на ученик
        (последното отваря отделна SMTP връзка за всеки и отнема над
        20 секунди за клас с 25+ ученика)."""
        second_user = User.objects.create_user(
            username='student2', password='test1234', role='student',
            first_name='Втори', last_name='Ученков', email='vtori@example.com')
        second_profile = StudentProfile.objects.create(
            user=second_user, school_class=self.class_a)
        second_parent = User.objects.create_user(
            username='parent2', password='test1234', role='parent',
            first_name='Родител', last_name='Втори', email='roditel2@example.com')
        ParentProfile.objects.create(user=second_parent).children.add(second_profile)

        self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(), 'action': 'cancel'})

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(
            set(sent.bcc),
            {'uchenik@example.com', 'roditel@example.com',
             'vtori@example.com', 'roditel2@example.com'})
        # „До“ е служебният адрес — реалните получатели са скрити в BCC.
        self.assertEqual(sent.to, [sent.from_email])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='invalid.nonexistent.test.local',
        EMAIL_TIMEOUT=2,
    )
    def test_unreachable_mail_server_does_not_crash_the_request(self):
        """Истински SMTP бекенд с несъществуващ хост — fail_silently трябва
        да погълне грешката, без да чупи заявката."""
        response = self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(), 'action': 'cancel'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_family_without_any_email_is_skipped_silently(self):
        self.student_profile.user.email = ''
        self.student_profile.user.save()
        parent_profile = ParentProfile.objects.get(children=self.student_profile)
        parent_profile.user.email = ''
        parent_profile.user.save()

        response = self.client.post(reverse('substitution_save'), {
            'lesson': self.lesson.pk, 'date': self.monday.isoformat(), 'action': 'cancel'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)


class FlowTests(TimetableBaseTest):
    """Целият поток през изгледите: чернова → часове → публикуване →
    преглед от ученик, тема на урок и заместване."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='admin1', password='test1234', role='admin',
            first_name='Админ', last_name='Админов')

        student_user = User.objects.create_user(
            username='student1', password='test1234', role='student',
            first_name='Ученик', last_name='Ученков')
        StudentProfile.objects.create(user=student_user, school_class=self.class_a)
        self.student_user = student_user

        # Хорариум на 10А: математика 2 ч., първи език 3 ч., втори език 2 ч.
        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_a,
            subject=self.english, hours_per_week=3)
        CurriculumEntry.objects.create(
            school_year=self.year, school_class=self.class_a,
            subject=self.german, hours_per_week=2)
        TeacherClassSubject.objects.create(
            teacher=self.teacher2, school_class=self.class_a, subject=self.german)

        self.version_a.delete()
        self.version_b.delete()

        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())

    def _add_lesson_via_view(self, day, period, subject=None, teacher=None, room=None):
        return self.client.post(reverse('lesson_add'), {
            'school_class': self.class_a.pk, 'year': self.year.pk,
            'day_of_week': day, 'period': period.pk,
            'subject': (subject or self.math).pk,
            'teacher': (teacher or self.teacher).pk,
            'room': (room or self.room101).pk,
        })

    def test_full_flow(self):
        self.client.force_login(self.admin)

        # 1. Отваряне на чернова.
        self.client.post(reverse('timetable_start_editing', args=[self.class_a.pk]),
                         {'year': self.year.pk})
        draft = services.draft_version(self.year, self.class_a)
        self.assertIsNotNone(draft)

        # 2. Добавяне на часовете по хорариум.
        self._add_lesson_via_view(1, self.period1)
        self._add_lesson_via_view(2, self.period1)
        for day in (1, 2, 3):
            self._add_lesson_via_view(day, self.period2, subject=self.english,
                                      teacher=self.teacher2, room=self.room102)
        for day in (4, 5):
            self._add_lesson_via_view(day, self.period2, subject=self.german,
                                      teacher=self.teacher2, room=self.room102)
        self.assertEqual(draft.lessons.count(), 7)

        # 3. Трети час по математика надхвърля хорариума и не се записва.
        self._add_lesson_via_view(3, self.period1)
        self.assertEqual(draft.lessons.count(), 7)

        # 4. Публикуване.
        self.client.post(reverse('timetable_publish', args=[draft.pk]), {'year': self.year.pk})
        draft.refresh_from_db()
        self.assertEqual(draft.status, TimetableVersion.PUBLISHED)

        # 5. Ученикът вижда публикуваното разписание.
        self.client.force_login(self.student_user)
        response = self.client.get(reverse('student_schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Математика')

        # 6. Учителят вижда своето разписание.
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('teacher_schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '10А')

        # 7. Учителят въвежда тема на урока за конкретна дата.
        self.client.post(reverse('teacher_lesson_topics'), {
            'date': self.monday.isoformat(), 'school_class': self.class_a.pk,
            'period': self.period1.pk, 'topic': 'Квадратни уравнения',
        })
        topic = LessonTopic.objects.get(date=self.monday, school_class=self.class_a)
        self.assertEqual(topic.topic, 'Квадратни уравнения')
        self.assertEqual(topic.subject, self.math)

        # 8. Друг учител не може да въвежда тема за чужд час.
        self.client.force_login(self.teacher2)
        self.client.post(reverse('teacher_lesson_topics'), {
            'date': self.monday.isoformat(), 'school_class': self.class_a.pk,
            'period': self.period1.pk, 'topic': 'Чужда тема',
        })
        topic.refresh_from_db()
        self.assertEqual(topic.topic, 'Квадратни уравнения')

        # 9. Учителят заявява отсъствие.
        self.client.force_login(self.teacher)
        self.client.post(reverse('teacher_my_absences'), {
            'start_date': self.monday.isoformat(),
            'end_date': self.monday.isoformat(), 'reason': 'Болничен',
        })
        absence = TeacherAbsence.objects.get(teacher=self.teacher)
        self.assertEqual(absence.status, TeacherAbsence.PENDING)

        # 10. Администраторът назначава заместник за конкретната дата.
        lesson = Lesson.objects.get(
            version__status=TimetableVersion.PUBLISHED, day_of_week=1, period=self.period1)
        self.client.force_login(self.admin)
        self.client.post(reverse('substitution_save'), {
            'lesson': lesson.pk, 'date': self.monday.isoformat(),
            'action': 'assign', 'substitute_teacher': self.teacher2.pk,
        })
        substitution = Substitution.objects.get(date=self.monday, school_class=self.class_a)
        self.assertEqual(substitution.substitute_teacher, self.teacher2)

        # Седмичното разписание остава непроменено.
        lesson.refresh_from_db()
        self.assertEqual(lesson.teacher, self.teacher)

        # 11. Заместникът вижда заместването си.
        self.client.force_login(self.teacher2)
        response = self.client.get(reverse('teacher_substitutions'))
        self.assertContains(response, '10А')
