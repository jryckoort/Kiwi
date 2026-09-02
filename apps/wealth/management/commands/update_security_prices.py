from django.core.management.base import BaseCommand, CommandError

from apps.wealth.pricing import sync_all_prices
from apps.wealth.providers import PriceUnavailable, available_providers, get_provider


class Command(BaseCommand):
    help = "Fetch the latest quote for every security that has a price symbol configured."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            help=(
                "Forcer un fournisseur pour ce lancement, sans toucher au .env "
                f"({', '.join(available_providers())}). Pratique pour en tester un."
            ),
        )

    def handle(self, *args, **options):
        provider = None
        if options.get("provider"):
            try:
                provider = get_provider(options["provider"])
            except PriceUnavailable as exc:
                raise CommandError(str(exc)) from exc

        results = sync_all_prices(provider=provider)
        if not results:
            self.stdout.write(
                self.style.WARNING("Aucun titre avec un symbole de cours configuré.")
            )
            return

        for result in results:
            if result.ok:
                self.stdout.write(self.style.SUCCESS(f"OK    {result.security}"))
            else:
                self.stdout.write(self.style.ERROR(f"ÉCHEC {result.security} : {result.error}"))

        failures = sum(1 for r in results if not r.ok)
        self.stdout.write(f"\n{len(results) - failures} cours mis à jour, {failures} en échec.")
