from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import CurrencyFactory, HouseholdFactory
from apps.budget.models import FinancialAccount, Transaction
from apps.fx.models import Currency, ExchangeRate
from apps.wealth.models import Liability, PriceSnapshot, RealAsset, Security, SecurityTransaction
from apps.wealth.services import compute_net_worth

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    CurrencyFactory()
    return HouseholdFactory(base_currency="EUR")


@pytest.fixture
def investment_account(household):
    return FinancialAccount.objects.create(
        household=household,
        name="Compte Titres",
        type=FinancialAccount.Type.INVESTMENT,
        currency_id="EUR",
    )


def _security(currency="EUR", identifier="IE00TEST"):
    return Security.objects.create(
        identifier=identifier, name="ETF Monde", type=Security.Type.ETF, currency_id=currency
    )


def test_net_worth_includes_security_holdings_at_market_price(household, investment_account):
    security = _security()
    SecurityTransaction.objects.create(
        household=household, account=investment_account, security=security,
        date=date(2024, 1, 1), type=SecurityTransaction.Type.BUY,
        quantity=Decimal("100"), price=Decimal("50"), fees=Decimal("0"), currency_id="EUR",
    )
    PriceSnapshot.objects.create(security=security, date=date(2026, 6, 1), price=Decimal("80"))

    total_assets, _, net_worth, _ = compute_net_worth(household)

    assert total_assets == Decimal("8000")
    assert net_worth == Decimal("8000")


def test_holdings_without_a_quote_fall_back_to_cost_and_warn(household, investment_account):
    security = _security()
    SecurityTransaction.objects.create(
        household=household, account=investment_account, security=security,
        date=date(2024, 1, 1), type=SecurityTransaction.Type.BUY,
        quantity=Decimal("10"), price=Decimal("30"), fees=Decimal("0"), currency_id="EUR",
    )

    total_assets, _, _, breakdown = compute_net_worth(household)

    assert total_assets == Decimal("300")
    assert any("aucun cours connu" in w for w in breakdown["warnings"])


def test_net_worth_converts_foreign_currency_accounts(household):
    Currency.objects.get_or_create(code="USD", defaults={"name": "Dollar", "symbol": "$"})
    ExchangeRate.objects.create(
        base_currency_id="EUR", quote_currency_id="USD", date=date(2026, 1, 1), rate=Decimal("2")
    )
    usd_account = FinancialAccount.objects.create(
        household=household, name="Compte USD", currency_id="USD"
    )
    Transaction.objects.create(
        household=household, account=usd_account, currency_id="USD",
        date=date(2026, 2, 1), amount=Decimal("200"), description="Dépôt",
    )

    total_assets, _, _, breakdown = compute_net_worth(household)

    # 200 USD at 1 EUR = 2 USD is 100 EUR.
    assert total_assets == Decimal("100")
    assert breakdown["warnings"] == []


def test_unconvertible_currency_is_counted_but_flagged(household):
    Currency.objects.get_or_create(code="GBP", defaults={"name": "Livre", "symbol": "£"})
    gbp_account = FinancialAccount.objects.create(
        household=household, name="Compte GBP", currency_id="GBP"
    )
    Transaction.objects.create(
        household=household, account=gbp_account, currency_id="GBP",
        date=date(2026, 2, 1), amount=Decimal("50"), description="Dépôt",
    )

    total_assets, _, _, breakdown = compute_net_worth(household)

    assert total_assets == Decimal("50")  # counted, not dropped
    assert any("non converti" in w for w in breakdown["warnings"])


def test_net_worth_subtracts_liabilities(household):
    RealAsset.objects.create(
        household=household, type=RealAsset.Type.REAL_ESTATE, name="Maison",
        acquisition_value=Decimal("300000"), current_value=Decimal("350000"), currency_id="EUR",
    )
    Liability.objects.create(
        household=household, type=Liability.Type.MORTGAGE, name="Crédit",
        principal=Decimal("250000"), remaining_balance=Decimal("200000"), currency_id="EUR",
    )

    total_assets, total_liabilities, net_worth, _ = compute_net_worth(household)

    assert total_assets == Decimal("350000")
    assert total_liabilities == Decimal("200000")
    assert net_worth == Decimal("150000")
