from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0015_userprofile_patronymic"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="patronymic",
        ),
    ]
