from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import CurrencyFactory, HouseholdFactory, UserFactory
from apps.budget.models import FinancialAccount, RecurringTransaction, Transaction
from apps.budget.projections import project_account, project_household
from apps.fx.models import Currency, ExchangeRate

pytestmark = pytest.mark.django_db

TODAY = date(2026, 3, 15)


@pytest.fixture
def household():
    CurrencyFactory()
    return HouseholdFactory(base_currency="EUR")


@pytest.fixture
def account(household):
    return FinancialAccount.objects.create(
        household=household, name="Compte courant", currency_id="EUR"
    )


def _tx(account, amount, day, month=3):
    return Transaction.objects.create(
        household=account.household,
        account=account,
        currency_id=account.currency_id,
        date=date(2026, month, day),
        amount=Decimal(amount),
        description="Mouvement",
    )


def _recurrence(account, amount, start_day, month=3, **kwargs):
    defaults = {
        "household": account.household,
        "account": account,
        "description": "Récurrence",
        "amount": Decimal(amount),
        "currency_id": account.currency_id,
        "frequency": RecurringTransaction.Frequency.MONTHLY,
        "start_date": date(2026, month, start_day),
    }
    return RecurringTransaction.objects.create(**{**defaults, **kwargs})


def test_current_balance_only_counts_transactions_up_to_today(account):
    _tx(account, "1000", day=1)
    _tx(account, "-200", day=10)
    _tx(account, "-50", day=20)  # future-dated

    projection = project_account(account, as_of=TODAY)

    assert projection.current_balance == Decimal("800")


def test_future_dated_transactions_are_projected(account):
    """A movement the user already entered with a future date is known money
    leaving the account — leaving it out would flatter the projection."""
    _tx(account, "1000", day=1)
    _tx(account, "-50", day=20)

    projection = project_account(account, as_of=TODAY)

    assert projection.scheduled_total == Decimal("-50")
    assert projection.projected_balance == Decimal("950")


def test_remaining_recurrences_are_projected(account):
    _tx(account, "1000", day=1)
    _recurrence(account, "-300", start_day=25)

    projection = project_account(account, as_of=TODAY)

    assert projection.recurring_total == Decimal("-300")
    assert projection.projected_balance == Decimal("700")
    assert [o["date"] for o in projection.occurrences] == [date(2026, 3, 25)]


def test_occurrences_already_past_are_not_projected_again(account):
    """The rent due on the 5th is already in the imported balance; projecting
    it a second time is exactly the double-count we are avoiding."""
    _tx(account, "1000", day=1)
    _tx(account, "-300", day=5)  # the rent, as imported from the bank
    _recurrence(account, "-300", start_day=5)

    projection = project_account(account, as_of=TODAY)

    assert projection.recurring_total == Decimal("0")
    assert projection.projected_balance == Decimal("700")


def test_occurrence_falling_exactly_today_is_treated_as_already_happened(account):
    _tx(account, "1000", day=1)
    _recurrence(account, "-300", start_day=15)  # today

    projection = project_account(account, as_of=TODAY)

    assert projection.recurring_total == Decimal("0")


def test_occurrences_beyond_month_end_are_out_of_horizon(account):
    _tx(account, "1000", day=1)
    _recurrence(account, "-300", start_day=25)
    _recurrence(account, "-999", start_day=2, month=4)  # next month

    projection = project_account(account, as_of=TODAY)

    assert projection.recurring_total == Decimal("-300")


def test_inactive_recurrences_are_ignored(account):
    _recurrence(account, "-300", start_day=25, is_active=False)

    assert project_account(account, as_of=TODAY).recurring_total == Decimal("0")


def test_projection_flags_a_negative_end_of_month(account):
    _tx(account, "100", day=1)
    _recurrence(account, "-500", start_day=25)

    projection = project_account(account, as_of=TODAY)

    assert projection.projected_balance == Decimal("-400")
    assert projection.goes_negative is True


def test_household_total_sums_every_active_account(household):
    user = UserFactory()
    joint = FinancialAccount.objects.create(
        household=household, name="Commun", currency_id="EUR"
    )
    personal = FinancialAccount.objects.create(
        household=household, name="Perso", currency_id="EUR", owner=user
    )
    _tx(joint, "1000", day=1)
    _tx(personal, "500", day=1)
    _recurrence(joint, "-300", start_day=25)

    result = project_household(household, as_of=TODAY)

    assert result["totals"]["current"] == Decimal("1500")
    assert result["totals"]["movement"] == Decimal("-300")
    assert result["totals"]["projected"] == Decimal("1200")
    assert len(result["projections"]) == 2


def test_archived_accounts_are_excluded_from_the_household_total(household):
    live = FinancialAccount.objects.create(household=household, name="Actif", currency_id="EUR")
    archived = FinancialAccount.objects.create(
        household=household, name="Clôturé", currency_id="EUR", is_archived=True
    )
    _tx(live, "100", day=1)
    _tx(archived, "9999", day=1)

    result = project_household(household, as_of=TODAY)

    assert result["totals"]["projected"] == Decimal("100")


def test_household_total_converts_foreign_accounts(household):
    Currency.objects.get_or_create(code="USD", defaults={"name": "Dollar", "symbol": "$"})
    ExchangeRate.objects.create(
        base_currency_id="EUR", quote_currency_id="USD", date=date(2026, 1, 1), rate=Decimal("2")
    )
    usd = FinancialAccount.objects.create(household=household, name="USD", currency_id="USD")
    _tx(usd, "200", day=1)
    _recurrence(usd, "-100", start_day=25)

    result = project_household(household, as_of=TODAY)

    assert result["totals"]["current"] == Decimal("100")  # 200 USD -> 100 EUR
    assert result["totals"]["movement"] == Decimal("-50")
    assert result["warnings"] == []


def test_unconvertible_account_is_counted_and_flagged(household):
    Currency.objects.get_or_create(code="GBP", defaults={"name": "Livre", "symbol": "£"})
    gbp = FinancialAccount.objects.create(household=household, name="GBP", currency_id="GBP")
    _tx(gbp, "80", day=1)

    result = project_household(household, as_of=TODAY)

    assert result["totals"]["projected"] == Decimal("80")
    assert any("non converti" in w for w in result["warnings"])


def test_projection_is_isolated_between_households(household):
    other = HouseholdFactory()
    mine = FinancialAccount.objects.create(household=household, name="Moi", currency_id="EUR")
    theirs = FinancialAccount.objects.create(household=other, name="Eux", currency_id="EUR")
    _tx(mine, "100", day=1)
    _tx(theirs, "9999", day=1)

    result = project_household(household, as_of=TODAY)

    assert result["totals"]["projected"] == Decimal("100")
    assert [p.account.name for p in result["projections"]] == ["Moi"]


def test_projection_appears_on_the_account_list_page(client, household, account):
    from apps.accounts.tests.factories import HouseholdMembershipFactory

    user = UserFactory()
    HouseholdMembershipFactory(user=user, household=household)
    client.force_login(user)
    _tx(account, "1000", day=1)
    _recurrence(account, "-300", start_day=28)

    response = client.get("/budget/comptes/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "Solde projeté" in body
    assert "None" not in body


def test_projection_appears_on_the_dashboard(client, household, account):
    from apps.accounts.tests.factories import HouseholdMembershipFactory

    user = UserFactory()
    HouseholdMembershipFactory(user=user, household=household)
    client.force_login(user)
    _tx(account, "1000", day=1)

    response = client.get("/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "Solde projeté fin de mois" in body
    assert "Prochaines échéances" in body
    assert "None" not in body
