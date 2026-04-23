from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0014_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="patronymic",
            field=models.CharField(blank=True, max_length=150, verbose_name="Отчество"),
        ),
    ]
