"""Provider parsing tests.

These cover the code that only ever runs against a live API, so they feed each
provider a realistically-shaped payload instead of hitting the network.
"""

from datetime import date
from decimal import Decimal

import pytest
import requests

from apps.wealth.providers import (
    DEFAULT_PROVIDER,
    PriceUnavailable,
    available_providers,
    get_provider,
    provider_for,
)
from apps.wealth.providers.stooq import StooqProvider
from apps.wealth.providers.twelvedata import TwelveDataProvider
from apps.wealth.providers.yahoo import YahooProvider

# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


def test_every_provider_is_resolvable_by_name():
    for name in available_providers():
        assert get_provider(name).name == name


def test_unknown_provider_names_the_valid_options():
    with pytest.raises(PriceUnavailable) as exc:
        get_provider("bloomberg")

    assert "bloomberg" in str(exc.value)
    assert "stooq" in str(exc.value)


def test_provider_defaults_to_the_configured_one(settings):
    settings.SECURITY_PRICE_PROVIDER = "stooq"
    assert get_provider().name == "stooq"


def test_blank_configuration_falls_back_to_the_default(settings):
    settings.SECURITY_PRICE_PROVIDER = ""
    assert get_provider().name == DEFAULT_PROVIDER


def test_provider_name_is_case_and_space_insensitive(settings):
    settings.SECURITY_PRICE_PROVIDER = "  StooQ "
    assert get_provider().name == "stooq"


@pytest.mark.django_db
def test_a_security_can_override_the_global_provider(settings):
    from apps.accounts.tests.factories import CurrencyFactory
    from apps.wealth.models import Security

    settings.SECURITY_PRICE_PROVIDER = "yahoo"
    CurrencyFactory()
    security = Security.objects.create(
        identifier="X", name="ETF", type=Security.Type.ETF, currency_id="EUR",
        price_symbol="iwda.nl", price_provider="stooq",
    )

    assert provider_for(security).name == "stooq"

    security.price_provider = ""
    assert provider_for(security).name == "yahoo"


# --------------------------------------------------------------------------
# Stooq — CSV, no API key, no currency reported
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _patch_requests(monkeypatch, response):
    def fake_get(url, params=None, timeout=None):
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(requests, "get", fake_get)


def test_stooq_parses_a_quote(monkeypatch):
    _patch_requests(
        monkeypatch,
        _FakeResponse(
            "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
            "IWDA.NL,2026-06-01,17:35:00,102.5,103.1,102.0,103.25,120000\n"
        ),
    )

    quote_date, price, currency = StooqProvider().fetch_quote("iwda.nl")

    assert quote_date == date(2026, 6, 1)
    assert price == Decimal("103.25")
    assert currency is None  # Stooq never says, so the caller trusts its config


def test_stooq_parses_history_and_sorts_nothing_away(monkeypatch):
    _patch_requests(
        monkeypatch,
        _FakeResponse(
            "Date,Open,High,Low,Close,Volume\n"
            "2025-12-30,94,95,93,95,100\n"
            "2025-12-31,96,98,96,97.50,120\n"
            "2026-01-02,98,99,97,99,130\n"
        ),
    )

    rows, currency = StooqProvider().fetch_history("iwda.nl", date(2025, 12, 30), date(2026, 1, 2))

    assert rows == [
        (date(2025, 12, 30), Decimal("95")),
        (date(2025, 12, 31), Decimal("97.50")),
        (date(2026, 1, 2), Decimal("99")),
    ]
    assert currency is None


def test_stooq_reports_an_unknown_symbol(monkeypatch):
    """Stooq answers a bare 'N/D' body with HTTP 200 for an unknown symbol."""
    _patch_requests(monkeypatch, _FakeResponse("N/D"))

    with pytest.raises(PriceUnavailable, match="Symbole inconnu"):
        StooqProvider().fetch_quote("nexistepas.zz")


def test_stooq_network_failure_becomes_price_unavailable(monkeypatch):
    _patch_requests(monkeypatch, requests.ConnectionError("boom"))

    with pytest.raises(PriceUnavailable, match="injoignable"):
        StooqProvider().fetch_quote("iwda.nl")


def test_stooq_skips_unusable_rows_rather_than_failing(monkeypatch):
    _patch_requests(
        monkeypatch,
        _FakeResponse(
            "Date,Open,High,Low,Close,Volume\n"
            "2025-12-30,94,95,93,N/D,100\n"
            "2025-12-31,96,98,96,97.50,120\n"
        ),
    )

    rows, _ = StooqProvider().fetch_history("iwda.nl", date(2025, 12, 30), date(2025, 12, 31))

    assert rows == [(date(2025, 12, 31), Decimal("97.50"))]


# --------------------------------------------------------------------------
# Twelve Data — JSON, API key, reports the currency
# --------------------------------------------------------------------------


class _FakeJsonResponse(_FakeResponse):
    def __init__(self, payload, status=200):
        super().__init__("", status)
        self._payload = payload

    def json(self):
        return self._payload


def test_twelvedata_parses_a_quote(monkeypatch, settings):
    settings.TWELVEDATA_API_KEY = "test-key"
    _patch_requests(
        monkeypatch,
        _FakeJsonResponse(
            {
                "meta": {"symbol": "IWDA.AS", "currency": "EUR"},
                "values": [
                    {"datetime": "2026-06-01", "close": "103.25"},
                    {"datetime": "2026-05-29", "close": "102.50"},
                ],
                "status": "ok",
            }
        ),
    )

    quote_date, price, currency = TwelveDataProvider().fetch_quote("IWDA.AS")

    # Twelve Data returns newest first — the latest row must win.
    assert quote_date == date(2026, 6, 1)
    assert price == Decimal("103.25")
    assert currency == "EUR"


def test_twelvedata_history_comes_back_chronological(monkeypatch, settings):
    settings.TWELVEDATA_API_KEY = "test-key"
    _patch_requests(
        monkeypatch,
        _FakeJsonResponse(
            {
                "meta": {"currency": "EUR"},
                "values": [
                    {"datetime": "2026-01-02", "close": "99"},
                    {"datetime": "2025-12-31", "close": "97.50"},
                ],
                "status": "ok",
            }
        ),
    )

    rows, currency = TwelveDataProvider().fetch_history(
        "IWDA.AS", date(2025, 12, 31), date(2026, 1, 2)
    )

    assert rows == [(date(2025, 12, 31), Decimal("97.50")), (date(2026, 1, 2), Decimal("99"))]
    assert currency == "EUR"


def test_twelvedata_reports_a_quota_error_carried_in_a_200_body(monkeypatch, settings):
    """The free tier signals rate limiting with status 'error' inside an HTTP
    200 body, so the payload has to be inspected even on success."""
    settings.TWELVEDATA_API_KEY = "test-key"
    _patch_requests(
        monkeypatch,
        _FakeJsonResponse(
            {"code": 429, "message": "You have run out of API credits", "status": "error"}
        ),
    )

    with pytest.raises(PriceUnavailable, match="API credits"):
        TwelveDataProvider().fetch_quote("IWDA.AS")


def test_twelvedata_without_a_key_says_so_plainly(monkeypatch, settings):
    settings.TWELVEDATA_API_KEY = ""

    with pytest.raises(PriceUnavailable, match="TWELVEDATA_API_KEY"):
        TwelveDataProvider().fetch_quote("IWDA.AS")


# --------------------------------------------------------------------------
# Yahoo — pandas DataFrame from yfinance
# --------------------------------------------------------------------------


class _FakeTicker:
    def __init__(self, frame, currency="EUR"):
        self._frame = frame
        self.fast_info = {"currency": currency}

    def history(self, **kwargs):
        return self._frame


def _yfinance_shaped_frame():
    import pandas as pd

    index = pd.DatetimeIndex(
        [pd.Timestamp("2026-05-29"), pd.Timestamp("2026-06-01")], name="Date"
    )
    return pd.DataFrame(
        {"Open": [101.0, 102.0], "Close": [102.5, 103.25], "Volume": [1000, 1200]}, index=index
    )


def test_yahoo_parses_a_yfinance_shaped_frame(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: _FakeTicker(_yfinance_shaped_frame()))

    quote_date, price, currency = YahooProvider().fetch_quote("IWDA.AS")

    assert quote_date == date(2026, 6, 1)  # most recent row
    assert price == Decimal("103.25")
    assert currency == "EUR"


def test_yahoo_parses_history(monkeypatch):
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: _FakeTicker(_yfinance_shaped_frame()))

    rows, currency = YahooProvider().fetch_history("IWDA.AS", date(2026, 5, 1), date(2026, 6, 2))

    assert rows == [(date(2026, 5, 29), Decimal("102.5")), (date(2026, 6, 1), Decimal("103.25"))]
    assert currency == "EUR"


def test_yahoo_raises_when_nothing_comes_back(monkeypatch):
    import pandas as pd
    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: _FakeTicker(pd.DataFrame()))

    with pytest.raises(PriceUnavailable):
        YahooProvider().fetch_quote("DELISTED.XX")
