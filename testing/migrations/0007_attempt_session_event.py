import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("testing", "0006_testattempt_question_sequence"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttemptSessionEvent",
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
                    "event_type",
                    models.CharField(
                        choices=[
                            (
                                "page_hidden",
                                "Вкладка скрыта (visibility)",
                            ),
                            ("page_visible", "Вкладка снова видна"),
                            ("window_blur", "Окно потеряло фокус"),
                            ("window_focus", "Окно получило фокус"),
                        ],
                        db_index=True,
                        max_length=32,
                        verbose_name="Тип события",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="Записано на сервере"
                    ),
                ),
                (
                    "client_timestamp",
                    models.DateTimeField(
                        blank=True,
                        help_text="ISO-время с браузера, если передано.",
                        null=True,
                        verbose_name="Время на клиенте",
                    ),
                ),
                (
                    "duration_away_ms",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Обычно при page_visible: сколько мс вкладка была скрыта.",
                        null=True,
                        verbose_name="Длительность «вне вкладки», мс",
                    ),
                ),
                (
                    "leave_count",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Накопительный номер ухода, если фронт ведёт счётчик.",
                        null=True,
                        verbose_name="Счётчик уходов (с клиента)",
                    ),
                ),
                ("meta", models.JSONField(blank=True, default=dict, verbose_name="Доп. данные")),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, null=True, verbose_name="IP"),
                ),
                (
                    "user_agent",
                    models.CharField(blank=True, max_length=512, verbose_name="User-Agent"),
                ),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session_events",
                        to="testing.testattempt",
                        verbose_name="Попытка",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempt_session_events",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Событие сессии попытки",
                "verbose_name_plural": "События сессий попыток",
                "ordering": ("created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="attemptsessionevent",
            index=models.Index(
                fields=["attempt", "created_at"],
                name="testing_att_attempt_e2cbf5_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="attemptsessionevent",
            index=models.Index(
                fields=["user", "created_at"],
                name="testing_att_user_id_7e8f1a_idx",
            ),
        ),
    ]
