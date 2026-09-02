"""FIFO makes every sale depend on the whole prior history, so editing or
deleting an earlier transaction has to invalidate the sales that follow it.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import CurrencyFactory, HouseholdFactory
from apps.budget.models import FinancialAccount
from apps.taxes.models import CapitalGainRecord, PlusValueTaxRule
from apps.wealth.models import Security, SecurityTransaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def context():
    CurrencyFactory()
    household = HouseholdFactory()
    account = FinancialAccount.objects.create(
        household=household,
        name="Compte Titres",
        type=FinancialAccount.Type.INVESTMENT,
        currency_id="EUR",
    )
    security = Security.objects.create(
        identifier="IE00RECALC", name="ETF Monde", type=Security.Type.ETF, currency_id="EUR"
    )
    PlusValueTaxRule.objects.update_or_create(
        year=2026,
        defaults={
            "rate_percent": Decimal("10.00"),
            "annual_exemption": Decimal("10000.00"),
            "reference_date": date(2025, 12, 31),
        },
    )
    return household, account, security


def _buy(context, quantity, price, on=date(2024, 1, 1)):
    household, account, security = context
    return SecurityTransaction.objects.create(
        household=household, account=account, security=security, date=on,
        type=SecurityTransaction.Type.BUY, quantity=Decimal(quantity),
        price=Decimal(price), fees=Decimal("0"), currency_id="EUR",
    )


def _sell(context, quantity, price, on=date(2026, 6, 1)):
    household, account, security = context
    return SecurityTransaction.objects.create(
        household=household, account=account, security=security, date=on,
        type=SecurityTransaction.Type.SELL, quantity=Decimal(quantity),
        price=Decimal(price), fees=Decimal("0"), currency_id="EUR",
    )


def test_editing_an_earlier_buy_recomputes_the_gain(context):
    buy = _buy(context, "100", "10")
    sell = _sell(context, "100", "30")

    record = CapitalGainRecord.objects.get(security_transaction=sell)
    assert record.realized_gain == Decimal("2000.00")

    buy.price = Decimal("20")  # the purchase price was mistyped
    buy.save()

    record.refresh_from_db()
    assert record.cost_basis == Decimal("2000.00")
    assert record.realized_gain == Decimal("1000.00")


def test_deleting_an_earlier_buy_recomputes_the_gain(context):
    first_buy = _buy(context, "100", "10", on=date(2024, 1, 1))
    _buy(context, "100", "20", on=date(2024, 2, 1))
    sell = _sell(context, "100", "30")

    record = CapitalGainRecord.objects.get(security_transaction=sell)
    assert record.realized_gain == Decimal("2000.00")

    first_buy.delete()  # entered twice by mistake

    record.refresh_from_db()
    assert record.realized_gain == Decimal("1000.00")


def test_inserting_a_backdated_buy_recomputes_the_gain(context):
    _buy(context, "100", "20", on=date(2024, 2, 1))
    sell = _sell(context, "100", "30")
    record = CapitalGainRecord.objects.get(security_transaction=sell)
    assert record.realized_gain == Decimal("1000.00")

    # A forgotten earlier purchase is added afterwards; FIFO must now consume
    # that older, cheaper lot instead.
    _buy(context, "100", "5", on=date(2023, 1, 1))

    record.refresh_from_db()
    assert record.cost_basis == Decimal("500.00")
    assert record.realized_gain == Decimal("2500.00")


def test_editing_one_sale_updates_the_later_sale_too(context):
    _buy(context, "100", "10", on=date(2024, 1, 1))
    _buy(context, "100", "20", on=date(2024, 2, 1))
    first_sell = _sell(context, "50", "30", on=date(2026, 3, 1))
    second_sell = _sell(context, "50", "40", on=date(2026, 4, 1))

    second = CapitalGainRecord.objects.get(security_transaction=second_sell)
    # First sale eats 50 @10; second eats the remaining 50 @10 → cost 500.
    assert second.cost_basis == Decimal("500.00")

    first_sell.quantity = Decimal("100")  # actually sold the whole first lot
    first_sell.save()

    second.refresh_from_db()
    # Now the first sale consumed all 100 @10, so the second falls on the @20 lot.
    assert second.cost_basis == Decimal("1000.00")
