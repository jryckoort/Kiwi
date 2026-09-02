import logging

from celery import shared_task
from django.utils import timezone

from apps.accounts.models import Household

from .pricing import sync_all_prices
from .services import snapshot_net_worth

logger = logging.getLogger(__name__)


@shared_task
def fetch_daily_security_prices():
    """Refresh quotes for every security with a Yahoo symbol configured."""
    results = sync_all_prices()
    failures = [r for r in results if not r.ok]
    logger.info(
        "Cours mis à jour : %s succès, %s échecs", len(results) - len(failures), len(failures)
    )
    return (
        f"{len(results) - len(failures)} cours mis à jour, {len(failures)} en échec."
        if results
        else "Aucun titre avec un symbole Yahoo configuré."
    )


@shared_task
def snapshot_all_households_net_worth():
    """Runs daily (see CELERY_BEAT_SCHEDULE) but only actually snapshots once
    per calendar month, on the 1st, to build a monthly net-worth history.
    """
    today = timezone.localdate()
    if today.day != 1:
        return "Pas le 1er du mois, rien à faire."

    count = 0
    for household in Household.objects.all():
        snapshot_net_worth(household, today)
        count += 1
    logger.info("Net worth snapshotted for %s households on %s", count, today)
    return f"{count} foyers photographiés pour le {today}."
