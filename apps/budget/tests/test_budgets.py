from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import (
    CurrencyFactory,
    HouseholdFactory,
    HouseholdMembershipFactory,
    UserFactory,
)
from apps.budget.budgets import budget_vs_actuals, copy_budget_from_previous_month, month_bounds
from apps.budget.models import BudgetLine, Category, FinancialAccount, RecurringTransaction, Transaction
from apps.fx.models import Currency, ExchangeRate

pytestmark = pytest.mark.django_db

MONTH = date(2026, 3, 1)


@pytest.fixture
def setup():
    CurrencyFactory()
    household = HouseholdFactory(base_currency="EUR")
    julien = UserFactory(first_name="Julien")
    partner = UserFactory(first_name="Marie")
    HouseholdMembershipFactory(user=julien, household=household)
    HouseholdMembershipFactory(user=partner, household=household)

    joint = FinancialAccount.objects.create(
        household=household, name="Compte commun", currency_id="EUR"
    )
    julien_account = FinancialAccount.objects.create(
        household=household, name="Compte Julien", currency_id="EUR", owner=julien
    )
    groceries = Category.objects.create(
        household=household, name="Courses", kind=Category.Kind.EXPENSE
    )
    return household, julien, partner, joint, julien_account, groceries


def _spend(household, account, category, amount, day=15, currency="EUR"):
    return Transaction.objects.create(
        household=household,
        account=account,
        category=category,
        currency_id=currency,
        date=date(2026, 3, day),
        amount=Decimal(amount),
        description="Dépense",
    )


def _find(groups, label, category_name):
    group = next(g for g in groups if g.label == label)
    return next(r for r in group.rows if r.category and r.category.name == category_name)


def test_month_bounds():
    assert month_bounds(date(2026, 2, 17)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_actuals_are_attributed_by_account_owner(setup):
    household, julien, _, joint, julien_account, groceries = setup
    BudgetLine.objects.create(
        household=household, category=groceries, month=MONTH, owner=None,
        planned_amount=Decimal("600"),
    )
    BudgetLine.objects.create(
        household=household, category=groceries, month=MONTH, owner=julien,
        planned_amount=Decimal("200"),
    )
    _spend(household, joint, groceries, "-450")
    _spend(household, julien_account, groceries, "-120")

    groups, _ = budget_vs_actuals(household, MONTH)

    commun = _find(groups, "Commun", "Courses")
    assert commun.planned == Decimal("600")
    assert commun.actual == Decimal("450")
    assert commun.variance == Decimal("150")

    perso = _find(groups, "Julien", "Courses")
    assert perso.planned == Decimal("200")
    assert perso.actual == Decimal("120")


def test_commun_group_is_listed_first(setup):
    household, julien, _, joint, julien_account, groceries = setup
    _spend(household, julien_account, groceries, "-10")
    _spend(household, joint, groceries, "-10")

    groups, _ = budget_vs_actuals(household, MONTH)

    assert groups[0].label == "Commun"


def test_overspending_is_flagged(setup):
    household, _, _, joint, _, groceries = setup
    BudgetLine.objects.create(
        household=household, category=groceries, month=MONTH, owner=None,
        planned_amount=Decimal("100"),
    )
    _spend(household, joint, groceries, "-160")

    row = _find(budget_vs_actuals(household, MONTH)[0], "Commun", "Courses")

    assert row.is_over_budget is True
    assert row.variance == Decimal("-60")
    assert row.progress_percent == 160


def test_spending_outside_any_budget_line_still_appears(setup):
    """An unbudgeted category must not be invisible — that is exactly where
    overspending would hide."""
    household, _, _, joint, _, groceries = setup
    _spend(household, joint, groceries, "-75")

    row = _find(budget_vs_actuals(household, MONTH)[0], "Commun", "Courses")

    assert row.planned == Decimal("0")
    assert row.actual == Decimal("75")


def test_uncategorized_spending_is_kept_in_its_own_row(setup):
    household, _, _, joint, _, _ = setup
    _spend(household, joint, None, "-30")

    groups, _ = budget_vs_actuals(household, MONTH)
    commun = next(g for g in groups if g.label == "Commun")
    uncategorized = next(r for r in commun.rows if r.category is None)

    assert uncategorized.actual == Decimal("30")


def test_income_is_compared_without_sign_flip(setup):
    household, julien, _, _, julien_account, _ = setup
    salary = Category.objects.create(
        household=household, name="Salaire", kind=Category.Kind.INCOME
    )
    BudgetLine.objects.create(
        household=household, category=salary, month=MONTH, owner=julien,
        planned_amount=Decimal("3000"),
    )
    _spend(household, julien_account, salary, "3100")

    row = _find(budget_vs_actuals(household, MONTH)[0], "Julien", "Salaire")

    assert row.actual == Decimal("3100")
    assert row.variance == Decimal("-100")  # earned more than planned


def test_transactions_outside_the_month_are_excluded(setup):
    household, _, _, joint, _, groceries = setup
    _spend(household, joint, groceries, "-50", day=15)
    Transaction.objects.create(
        household=household, account=joint, category=groceries, currency_id="EUR",
        date=date(2026, 4, 1), amount=Decimal("-999"), description="Mois suivant",
    )

    row = _find(budget_vs_actuals(household, MONTH)[0], "Commun", "Courses")

    assert row.actual == Decimal("50")


def test_recurring_expected_is_reported_alongside_actuals(setup):
    household, _, _, joint, _, groceries = setup
    rent_category = Category.objects.create(
        household=household, name="Loyer", kind=Category.Kind.EXPENSE
    )
    RecurringTransaction.objects.create(
        household=household, account=joint, category=rent_category,
        description="Loyer", amount=Decimal("-1200"), currency_id="EUR",
        frequency=RecurringTransaction.Frequency.MONTHLY, start_date=date(2026, 1, 5),
    )

    row = _find(budget_vs_actuals(household, MONTH)[0], "Commun", "Loyer")

    assert row.recurring_expected == Decimal("1200")
    assert row.actual == Decimal("0")  # forecast only, never materialized


def test_foreign_currency_actuals_are_converted(setup):
    household, _, _, joint, _, groceries = setup
    Currency.objects.get_or_create(code="USD", defaults={"name": "Dollar", "symbol": "$"})
    ExchangeRate.objects.create(
        base_currency_id="EUR", quote_currency_id="USD", date=date(2026, 1, 1), rate=Decimal("2")
    )
    usd_account = FinancialAccount.objects.create(
        household=household, name="Compte USD", currency_id="USD"
    )
    _spend(household, usd_account, groceries, "-100", currency="USD")

    row = _find(budget_vs_actuals(household, MONTH)[0], "Commun", "Courses")

    assert row.actual == Decimal("50")  # 100 USD at 2 USD per EUR


def test_unconvertible_currency_is_counted_and_flagged_once(setup):
    """The amount must still be counted rather than dropped, and repeating the
    same warning once per transaction would drown the page in noise.
    """
    household, _, _, joint, _, groceries = setup
    Currency.objects.get_or_create(code="GBP", defaults={"name": "Livre", "symbol": "£"})
    gbp_account = FinancialAccount.objects.create(
        household=household, name="Compte GBP", currency_id="GBP"
    )
    _spend(household, gbp_account, groceries, "-20", day=3, currency="GBP")
    _spend(household, gbp_account, groceries, "-20", day=4, currency="GBP")

    groups, warnings = budget_vs_actuals(household, MONTH)

    assert _find(groups, "Commun", "Courses").actual == Decimal("40")
    assert warnings == ["Dépense : montant en GBP non converti (taux indisponible)"]


def test_copy_from_previous_month_seeds_and_does_not_overwrite(setup):
    household, julien, _, _, _, groceries = setup
    BudgetLine.objects.create(
        household=household, category=groceries, month=date(2026, 2, 1), owner=None,
        planned_amount=Decimal("600"),
    )
    BudgetLine.objects.create(
        household=household, category=groceries, month=date(2026, 2, 1), owner=julien,
        planned_amount=Decimal("150"),
    )
    # A line already set for March by hand must survive the copy.
    BudgetLine.objects.create(
        household=household, category=groceries, month=MONTH, owner=julien,
        planned_amount=Decimal("999"),
    )

    created = copy_budget_from_previous_month(household, MONTH)

    assert created == 1  # only the commun line was missing
    assert BudgetLine.objects.get(month=MONTH, owner=julien).planned_amount == Decimal("999")
    assert BudgetLine.objects.get(month=MONTH, owner=None).planned_amount == Decimal("600")


def test_budget_lines_are_isolated_between_households(setup):
    household, _, _, _, _, groceries = setup
    other = HouseholdFactory()
    other_category = Category.objects.create(
        household=other, name="Courses", kind=Category.Kind.EXPENSE
    )
    BudgetLine.objects.create(
        household=other, category=other_category, month=MONTH, owner=None,
        planned_amount=Decimal("5000"),
    )
    BudgetLine.objects.create(
        household=household, category=groceries, month=MONTH, owner=None,
        planned_amount=Decimal("600"),
    )

    groups, _ = budget_vs_actuals(household, MONTH)
    planned = sum(g.planned_total for g in groups)

    assert planned == Decimal("600")
