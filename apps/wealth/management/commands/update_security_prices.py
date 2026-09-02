from django.core.management.base import BaseCommand

from apps.wealth.pricing import sync_all_prices


class Command(BaseCommand):
    help = "Fetch the latest Yahoo Finance quote for every security that has a symbol configured."

    def handle(self, *args, **options):
        results = sync_all_prices()
        if not results:
            self.stdout.write(
                self.style.WARNING("Aucun titre avec un symbole Yahoo configuré.")
            )
            return

        for result in results:
            if result.ok:
                self.stdout.write(self.style.SUCCESS(f"OK   {result.security} "))
            else:
                self.stdout.write(self.style.ERROR(f"ÉCHEC {result.security} : {result.error}"))

        failures = sum(1 for r in results if not r.ok)
        self.stdout.write(
            f"\n{len(results) - failures} cours mis à jour, {failures} en échec."
        )
