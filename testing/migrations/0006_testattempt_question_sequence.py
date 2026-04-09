from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing", "0005_seed_audit_log_viewer_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="testattempt",
            name="question_sequence",
            field=models.JSONField(
                blank=True,
                help_text="Случайная перестановка при старте попытки; для next_question и согласованного порядка.",
                null=True,
                verbose_name="Порядок вопросов (id)",
            ),
        ),
    ]
