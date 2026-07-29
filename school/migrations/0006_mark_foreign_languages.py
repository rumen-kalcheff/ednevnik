from django.db import migrations


# Началното отбелязване на чуждите езици: всеки предмет „… език“ без
# българския. Администраторът може да промени отметката от формата на предмета.
NOT_FOREIGN = ['Български език', 'Български език и литература']


def mark_foreign_languages(apps, schema_editor):
    Subject = apps.get_model('school', 'Subject')
    Subject.objects.filter(
        name__endswith='език'
    ).exclude(name__in=NOT_FOREIGN).update(is_foreign_language=True)


def unmark_foreign_languages(apps, schema_editor):
    Subject = apps.get_model('school', 'Subject')
    Subject.objects.update(is_foreign_language=False)


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0005_subject_is_foreign_language'),
    ]

    operations = [
        migrations.RunPython(mark_foreign_languages, unmark_foreign_languages),
    ]
