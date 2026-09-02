"""Common interface every price source implements.

Symbols are provider-specific — the same ETF is ``IWDA.AS`` on Yahoo and
``iwda.nl`` on Stooq — so a security stores one ``price_symbol`` and,
optionally, which provider that symbol belongs to.

Providers return the quote currency when they know it (Yahoo and Twelve Data
do, Stooq does not). ``None`` means "I don't know", and the caller then trusts
the currency configured on the security rather than refusing the quote.
"""

from decimal import Decimal


class PriceUnavailable(Exception):
    """A quote could not be obtained, or could not be trusted."""


class PriceProvider:
    #: short key used in .env and in Security.price_provider
    name = ""
    #: shown in the admin so it's obvious what a symbol should look like
    symbol_example = ""
    requires_api_key = False

    def fetch_quote(self, symbol):
        """Return ``(date, Decimal price, currency or None)`` for the latest close."""
        raise NotImplementedError

    def fetch_history(self, symbol, start, end):
        """Return ``([(date, Decimal price), ...], currency or None)``."""
        raise NotImplementedError

    # Shared parsing helpers — every provider hands back strings from CSV or
    # JSON, and a malformed one must surface as PriceUnavailable rather than
    # some provider-specific exception leaking upwards.

    @staticmethod
    def to_decimal(raw, context=""):
        try:
            value = Decimal(str(raw).strip())
        except Exception as exc:  # noqa: BLE001 - any parse failure is the same to us
            raise PriceUnavailable(f"Cours illisible{f' ({context})' if context else ''} : {raw!r}") from exc
        if value <= 0:
            raise PriceUnavailable(f"Cours non exploitable : {value}")
        return value
