from decimal import Decimal

from django.utils import timezone

from .models import ExchangeRate


class ExchangeRateUnavailable(Exception):
    pass


def convert(amount: Decimal, from_code: str, to_code: str, on_date=None) -> Decimal:
    """Convert ``amount`` from one currency to another using the most recent
    known rate on or before ``on_date`` (defaults to today).

    Only looks up a direct rate or its inverse — it does not triangulate
    through a third currency. In practice rates are fetched against EUR, so
    this covers every EUR<->X conversion; a X<->Y conversion where neither is
    EUR is a known v2 follow-up.
    """
    if from_code == to_code:
        return amount

    on_date = on_date or timezone.localdate()

    direct = (
        ExchangeRate.objects.filter(
            base_currency_id=from_code, quote_currency_id=to_code, date__lte=on_date
        )
        .order_by("-date")
        .first()
    )
    if direct:
        return amount * direct.rate

    inverse = (
        ExchangeRate.objects.filter(
            base_currency_id=to_code, quote_currency_id=from_code, date__lte=on_date
        )
        .order_by("-date")
        .first()
    )
    if inverse:
        return amount / inverse.rate

    raise ExchangeRateUnavailable(
        f"Aucun taux de change {from_code}->{to_code} disponible au {on_date}"
    )
