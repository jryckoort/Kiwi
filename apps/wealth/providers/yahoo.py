"""Yahoo Finance through yfinance.

Best coverage of European ETF listings, and needs no API key — but it talks
to an unofficial endpoint that Yahoo changes without notice, so treat an
outage here as expected rather than exceptional.
"""

import logging

from .base import PriceProvider, PriceUnavailable

logger = logging.getLogger(__name__)


class YahooProvider(PriceProvider):
    name = "yahoo"
    symbol_example = "IWDA.AS"

    def _ticker(self, symbol):
        import yfinance as yf

        return yf.Ticker(symbol)

    def _currency(self, ticker):
        try:
            return ticker.fast_info.get("currency")
        except Exception:  # noqa: BLE001 - fast_info is best-effort metadata
            logger.warning("Devise indisponible (Yahoo)")
            return None

    def fetch_quote(self, symbol):
        ticker = self._ticker(symbol)
        history = ticker.history(period="5d", auto_adjust=False)
        if history is None or history.empty:
            raise PriceUnavailable(f"Aucune cotation renvoyée pour {symbol}")

        last = history.iloc[-1]
        quote_date = history.index[-1].date()
        return quote_date, self.to_decimal(last["Close"], symbol), self._currency(ticker)

    def fetch_history(self, symbol, start, end):
        ticker = self._ticker(symbol)
        history = ticker.history(start=start, end=end, auto_adjust=False)
        if history is None or history.empty:
            raise PriceUnavailable(f"Aucun historique renvoyé pour {symbol}")

        rows = []
        for index, row in history.iterrows():
            try:
                rows.append((index.date(), self.to_decimal(row["Close"], symbol)))
            except PriceUnavailable:
                continue  # skip a bad day rather than losing the whole range
        if not rows:
            raise PriceUnavailable(f"Historique inexploitable pour {symbol}")
        return rows, self._currency(ticker)
