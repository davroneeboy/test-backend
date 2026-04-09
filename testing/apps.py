from django.apps import AppConfig


class TestingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "testing"
    verbose_name = "Тестирование"

    def ready(self):
        # В админке группы отображаются как «отделы» (один источник правды — Group).
        from django.contrib.auth.models import Group

        Group._meta.verbose_name = "Отдел"
        Group._meta.verbose_name_plural = "Отделы"
