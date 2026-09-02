"""Price feed tests.

Every test injects a fake fetcher — nothing here touches the network, so the
suite stays deterministic and green when Yahoo is down or rate-limiting.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import CurrencyFactory
from apps.fx.models import Currency
from apps.wealth.models import PriceSnapshot, Security
from apps.wealth.pricing import (
    PriceUnavailable,
    backfill_security_history,
    sync_all_prices,
    sync_security_price,
)
from apps.wealth.services import is_stale, latest_quote

pytestmark = pytest.mark.django_db


@pytest.fixture
def security():
    CurrencyFactory()
    return Security.objects.create(
        identifier="IE00B4L5Y983",
        name="iShares Core MSCI World",
        type=Security.Type.ETF,
        currency_id="EUR",
        yahoo_symbol="IWDA.AS",
    )


def fake_quote(quote_date, price, currency="EUR"):
    def _fetch(symbol):
        return quote_date, Decimal(price), currency

    return _fetch


def test_quote_is_stored_as_a_price_snapshot(security):
    result = sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "103.25"))

    assert result.ok
    assert result.stored == 1
    snapshot = PriceSnapshot.objects.get(security=security)
    assert snapshot.date == date(2026, 6, 1)
    assert snapshot.price == Decimal("103.25")

    security.refresh_from_db()
    assert security.last_synced_at is not None
    assert security.last_sync_error == ""


def test_syncing_twice_updates_rather_than_duplicates(security):
    sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "100"))
    sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "104"))

    assert PriceSnapshot.objects.filter(security=security).count() == 1
    assert PriceSnapshot.objects.get(security=security).price == Decimal("104")


def test_currency_mismatch_is_refused_rather_than_stored(security):
    """Yahoo serves the same ISIN from several listings. Storing a USD quote
    against a EUR-denominated holding would silently inflate net worth."""
    result = sync_security_price(
        security, fetch=fake_quote(date(2026, 6, 1), "103.25", currency="USD")
    )

    assert not result.ok
    assert "Devise incohérente" in result.error
    assert not PriceSnapshot.objects.filter(security=security).exists()

    security.refresh_from_db()
    assert "USD" in security.last_sync_error


def test_missing_provider_currency_trusts_the_configured_one(security):
    result = sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "50", currency=None))

    assert result.ok
    assert PriceSnapshot.objects.filter(security=security).exists()


def test_provider_failure_is_recorded_not_raised(security):
    def failing(symbol):
        raise PriceUnavailable("Aucune cotation renvoyée pour IWDA.AS")

    result = sync_security_price(security, fetch=failing)

    assert not result.ok
    assert "Aucune cotation" in result.error
    security.refresh_from_db()
    assert "Aucune cotation" in security.last_sync_error


def test_unexpected_provider_exception_is_contained(security):
    def exploding(symbol):
        raise RuntimeError("Yahoo a changé son API")

    result = sync_security_price(security, fetch=exploding)

    assert not result.ok
    assert "RuntimeError" in result.error
    assert not PriceSnapshot.objects.filter(security=security).exists()


def test_non_positive_price_is_refused(security):
    result = sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "0"))

    assert not result.ok
    assert not PriceSnapshot.objects.filter(security=security).exists()


def test_security_without_symbol_is_skipped(security):
    security.yahoo_symbol = ""
    security.save()

    result = sync_security_price(security)

    assert not result.ok
    assert "Aucun symbole" in result.error


def test_a_failing_ticker_does_not_abort_the_whole_run(security):
    """One delisted holding must not stop the rest of the portfolio pricing."""
    Currency.objects.get_or_create(code="USD", defaults={"name": "Dollar", "symbol": "$"})
    other = Security.objects.create(
        identifier="US0378331005", name="Apple", type=Security.Type.STOCK,
        currency_id="USD", yahoo_symbol="AAPL",
    )

    def selective(symbol):
        if symbol == "IWDA.AS":
            raise PriceUnavailable("délisté")
        return date(2026, 6, 1), Decimal("190"), "USD"

    results = sync_all_prices(fetch=selective)

    assert len(results) == 2
    assert sorted(r.ok for r in results) == [False, True]
    assert PriceSnapshot.objects.filter(security=other).exists()
    assert not PriceSnapshot.objects.filter(security=security).exists()


def test_securities_without_a_symbol_are_not_even_attempted(security):
    Security.objects.create(
        identifier="MANUAL1", name="Titre saisi à la main", type=Security.Type.FUND,
        currency_id="EUR", yahoo_symbol="",
    )

    results = sync_all_prices(fetch=fake_quote(date(2026, 6, 1), "10"))

    assert [r.security.identifier for r in results] == ["IE00B4L5Y983"]


def test_backfill_stores_every_close_in_the_window(security):
    def history(symbol, start, end):
        rows = [
            (date(2025, 12, 30), Decimal("95")),
            (date(2025, 12, 31), Decimal("97.50")),
            (date(2026, 1, 2), Decimal("99")),
        ]
        return rows, "EUR"

    result = backfill_security_history(
        security, date(2025, 12, 30), date(2026, 1, 2), fetch=history
    )

    assert result.ok
    assert result.stored == 3
    # This is the price the Belgian capital gains regime uses to grandfather
    # holdings bought before 2026.
    reference = PriceSnapshot.objects.get(security=security, date=date(2025, 12, 31))
    assert reference.price == Decimal("97.50")


def test_backfill_refuses_a_currency_mismatch(security):
    def history(symbol, start, end):
        return [(date(2025, 12, 31), Decimal("97.50"))], "USD"

    result = backfill_security_history(security, date(2025, 12, 30), date(2026, 1, 2), fetch=history)

    assert not result.ok
    assert not PriceSnapshot.objects.filter(security=security).exists()


def test_latest_quote_and_staleness(security):
    today = date.today()
    PriceSnapshot.objects.create(security=security, date=today - timedelta(days=2), price=Decimal("100"))

    price, quote_date = latest_quote(security)

    assert price == Decimal("100")
    assert is_stale(quote_date) is False
    assert is_stale(today - timedelta(days=40)) is True
    assert is_stale(None) is True


def test_stale_price_is_flagged_in_net_worth(security):
    from apps.accounts.tests.factories import HouseholdFactory
    from apps.budget.models import FinancialAccount
    from apps.wealth.models import SecurityTransaction
    from apps.wealth.services import compute_net_worth

    household = HouseholdFactory(base_currency="EUR")
    account = FinancialAccount.objects.create(
        household=household, name="Titres", type=FinancialAccount.Type.INVESTMENT, currency_id="EUR"
    )
    SecurityTransaction.objects.create(
        household=household, account=account, security=security, date=date(2024, 1, 1),
        type=SecurityTransaction.Type.BUY, quantity=Decimal("10"), price=Decimal("90"),
        fees=Decimal("0"), currency_id="EUR",
    )
    PriceSnapshot.objects.create(
        security=security, date=date.today() - timedelta(days=60), price=Decimal("100")
    )

    total_assets, _, _, breakdown = compute_net_worth(household)

    assert total_assets == Decimal("1000")  # still valued, not dropped
    assert any("périmé" in w for w in breakdown["warnings"])


def test_successful_sync_clears_a_previous_error(security):
    security.last_sync_error = "erreur précédente"
    security.last_synced_at = timezone.now()
    security.save()

    sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "101"))

    security.refresh_from_db()
    assert security.last_sync_error == ""


class _FakeFastInfo(dict):
    """yfinance exposes fast_info as a dict-like object."""


class _FakeTicker:
    def __init__(self, frame, currency="EUR"):
        self._frame = frame
        self.fast_info = _FakeFastInfo({"currency": currency})

    def history(self, **kwargs):
        return self._frame


def _yfinance_shaped_frame():
    """A DataFrame shaped the way yfinance actually returns one: a
    DatetimeIndex and OHLC columns."""
    import pandas as pd

    index = pd.DatetimeIndex(
        [pd.Timestamp("2026-05-29"), pd.Timestamp("2026-06-01")], name="Date"
    )
    return pd.DataFrame(
        {"Open": [101.0, 102.0], "Close": [102.5, 103.25], "Volume": [1000, 1200]}, index=index
    )


def test_fetch_quote_parses_a_yfinance_shaped_frame(monkeypatch):
    """Covers the DataFrame parsing that the injected fakes bypass — the one
    piece that only runs for real against Yahoo."""
    import yfinance

    monkeypatch.setattr(
        yfinance, "Ticker", lambda symbol: _FakeTicker(_yfinance_shaped_frame())
    )
    from apps.wealth.pricing import fetch_quote

    quote_date, price, currency = fetch_quote("IWDA.AS")

    assert quote_date == date(2026, 6, 1)  # the most recent row
    assert price == Decimal("103.25")
    assert currency == "EUR"


def test_fetch_history_parses_a_yfinance_shaped_frame(monkeypatch):
    import yfinance

    monkeypatch.setattr(
        yfinance, "Ticker", lambda symbol: _FakeTicker(_yfinance_shaped_frame())
    )
    from apps.wealth.pricing import fetch_history

    rows, currency = fetch_history("IWDA.AS", date(2026, 5, 1), date(2026, 6, 2))

    assert rows == [(date(2026, 5, 29), Decimal("102.5")), (date(2026, 6, 1), Decimal("103.25"))]
    assert currency == "EUR"


def test_fetch_quote_raises_when_the_provider_returns_nothing(monkeypatch):
    import pandas as pd
    import yfinance

    monkeypatch.setattr(
        yfinance, "Ticker", lambda symbol: _FakeTicker(pd.DataFrame())
    )
    from apps.wealth.pricing import PriceUnavailable, fetch_quote

    with pytest.raises(PriceUnavailable):
        fetch_quote("DELISTED.XX")


def test_sync_errors_are_shown_on_the_wealth_page(client, security):
    from apps.accounts.tests.factories import (
        HouseholdFactory,
        HouseholdMembershipFactory,
        UserFactory,
    )
    from apps.budget.models import FinancialAccount
    from apps.wealth.models import SecurityTransaction

    user = UserFactory()
    household = HouseholdFactory(base_currency="EUR")
    HouseholdMembershipFactory(user=user, household=household)
    account = FinancialAccount.objects.create(
        household=household, name="Titres", type=FinancialAccount.Type.INVESTMENT, currency_id="EUR"
    )
    SecurityTransaction.objects.create(
        household=household, account=account, security=security, date=date(2024, 1, 1),
        type=SecurityTransaction.Type.BUY, quantity=Decimal("10"), price=Decimal("90"),
        fees=Decimal("0"), currency_id="EUR",
    )
    sync_security_price(security, fetch=fake_quote(date(2026, 6, 1), "100", currency="USD"))

    client.force_login(user)
    body = client.get("/patrimoine/").content.decode()

    assert "Récupération automatique des cours en échec" in body
    assert "Devise incohérente" in body
