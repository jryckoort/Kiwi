from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import CurrencyFactory, HouseholdFactory
from apps.budget.models import FinancialAccount, RecurringTransaction
from apps.budget.recurring import expected_amount_between, occurrences_between, upcoming_occurrences

pytestmark = pytest.mark.django_db


@pytest.fixture
def account():
    CurrencyFactory()
    household = HouseholdFactory()
    return FinancialAccount.objects.create(
        household=household, name="Compte courant", currency_id="EUR"
    )


def _recurrence(account, **kwargs):
    defaults = {
        "household": account.household,
        "account": account,
        "description": "Loyer",
        "amount": Decimal("-1200"),
        "currency_id": "EUR",
        "frequency": RecurringTransaction.Frequency.MONTHLY,
        "start_date": date(2026, 1, 5),
    }
    return RecurringTransaction.objects.create(**{**defaults, **kwargs})


def test_monthly_occurrences_within_window(account):
    rent = _recurrence(account)

    dates = occurrences_between(rent, date(2026, 1, 1), date(2026, 4, 30))

    assert dates == [date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5), date(2026, 4, 5)]


def test_month_end_start_clamps_to_short_months_without_drifting(account):
    """A rent due on the 31st must fall back to the 28th in February and then
    return to the 31st — not stay stuck on the 28th for good.
    """
    rent = _recurrence(account, start_date=date(2026, 1, 31))

    dates = occurrences_between(rent, date(2026, 1, 1), date(2026, 5, 31))

    assert dates == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]


def test_interval_skips_periods(account):
    every_two_months = _recurrence(account, interval=2)

    dates = occurrences_between(every_two_months, date(2026, 1, 1), date(2026, 6, 30))

    assert dates == [date(2026, 1, 5), date(2026, 3, 5), date(2026, 5, 5)]


def test_end_date_stops_the_series(account):
    rent = _recurrence(account, end_date=date(2026, 3, 1))

    dates = occurrences_between(rent, date(2026, 1, 1), date(2026, 12, 31))

    assert dates == [date(2026, 1, 5), date(2026, 2, 5)]


def test_window_before_the_series_starts_is_empty(account):
    rent = _recurrence(account, start_date=date(2026, 6, 1))

    assert occurrences_between(rent, date(2026, 1, 1), date(2026, 5, 31)) == []


def test_weekly_and_quarterly_and_yearly(account):
    weekly = _recurrence(
        account, frequency=RecurringTransaction.Frequency.WEEKLY, start_date=date(2026, 1, 1)
    )
    quarterly = _recurrence(
        account, frequency=RecurringTransaction.Frequency.QUARTERLY, start_date=date(2026, 1, 1)
    )
    yearly = _recurrence(
        account, frequency=RecurringTransaction.Frequency.YEARLY, start_date=date(2026, 1, 1)
    )

    assert occurrences_between(weekly, date(2026, 1, 1), date(2026, 1, 31)) == [
        date(2026, 1, 1), date(2026, 1, 8), date(2026, 1, 15), date(2026, 1, 22), date(2026, 1, 29)
    ]
    assert occurrences_between(quarterly, date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)
    ]
    assert occurrences_between(yearly, date(2026, 1, 1), date(2028, 12, 31)) == [
        date(2026, 1, 1), date(2027, 1, 1), date(2028, 1, 1)
    ]


def test_expected_amount_multiplies_by_occurrence_count(account):
    weekly = _recurrence(
        account,
        frequency=RecurringTransaction.Frequency.WEEKLY,
        start_date=date(2026, 1, 1),
        amount=Decimal("-25"),
    )

    total = expected_amount_between(weekly, date(2026, 1, 1), date(2026, 1, 31))

    assert total == Decimal("-125")  # five Thursdays in January 2026


def test_upcoming_ignores_inactive_recurrences(account):
    _recurrence(account, description="Actif")
    _recurrence(account, description="Archivé", is_active=False)

    upcoming = upcoming_occurrences(account.household, date(2026, 1, 1), date(2026, 1, 31))

    assert [row["recurrence"].description for row in upcoming] == ["Actif"]


def test_end_before_start_is_rejected(account):
    recurrence = RecurringTransaction(
        household=account.household,
        account=account,
        description="Invalide",
        amount=Decimal("-10"),
        currency_id="EUR",
        frequency=RecurringTransaction.Frequency.MONTHLY,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 1, 1),
    )

    with pytest.raises(ValidationError):
        recurrence.full_clean()


def test_recurrence_owner_follows_the_account(account):
    from apps.accounts.tests.factories import UserFactory

    user = UserFactory()
    personal = FinancialAccount.objects.create(
        household=account.household, name="Compte perso", currency_id="EUR", owner=user
    )

    assert _recurrence(account).owner is None  # joint account -> commun
    assert _recurrence(personal).owner == user
