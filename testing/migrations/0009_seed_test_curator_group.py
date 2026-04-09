# Группа «Куратор тестов»: тесты и вложенные вопросы/варианты (полный доступ),
# попытки только просмотр, отделы и пользователи (без удаления пользователей),
# без журнала действий админов и без прав на ответы/события сессии.

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


def seed(apps, schema_editor):
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=TEST_CURATOR_GROUP)
    perms = Permission.objects.filter(codename__in=_CURATOR_PERMISSION_CODENAMES)
    group.permissions.set(perms)


def unseed(apps, schema_editor):
    from django.contrib.auth.models import Group

    Group.objects.filter(name=TEST_CURATOR_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0008_rename_attempt_session_event_indexes"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
