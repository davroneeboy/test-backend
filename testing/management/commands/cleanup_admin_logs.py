"""
Удаляет записи AdminActionLog старше заданного числа дней.

Использование:
    python manage.py cleanup_admin_logs            # удалить старше 365 дней
    python manage.py cleanup_admin_logs --days 90  # удалить старше 90 дней
    python manage.py cleanup_admin_logs --dry-run  # показать сколько будет удалено
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Удаляет записи AdminActionLog старше заданного числа дней"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Удалить записи старше N дней (по умолчанию 365)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать количество записей без удаления",
        )

    def handle(self, *args, **options):
        from testing.models import AdminActionLog

        days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timezone.timedelta(days=days)

        qs = AdminActionLog.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if count == 0:
            self.stdout.write(f"Нет записей старше {days} дней.")
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] Будет удалено {count} записей старше {days} дней "
                    f"(до {cutoff.strftime('%d.%m.%Y %H:%M')})."
                )
            )
            return

        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Удалено {deleted} записей AdminActionLog старше {days} дней."
            )
        )
