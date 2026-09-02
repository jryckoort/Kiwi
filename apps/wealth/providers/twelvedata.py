"""Twelve Data — JSON API with a generous free tier, requires an API key.

Reports the quote currency, which lets the currency guard actually do its job
(Stooq can't). Set ``TWELVEDATA_API_KEY`` in .env.

The free tier is rate-limited; the API signals that with an HTTP 200 body
carrying ``status: error`` rather than an error status code, so the response
body has to be inspected even on success.
"""

from datetime import datetime

import requests
from django.conf import settings

from .base import PriceProvider, PriceUnavailable

BASE_URL = "https://api.twelvedata.com/time_series"
TIMEOUT_SECONDS = 15


class TwelveDataProvider(PriceProvider):
    name = "twelvedata"
    symbol_example = "IWDA.AS"
    requires_api_key = True

    def _payload(self, symbol, **extra):
        api_key = getattr(settings, "TWELVEDATA_API_KEY", "")
        if not api_key:
            raise PriceUnavailable(
                "TWELVEDATA_API_KEY absent du .env — indispensable pour ce fournisseur."
            )

        params = {"symbol": symbol, "interval": "1day", "apikey": api_key, **extra}
        try:
            response = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise PriceUnavailable(f"Twelve Data injoignable : {exc}") from exc
        except ValueError as exc:
            raise PriceUnavailable(f"Réponse Twelve Data illisible : {exc}") from exc

        # Quota and unknown-symbol errors come back with HTTP 200.
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise PriceUnavailable(
                f"Twelve Data a refusé la requête : {payload.get('message', 'raison inconnue')}"
            )

        values = payload.get("values") if isinstance(payload, dict) else None
        if not values:
            raise PriceUnavailable(f"Aucune donnée renvoyée pour {symbol}")

        currency = (payload.get("meta") or {}).get("currency")
        return values, currency

    def _parse_row(self, row, symbol):
        raw_date, close = row.get("datetime"), row.get("close")
        if not raw_date or close is None:
            raise PriceUnavailable(f"Ligne incomplète pour {symbol}")
        try:
            # Intraday intervals would carry a time component; we only ask for
            # daily bars, so keep the date part.
            quote_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
        except ValueError as exc:
            raise PriceUnavailable(f"Date illisible pour {symbol} : {raw_date!r}") from exc
        return quote_date, self.to_decimal(close, symbol)

    def fetch_quote(self, symbol):
        values, currency = self._payload(symbol, outputsize=5)
        # Twelve Data returns newest first.
        quote_date, price = self._parse_row(values[0], symbol)
        return quote_date, price, currency

    def fetch_history(self, symbol, start, end):
        values, currency = self._payload(
            symbol,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            outputsize=5000,
        )

        rows = []
        for value in values:
            try:
                rows.append(self._parse_row(value, symbol))
            except PriceUnavailable:
                continue  # skip a bad row rather than losing the whole range

        if not rows:
            raise PriceUnavailable(f"Aucun historique exploitable pour {symbol}")
        rows.sort(key=lambda row: row[0])
        return rows, currency
