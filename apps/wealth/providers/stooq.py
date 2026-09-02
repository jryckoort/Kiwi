"""Stooq — plain CSV over HTTP, no API key, no registration.

The most dependable free option for a light self-hosted setup: there is no
quota to exhaust and no credential to rotate. The trade-off is that Stooq
never tells you the quote currency, so ``fetch_*`` returns ``None`` for it and
the caller falls back to the currency configured on the security. Double-check
that currency yourself when you enter the symbol.

Symbols differ from Yahoo's: the Amsterdam-listed IWDA is ``iwda.nl`` here,
not ``IWDA.AS``.
"""

import csv
import io
from datetime import datetime

import requests

from .base import PriceProvider, PriceUnavailable

QUOTE_URL = "https://stooq.com/q/l/"
HISTORY_URL = "https://stooq.com/q/d/l/"
TIMEOUT_SECONDS = 15


class StooqProvider(PriceProvider):
    name = "stooq"
    symbol_example = "iwda.nl"

    def _get(self, url, params):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PriceUnavailable(f"Stooq injoignable : {exc}") from exc

        text = response.text.strip()
        # Stooq answers with a bare "N/D" body for an unknown symbol instead
        # of an HTTP error code.
        if not text or text.upper().startswith("N/D"):
            raise PriceUnavailable(f"Symbole inconnu chez Stooq : {params.get('s')}")
        return text

    def fetch_quote(self, symbol):
        text = self._get(QUOTE_URL, {"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise PriceUnavailable(f"Aucune cotation renvoyée pour {symbol}")

        row = rows[-1]
        close = row.get("Close")
        raw_date = row.get("Date")
        if not close or not raw_date or close.upper() == "N/D":
            raise PriceUnavailable(f"Cotation incomplète pour {symbol}")

        try:
            quote_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise PriceUnavailable(f"Date illisible pour {symbol} : {raw_date!r}") from exc

        return quote_date, self.to_decimal(close, symbol), None

    def fetch_history(self, symbol, start, end):
        text = self._get(
            HISTORY_URL,
            {
                "s": symbol,
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
                "i": "d",
            },
        )

        rows = []
        for row in csv.DictReader(io.StringIO(text)):
            raw_date, close = row.get("Date"), row.get("Close")
            if not raw_date or not close or close.upper() == "N/D":
                continue
            try:
                quote_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                rows.append((quote_date, self.to_decimal(close, symbol)))
            except (ValueError, PriceUnavailable):
                continue  # skip a bad row rather than losing the whole range

        if not rows:
            raise PriceUnavailable(f"Aucun historique exploitable pour {symbol}")
        return rows, None
