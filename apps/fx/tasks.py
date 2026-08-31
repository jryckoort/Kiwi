import logging
from datetime import date
from decimal import Decimal

import requests
from celery import shared_task
from django.db import transaction

from .models import Currency, ExchangeRate

logger = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
REQUEST_TIMEOUT_SECONDS = 10


@shared_task
def fetch_daily_exchange_rates():
    """Fetch today's EUR-based rates for every currency already known to the
    app (i.e. referenced by a household, account, or security), so the
    ``fx.convert`` helper always has a recent rate to fall back on.
    """
    codes = list(Currency.objects.exclude(code="EUR").values_list("code", flat=True))
    if not codes:
        return "Aucune devise à mettre à jour."

    response = requests.get(
        FRANKFURTER_URL,
        params={"base": "EUR", "symbols": ",".join(codes)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    rate_date = date.fromisoformat(payload["date"])
    eur, _ = Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "symbol": "€"})

    created = 0
    with transaction.atomic():
        for code, rate in payload["rates"].items():
            currency = Currency.objects.filter(code=code).first()
            if not currency:
                continue
            _, was_created = ExchangeRate.objects.update_or_create(
                base_currency=eur,
                quote_currency=currency,
                date=rate_date,
                defaults={"rate": Decimal(str(rate))},
            )
            created += was_created

    logger.info("Fetched %s exchange rates for %s", len(payload["rates"]), rate_date)
    return f"{created} nouveaux taux enregistrés pour le {rate_date}."
