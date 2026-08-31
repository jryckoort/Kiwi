from django.core.management.base import BaseCommand

from apps.fx.tasks import fetch_daily_exchange_rates


class Command(BaseCommand):
    help = "Fetch today's exchange rates (EUR-based) from the Frankfurter API."

    def handle(self, *args, **options):
        result = fetch_daily_exchange_rates.run()
        self.stdout.write(self.style.SUCCESS(result))
