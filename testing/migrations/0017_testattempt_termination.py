from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0016_remove_userprofile_patronymic"),
    ]

    operations = [
        migrations.AddField(
            model_name="testattempt",
            name="termination_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("tab_switch", "Boshqa vkladkaga o'tildi"),
                    ("window_blur", "Boshqa ilovaga o'tildi"),
                ],
                max_length=20,
                verbose_name="Tugatilish sababi",
            ),
        ),
    ]
