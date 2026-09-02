from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import CurrencyFactory, HouseholdFactory
from apps.budget.models import FinancialAccount
from apps.taxes.models import CapitalGainRecord, PlusValueTaxRule, PrecompteMobilierRule, TOBRate
from apps.taxes.services import (
    compute_and_store_capital_gain,
    compute_annual_plus_value_tax,
    compute_plus_value_whatif,
    compute_precompte_mobilier,
    compute_tob,
)
from apps.wealth.models import PriceSnapshot, Security, SecurityTransaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    CurrencyFactory()
    return HouseholdFactory()


@pytest.fixture
def investment_account(household):
    return FinancialAccount.objects.create(
        household=household,
        name="Compte Titres",
        type=FinancialAccount.Type.INVESTMENT,
        currency_id="EUR",
    )


@pytest.fixture
def security():
    return Security.objects.create(
        identifier="IE00B4L5Y983", name="iShares Core MSCI World", type=Security.Type.ETF, currency_id="EUR"
    )


@pytest.fixture
def plus_value_rule_2026():
    rule, _ = PlusValueTaxRule.objects.update_or_create(
        year=2026,
        defaults={
            "rate_percent": Decimal("10.00"),
            "annual_exemption": Decimal("10000.00"),
            "reference_date": date(2025, 12, 31),
        },
    )
    return rule


def test_tob_applies_rate_below_cap():
    TOBRate.objects.update_or_create(
        instrument_type=TOBRate.InstrumentType.SHARES,
        defaults={
            "rate_percent": Decimal("0.35"),
            "cap_amount": Decimal("1600.00"),
            "effective_from": date(2017, 1, 1),
        },
    )
    result = compute_tob(TOBRate.InstrumentType.SHARES, Decimal("10000"))
    assert result["tax_due"] == Decimal("35.00")
    assert result["capped"] is False


def test_tob_is_capped_on_large_orders():
    TOBRate.objects.update_or_create(
        instrument_type=TOBRate.InstrumentType.CAPITALIZATION,
        defaults={
            "rate_percent": Decimal("1.32"),
            "cap_amount": Decimal("4000.00"),
            "effective_from": date(2017, 1, 1),
        },
    )
    result = compute_tob(TOBRate.InstrumentType.CAPITALIZATION, Decimal("1000000"))
    assert result["raw_tax"] == Decimal("13200.00")
    assert result["tax_due"] == Decimal("4000.00")
    assert result["capped"] is True


def test_precompte_mobilier_on_dividend():
    PrecompteMobilierRule.objects.update_or_create(
        year=2026,
        defaults={
            "rate_percent": Decimal("30.00"),
            "savings_account_exempt_threshold": Decimal("1100.00"),
        },
    )
    result = compute_precompte_mobilier(Decimal("500"), is_regulated_savings=False, year=2026)
    assert result["tax_due"] == Decimal("150.00")
    assert result["net_income"] == Decimal("350.00")


def test_precompte_mobilier_savings_exemption_applied():
    PrecompteMobilierRule.objects.update_or_create(
        year=2026,
        defaults={
            "rate_percent": Decimal("30.00"),
            "savings_account_exempt_threshold": Decimal("1100.00"),
        },
    )
    result = compute_precompte_mobilier(Decimal("800"), is_regulated_savings=True, year=2026)
    assert result["taxable"] == Decimal("0")
    assert result["tax_due"] == Decimal("0.00")


def test_plus_value_whatif_below_exemption_is_tax_free(plus_value_rule_2026):
    result = compute_plus_value_whatif(Decimal("5000"), Decimal("12000"), year=2026)
    assert result["gain"] == Decimal("7000")
    assert result["taxable"] == Decimal("0")
    assert result["tax_due"] == Decimal("0.00")


def test_plus_value_whatif_above_exemption_is_taxed(plus_value_rule_2026):
    result = compute_plus_value_whatif(Decimal("5000"), Decimal("20000"), year=2026)
    assert result["gain"] == Decimal("15000")
    assert result["taxable"] == Decimal("5000")
    assert result["tax_due"] == Decimal("500.00")


def test_fifo_capital_gain_on_sale(household, investment_account, security, plus_value_rule_2026):
    SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2024, 1, 10),
        type=SecurityTransaction.Type.BUY,
        quantity=Decimal("100"),
        price=Decimal("50"),
        fees=Decimal("5"),
        currency_id="EUR",
    )
    sell = SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2026, 6, 1),
        type=SecurityTransaction.Type.SELL,
        quantity=Decimal("40"),
        price=Decimal("80"),
        fees=Decimal("5"),
        currency_id="EUR",
    )

    record = CapitalGainRecord.objects.get(security_transaction=sell)
    # unit cost = (100*50 + 5) / 100 = 50.05 ; cost basis for 40 shares = 2002.00
    assert record.cost_basis == Decimal("2002.00")
    # proceeds = 40*80 - 5 = 3195.00
    assert record.proceeds == Decimal("3195.00")
    assert record.realized_gain == Decimal("1193.00")


def test_grandfathered_reference_value_is_used_when_higher(
    household, investment_account, security, plus_value_rule_2026
):
    """If the security's value at the reference date was higher than the
    actual FIFO cost, the reference value should be used instead — that's the
    whole point of grandfathering pre-existing holdings.
    """
    SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2015, 1, 10),
        type=SecurityTransaction.Type.BUY,
        quantity=Decimal("100"),
        price=Decimal("10"),
        fees=Decimal("0"),
        currency_id="EUR",
    )
    PriceSnapshot.objects.create(security=security, date=date(2025, 12, 31), price=Decimal("40"))

    sell = SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2026, 6, 1),
        type=SecurityTransaction.Type.SELL,
        quantity=Decimal("50"),
        price=Decimal("60"),
        fees=Decimal("0"),
        currency_id="EUR",
    )

    record = CapitalGainRecord.objects.get(security_transaction=sell)
    # FIFO cost would be 50*10=500, but reference value 50*40=2000 is higher and wins.
    assert record.cost_basis == Decimal("2000.00")
    assert record.proceeds == Decimal("3000.00")
    assert record.realized_gain == Decimal("1000.00")


def test_annual_plus_value_tax_aggregates_household_gains(
    household, investment_account, security, plus_value_rule_2026
):
    SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2024, 1, 10),
        type=SecurityTransaction.Type.BUY,
        quantity=Decimal("100"),
        price=Decimal("10"),
        fees=Decimal("0"),
        currency_id="EUR",
    )
    SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2026, 3, 1),
        type=SecurityTransaction.Type.SELL,
        quantity=Decimal("100"),
        price=Decimal("160"),
        fees=Decimal("0"),
        currency_id="EUR",
    )

    summary = compute_annual_plus_value_tax(household, 2026)
    # gain = 100*160 - 100*10 = 15000 ; taxable = 15000-10000=5000 ; tax = 500
    assert summary["total_gain"] == Decimal("15000")
    assert summary["taxable"] == Decimal("5000")
    assert summary["tax_due"] == Decimal("500.00")


def test_compute_and_store_capital_gain_ignores_non_sell(household, investment_account, security):
    buy = SecurityTransaction.objects.create(
        household=household,
        account=investment_account,
        security=security,
        date=date(2024, 1, 10),
        type=SecurityTransaction.Type.BUY,
        quantity=Decimal("10"),
        price=Decimal("10"),
        fees=Decimal("0"),
        currency_id="EUR",
    )
    assert compute_and_store_capital_gain(buy) is None
    assert not CapitalGainRecord.objects.filter(security_transaction=buy).exists()
