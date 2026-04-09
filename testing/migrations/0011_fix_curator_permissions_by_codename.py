# Назначение прав куратору по codename (если 0010 отработал с пустым списком).

from django.db import migrations

TEST_CURATOR_GROUP = "Куратор тестов"

_CURATOR_PERMISSION_CODENAMES = (
    "add_test",
    "change_test",
    "delete_test",
    "view_test",
    "add_question",
    "change_question",
    "delete_question",
    "view_question",
    "add_answeroption",
    "change_answeroption",
    "delete_answeroption",
    "view_answeroption",
    "view_testattempt",
    "add_group",
    "change_group",
    "view_group",
    "add_user",
    "change_user",
    "view_user",
)


def forwards(apps, schema_editor):
    # Реальные модели: исторический Permission в RunPython не всегда отрабатывает filter по codename.
    from django.contrib.auth.models import Group, Permission

    group = Group.objects.filter(name=TEST_CURATOR_GROUP).first()
    if not group:
        return
    perms = Permission.objects.filter(codename__in=_CURATOR_PERMISSION_CODENAMES)
    group.permissions.set(perms)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0010_reseed_test_curator_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
