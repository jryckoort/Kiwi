import logging

from celery import shared_task
from django.utils import timezone

from apps.accounts.models import Household

from .services import snapshot_net_worth

logger = logging.getLogger(__name__)


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
