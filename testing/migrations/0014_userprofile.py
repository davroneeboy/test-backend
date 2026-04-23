import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0013_curator_group_include_auth_permissions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "region_type",
                    models.CharField(
                        choices=[
                            ("markaziy", "Марказий аппарат"),
                            ("viloyat", "Вилоят"),
                        ],
                        default="markaziy",
                        max_length=20,
                        verbose_name="Тип региона",
                    ),
                ),
                (
                    "viloyat",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("andijon", "Андижон вилояти"),
                            ("buxoro", "Бухоро вилояти"),
                            ("fargona", "Фарғона вилояти"),
                            ("jizzax", "Жиззах вилояти"),
                            ("qashqadaryo", "Қашқадарё вилояти"),
                            ("navoiy", "Навоий вилояти"),
                            ("namangan", "Наманган вилояти"),
                            ("samarqand", "Самарқанд вилояти"),
                            ("sirdaryo", "Сирдарё вилояти"),
                            ("surxondaryo", "Сурхондарё вилояти"),
                            ("toshkent_vil", "Тошкент вилояти"),
                            ("xorazm", "Хоразм вилояти"),
                            ("toshkent_sh", "Тошкент шаҳри"),
                            ("qoraqalpogiston", "Қорақалпоғистон Республикаси"),
                        ],
                        max_length=30,
                        verbose_name="Вилоят",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Профиль пользователя",
                "verbose_name_plural": "Профили пользователей",
            },
        ),
    ]
