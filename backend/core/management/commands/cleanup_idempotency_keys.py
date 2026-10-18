from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import IdempotencyKey


class Command(BaseCommand):
    help = "Remove chaves de idempotência expiradas."

    def handle(self, *args, **options):
        deleted, _ = IdempotencyKey.objects.filter(
            expires_at__lte=timezone.now()
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(f"{deleted} chave(s) expirada(s) removida(s).")
        )
