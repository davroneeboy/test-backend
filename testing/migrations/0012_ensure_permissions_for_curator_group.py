# Гарантирует Permission для моделей testing и заново назначает их группе куратора.

from django.apps import apps as django_apps
from django.contrib.auth.management import create_permissions
from django.db import DEFAULT_DB_ALIAS, migrations

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
    from django.contrib.auth.models import Group, Permission

    create_permissions(
        django_apps.get_app_config("testing"),
        verbosity=0,
        interactive=False,
        using=DEFAULT_DB_ALIAS,
        apps=django_apps,
    )
    group = Group.objects.filter(name=TEST_CURATOR_GROUP).first()
    if not group:
        return
    perms = Permission.objects.filter(codename__in=_CURATOR_PERMISSION_CODENAMES)
    group.permissions.set(perms)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0011_fix_curator_permissions_by_codename"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
