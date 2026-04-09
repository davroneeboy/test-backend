# Группа для просмотра отдельного журнала действий админов.

from django.db import migrations


AUDIT_LOG_VIEWERS_GROUP = "Просмотр логов админов"


def seed_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=AUDIT_LOG_VIEWERS_GROUP)


def unseed_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=AUDIT_LOG_VIEWERS_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("testing", "0004_admin_action_log"),
    ]

    operations = [
        migrations.RunPython(seed_group, unseed_group),
    ]
