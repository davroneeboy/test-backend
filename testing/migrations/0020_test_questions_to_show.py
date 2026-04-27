from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0019_remove_questiongroup_title"),
    ]

    operations = [
        migrations.AddField(
            model_name="test",
            name="questions_to_show",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                verbose_name="Ko'rsatiladigan savollar soni",
                help_text=(
                    "Bo'sh — barcha savollar ko'rsatiladi. "
                    "Savol guruhlari bo'lmasa, har bir urinishda shu miqdor tasodifiy tanlanadi."
                ),
            ),
        ),
    ]
