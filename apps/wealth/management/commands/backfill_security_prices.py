from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError

from apps.wealth.models import Security
from apps.wealth.pricing import backfill_security_history
from apps.wealth.providers import PriceUnavailable, available_providers, get_provider


class Command(BaseCommand):
    help = (
        "Backfill historical Yahoo Finance closes. Useful to populate the "
        "31/12/2025 reference price used by the Belgian capital gains tax."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--since", required=True, help="Date de début au format YYYY-MM-DD."
        )
        parser.add_argument("--until", help="Date de fin (par défaut aujourd'hui).")
        parser.add_argument(
            "--identifier", help="Ne traiter qu'un titre (son ISIN/ticker Kiwi)."
        )
        parser.add_argument(
            "--provider",
            help=(
                "Forcer un fournisseur pour ce lancement "
                f"({', '.join(available_providers())})."
            ),
        )

    def handle(self, *args, **options):
        try:
            start = datetime.strptime(options["since"], "%Y-%m-%d").date()
            end = (
                datetime.strptime(options["until"], "%Y-%m-%d").date()
                if options.get("until")
                else date.today()
            )
        except ValueError as exc:
            raise CommandError(f"Date invalide : {exc}") from exc

        if start > end:
            raise CommandError("--since doit précéder --until.")

        securities = Security.objects.exclude(price_symbol="")
        if options.get("identifier"):
            securities = securities.filter(identifier=options["identifier"])
        if not securities.exists():
            raise CommandError("Aucun titre correspondant avec un symbole Yahoo configuré.")

        provider = None
        if options.get("provider"):
            try:
                provider = get_provider(options["provider"])
            except PriceUnavailable as exc:
                raise CommandError(str(exc)) from exc

        for security in securities:
            result = backfill_security_history(security, start, end, provider=provider)
            if result.ok:
                self.stdout.write(
                    self.style.SUCCESS(f"OK   {security} : {result.stored} cours enregistrés")
                )
            else:
                self.stdout.write(self.style.ERROR(f"ÉCHEC {security} : {result.error}"))
