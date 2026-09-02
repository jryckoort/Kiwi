"""Automatic security prices from Yahoo Finance.

yfinance talks to an unofficial Yahoo endpoint that changes without notice,
so the network call is isolated in ``fetch_quote`` / ``fetch_history`` and
injected into everything else. That keeps the tests off the network and makes
swapping provider a one-function change if Yahoo breaks again.

Two rules the rest of the module enforces, both about not corrupting money:

* a quote whose currency disagrees with ``Security.currency`` is refused
  rather than stored — writing a USD price against a EUR-denominated holding
  would silently inflate net worth;
* one failing ticker never aborts the run, and the reason is written to
  ``Security.last_sync_error`` so a self-hosted user sees it in the app
  instead of having to read Celery logs.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import PriceSnapshot, Security

logger = logging.getLogger(__name__)


class PriceUnavailable(Exception):
    """Raised when a quote could not be obtained or trusted."""


@dataclass
class SyncResult:
    security: Security
    stored: int = 0
    error: str = ""

    @property
    def ok(self):
        return not self.error


def fetch_quote(symbol):
    """Latest close for ``symbol``. Returns ``(date, price, currency)``.

    The only place that touches the network for a single quote.
    """
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    history = ticker.history(period="5d", auto_adjust=False)
    if history is None or history.empty:
        raise PriceUnavailable(f"Aucune cotation renvoyée pour {symbol}")

    last = history.iloc[-1]
    quote_date = history.index[-1].date()
    price = Decimal(str(last["Close"]))

    currency = None
    try:
        currency = ticker.fast_info.get("currency")
    except Exception:  # noqa: BLE001 - fast_info is best-effort metadata
        logger.warning("Devise indisponible pour %s", symbol)

    return quote_date, price, currency


def fetch_history(symbol, start, end):
    """Daily closes for ``symbol`` between two dates.

    Returns a list of ``(date, price)`` plus the quote currency.
    """
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    history = ticker.history(start=start, end=end, auto_adjust=False)
    if history is None or history.empty:
        raise PriceUnavailable(f"Aucun historique renvoyé pour {symbol}")

    currency = None
    try:
        currency = ticker.fast_info.get("currency")
    except Exception:  # noqa: BLE001
        logger.warning("Devise indisponible pour %s", symbol)

    rows = [(index.date(), Decimal(str(row["Close"]))) for index, row in history.iterrows()]
    return rows, currency


def _check_currency(security, quote_currency):
    """Refuse a quote denominated in something other than the security's currency.

    Yahoo happily serves the same ISIN from several listings; storing a price
    in the wrong currency would silently distort every valuation built on it.
    """
    if not quote_currency:
        return  # provider did not say; trust the configured currency
    if quote_currency.upper() != security.currency_id.upper():
        raise PriceUnavailable(
            f"Devise incohérente : Yahoo cote {security.yahoo_symbol} en "
            f"{quote_currency.upper()}, or le titre est enregistré en {security.currency_id}"
        )


def _record_failure(security, message):
    security.last_sync_error = message[:255]
    security.save(update_fields=["last_sync_error"])
    logger.warning("Échec de synchro pour %s : %s", security, message)


def sync_security_price(security, fetch=fetch_quote):
    """Fetch and store the latest quote for one security."""
    result = SyncResult(security=security)

    if not security.yahoo_symbol:
        result.error = "Aucun symbole Yahoo configuré"
        return result

    try:
        quote_date, price, currency = fetch(security.yahoo_symbol)
        _check_currency(security, currency)
        if price <= 0:
            raise PriceUnavailable(f"Cours non exploitable ({price})")
    except PriceUnavailable as exc:
        result.error = str(exc)
        _record_failure(security, result.error)
        return result
    except (InvalidOperation, KeyError, IndexError, TypeError, ValueError) as exc:
        result.error = f"Réponse inattendue du fournisseur : {exc}"
        _record_failure(security, result.error)
        return result
    except Exception as exc:  # noqa: BLE001 - network/provider errors are open-ended
        result.error = f"{type(exc).__name__}: {exc}"
        _record_failure(security, result.error)
        return result

    PriceSnapshot.objects.update_or_create(
        security=security, date=quote_date, defaults={"price": price}
    )
    security.last_synced_at = timezone.now()
    security.last_sync_error = ""
    security.save(update_fields=["last_synced_at", "last_sync_error"])
    result.stored = 1
    return result


def sync_all_prices(fetch=fetch_quote):
    """Refresh every security that has a Yahoo symbol configured.

    A failure on one ticker is recorded and the run continues — one delisted
    holding must not stop the rest of the portfolio from being priced.
    """
    results = []
    for security in Security.objects.exclude(yahoo_symbol=""):
        results.append(sync_security_price(security, fetch=fetch))
    return results


def backfill_security_history(security, start, end=None, fetch=fetch_history):
    """Store daily closes over a period.

    Handy to populate the 31/12/2025 reference price the Belgian plus-value
    tax uses to grandfather holdings bought before the regime started.
    """
    result = SyncResult(security=security)
    end = end or date.today()

    if not security.yahoo_symbol:
        result.error = "Aucun symbole Yahoo configuré"
        return result

    try:
        rows, currency = fetch(security.yahoo_symbol, start, end)
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
        if price <= 0:
            continue
        PriceSnapshot.objects.update_or_create(
            security=security, date=quote_date, defaults={"price": price}
        )
        result.stored += 1

    security.last_synced_at = timezone.now()
    security.last_sync_error = ""
    security.save(update_fields=["last_synced_at", "last_sync_error"])
    return result
