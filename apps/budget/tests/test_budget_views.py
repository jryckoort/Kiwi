from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import (
    CurrencyFactory,
    HouseholdFactory,
    HouseholdMembershipFactory,
    UserFactory,
)
from apps.budget.models import BudgetLine, Category, FinancialAccount, RecurringTransaction, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    CurrencyFactory()
    user = UserFactory(first_name="Julien")
    household = HouseholdFactory(base_currency="EUR")
    HouseholdMembershipFactory(user=user, household=household)
    client.force_login(user)
    return client, user, household


def test_budget_page_renders_plan_and_actuals(logged_in):
    client, user, household = logged_in
    account = FinancialAccount.objects.create(
        household=household, name="Compte commun", currency_id="EUR"
    )
    groceries = Category.objects.create(
        household=household, name="Courses", kind=Category.Kind.EXPENSE
    )
    BudgetLine.objects.create(
        household=household, category=groceries, month=date(2026, 3, 1),
        owner=None, planned_amount=Decimal("600"),
    )
    Transaction.objects.create(
        household=household, account=account, category=groceries, currency_id="EUR",
        date=date(2026, 3, 10), amount=Decimal("-450"), description="Colruyt",
    )

    response = client.get("/budget/budgets/?mois=2026-03")
    body = response.content.decode()

    assert response.status_code == 200
    assert "Courses" in body
    assert "600,00" in body  # planned
    assert "450,00" in body  # actual


def test_budget_page_falls_back_to_current_month_on_bad_input(logged_in):
    client, _, _ = logged_in

    response = client.get("/budget/budgets/?mois=pas-une-date")

    assert response.status_code == 200


def test_posting_a_budget_line_creates_it_for_the_displayed_month(logged_in):
    client, _, household = logged_in
    groceries = Category.objects.create(
        household=household, name="Courses", kind=Category.Kind.EXPENSE
    )

    response = client.post(
        "/budget/budgets/?mois=2026-05",
        {"category": groceries.pk, "owner": "", "planned_amount": "500"},
    )

    assert response.status_code == 302
    line = BudgetLine.objects.get()
    assert line.month == date(2026, 5, 1)
    assert line.owner is None
    assert line.planned_amount == Decimal("500")


def test_reposting_the_same_line_updates_instead_of_erroring(logged_in):
    """The unique constraint must not surface as a crash when a user simply
    re-enters an amount for a category they already budgeted."""
    client, _, household = logged_in
    groceries = Category.objects.create(
        household=household, name="Courses", kind=Category.Kind.EXPENSE
    )

    client.post(
        "/budget/budgets/?mois=2026-05",
        {"category": groceries.pk, "owner": "", "planned_amount": "500"},
    )
    response = client.post(
        "/budget/budgets/?mois=2026-05",
        {"category": groceries.pk, "owner": "", "planned_amount": "650"},
    )

    assert response.status_code == 302
    assert BudgetLine.objects.count() == 1
    assert BudgetLine.objects.get().planned_amount == Decimal("650")


def test_copy_previous_month_action(logged_in):
    client, _, household = logged_in
    groceries = Category.objects.create(
        household=household, name="Courses", kind=Category.Kind.EXPENSE
    )
    BudgetLine.objects.create(
        household=household, category=groceries, month=date(2026, 4, 1),
        owner=None, planned_amount=Decimal("600"),
    )

    response = client.post("/budget/budgets/reprendre/", {"mois": "2026-05"})

    assert response.status_code == 302
    assert BudgetLine.objects.filter(month=date(2026, 5, 1)).exists()


def test_recurring_pages_render_and_create(logged_in):
    client, _, household = logged_in
    account = FinancialAccount.objects.create(
        household=household, name="Compte commun", currency_id="EUR"
    )

    assert client.get("/budget/recurrentes/").status_code == 200

    response = client.post(
        "/budget/recurrentes/nouvelle/",
        {
            "description": "Loyer",
            "account": account.pk,
            "category": "",
            "amount": "-1200",
            "frequency": "monthly",
            "interval": "1",
            "start_date": "2026-01-05",
            "end_date": "",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    recurrence = RecurringTransaction.objects.get()
    assert recurrence.description == "Loyer"
    assert recurrence.household == household
    # Forecast-only: declaring a recurrence must not create a real movement.
    assert Transaction.objects.count() == 0


def test_cannot_budget_a_foreign_households_category(logged_in):
    client, _, _ = logged_in
    other_household = HouseholdFactory()
    foreign_category = Category.objects.create(
        household=other_household, name="Courses", kind=Category.Kind.EXPENSE
    )

    response = client.post(
        "/budget/budgets/?mois=2026-05",
        {"category": foreign_category.pk, "owner": "", "planned_amount": "500"},
    )

    assert response.status_code == 200  # re-rendered with an error, no redirect
    assert not BudgetLine.objects.exists()


def test_cannot_attach_a_recurrence_to_a_foreign_account(logged_in):
    client, _, _ = logged_in
    other_household = HouseholdFactory()
    foreign_account = FinancialAccount.objects.create(
        household=other_household, name="Compte externe", currency_id="EUR"
    )

    response = client.post(
        "/budget/recurrentes/nouvelle/",
        {
            "description": "Intrusion",
            "account": foreign_account.pk,
            "category": "",
            "amount": "-10",
            "frequency": "monthly",
            "interval": "1",
            "start_date": "2026-01-05",
            "end_date": "",
            "is_active": "on",
        },
    )

    assert response.status_code == 200
    assert not RecurringTransaction.objects.exists()


def test_cannot_delete_another_households_budget_line(logged_in):
    client, _, _ = logged_in
    other_household = HouseholdFactory()
    foreign_category = Category.objects.create(
        household=other_household, name="Courses", kind=Category.Kind.EXPENSE
    )
    foreign_line = BudgetLine.objects.create(
        household=other_household, category=foreign_category, month=date(2026, 5, 1),
        owner=None, planned_amount=Decimal("100"),
    )

    response = client.post(f"/budget/budgets/ligne/{foreign_line.pk}/supprimer/")

    assert response.status_code == 404
    assert BudgetLine.objects.filter(pk=foreign_line.pk).exists()
