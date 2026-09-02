"""Fetching and storing security prices.

The market-data source is pluggable (see ``apps/wealth/providers``) and chosen
by config, so this module never imports a provider library directly. Tests
pass a fake provider in; production passes none and the configured one is used.

Two rules protect the valuations built on these prices:

* a quote whose currency disagrees with ``Security.currency`` is refused
  rather than stored — a USD price against a EUR-denominated holding would
  silently inflate net worth. Providers that don't report a currency (Stooq)
  return ``None`` and the configured currency is trusted;
* one failing security never aborts the run, and the reason is written to
  ``Security.last_sync_error`` so a self-hosted user sees it in the app
  instead of having to read Celery logs.
"""

import logging
from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from .models import PriceSnapshot, Security
from .providers import PriceUnavailable, provider_for

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    security: Security
    stored: int = 0
    error: str = ""

    @property
    def ok(self):
        return not self.error


def _check_currency(security, quote_currency):
    """Refuse a quote denominated in something other than the security's currency.

    Providers happily serve the same instrument from several listings; storing
    a price in the wrong currency would silently distort every valuation built
    on it. ``None`` means the provider didn't say, so we trust the config.
    """
    if not quote_currency:
        return
    if quote_currency.upper() != security.currency_id.upper():
        raise PriceUnavailable(
            f"Devise incohérente : le fournisseur cote {security.price_symbol} en "
            f"{quote_currency.upper()}, or le titre est enregistré en {security.currency_id}"
        )


def _record_failure(security, message):
    security.last_sync_error = message[:255]
    security.save(update_fields=["last_sync_error"])
    logger.warning("Échec de synchro pour %s : %s", security, message)


def _record_success(security):
    security.last_synced_at = timezone.now()
    security.last_sync_error = ""
    security.save(update_fields=["last_synced_at", "last_sync_error"])


def _store(security, quote_date, price):
    # Providers validate as they parse, but this is money: re-check here so a
    # provider that forgets can't write a nonsense price into a valuation.
    if price is None or price <= 0:
        raise PriceUnavailable(f"Cours non exploitable : {price}")
    PriceSnapshot.objects.update_or_create(
        security=security, date=quote_date, defaults={"price": price}
    )


def sync_security_price(security, provider=None):
    """Fetch and store the latest quote for one security."""
    result = SyncResult(security=security)

    if not security.price_symbol:
        result.error = "Aucun symbole de cours configuré"
        return result

    try:
        source = provider or provider_for(security)
        quote_date, price, currency = source.fetch_quote(security.price_symbol)
        _check_currency(security, currency)
        _store(security, quote_date, price)
    except PriceUnavailable as exc:
        result.error = str(exc)
        _record_failure(security, result.error)
        return result
    except Exception as exc:  # noqa: BLE001 - provider errors are open-ended
        result.error = f"{type(exc).__name__}: {exc}"
        _record_failure(security, result.error)
        return result

    _record_success(security)
    result.stored = 1
    return result


def sync_all_prices(provider=None):
    """Refresh every security that has a symbol configured.

    A failure on one security is recorded and the run continues — one delisted
    holding must not stop the rest of the portfolio from being priced.
    """
    return [
        sync_security_price(security, provider=provider)
        for security in Security.objects.exclude(price_symbol="")
    ]


def backfill_security_history(security, start, end=None, provider=None):
    """Store daily closes over a period.

    Handy to populate the 31/12/2025 reference price the Belgian plus-value
    tax uses to grandfather holdings bought before the regime started.
    """
    result = SyncResult(security=security)
    end = end or date.today()

    if not security.price_symbol:
        result.error = "Aucun symbole de cours configuré"
        return result

    try:
        source = provider or provider_for(security)
        rows, currency = source.fetch_history(security.price_symbol, start, end)
        _check_currency(security, currency)
    except PriceUnavailable as exc:
        result.error = str(exc)
        _record_failure(security, result.error)
        return result
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        _record_failure(security, result.error)
        return result

    for quote_date, price in rows:
        try:
            _store(security, quote_date, price)
        except PriceUnavailable:
            continue  # skip one bad day rather than losing the whole range
        result.stored += 1

    _record_success(security)
    return result
