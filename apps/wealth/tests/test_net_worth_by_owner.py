"""Net worth sliced per member, and consolidated for the family.

The family figure and the per-person figures come from the same items, so
they can never disagree — that invariant is what these tests pin down.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import (
    CurrencyFactory,
    HouseholdFactory,
    HouseholdMembershipFactory,
    UserFactory,
)
from apps.budget.models import FinancialAccount, Transaction
from apps.wealth.models import Liability, PriceSnapshot, RealAsset, Security, SecurityTransaction
from apps.wealth.services import compute_net_worth, compute_net_worth_by_owner

pytestmark = pytest.mark.django_db


@pytest.fixture
def family():
    CurrencyFactory()
    household = HouseholdFactory(base_currency="EUR")
    julien = UserFactory(first_name="Julien")
    marie = UserFactory(first_name="Marie")
    HouseholdMembershipFactory(user=julien, household=household)
    HouseholdMembershipFactory(user=marie, household=household)
    return household, julien, marie


def _account(household, name, owner=None, **kwargs):
    return FinancialAccount.objects.create(
        household=household, name=name, owner=owner, currency_id="EUR", **kwargs
    )


def _deposit(account, amount):
    Transaction.objects.create(
        household=account.household, account=account, currency_id="EUR",
        date=date(2026, 1, 5), amount=Decimal(amount), description="Dépôt",
    )


def _group(result, label):
    return next(g for g in result["groups"] if g.label == label)


def test_each_member_and_commun_gets_its_own_slice(family):
    household, julien, marie = family
    _deposit(_account(household, "Compte Julien", owner=julien), "1000")
    _deposit(_account(household, "Compte Marie", owner=marie), "600")
    _deposit(_account(household, "Compte commun"), "400")

    result = compute_net_worth_by_owner(household, viewer=julien)

    assert [g.label for g in result["groups"]] == ["Moi", "Commun au foyer", "Marie"]
    assert _group(result, "Moi").net_worth == Decimal("1000")
    assert _group(result, "Commun au foyer").net_worth == Decimal("400")
    assert _group(result, "Marie").net_worth == Decimal("600")


def test_the_family_total_is_the_sum_of_the_groups(family):
    household, julien, marie = family
    _deposit(_account(household, "Compte Julien", owner=julien), "1000")
    _deposit(_account(household, "Compte Marie", owner=marie), "600")
    _deposit(_account(household, "Compte commun"), "400")
    RealAsset.objects.create(
        household=household, owner=None, type=RealAsset.Type.REAL_ESTATE, name="Maison",
        acquisition_value=Decimal("300000"), current_value=Decimal("350000"), currency_id="EUR",
    )
    Liability.objects.create(
        household=household, owner=None, type=Liability.Type.MORTGAGE, name="Crédit",
        principal=Decimal("250000"), remaining_balance=Decimal("200000"), currency_id="EUR",
    )

    result = compute_net_worth_by_owner(household, viewer=julien)

    assert result["net_worth"] == sum(g.net_worth for g in result["groups"])
    assert result["net_worth"] == Decimal("152000")  # 2000 cash + 350000 - 200000


def test_the_family_total_matches_the_flat_computation(family):
    """The consolidated view and the plain household total are the same
    numbers sliced differently — if these ever diverge, one of them lies."""
    household, julien, marie = family
    _deposit(_account(household, "Compte Julien", owner=julien), "1000")
    _deposit(_account(household, "Compte commun"), "400")
    Liability.objects.create(
        household=household, owner=marie, type=Liability.Type.LOAN, name="Prêt Marie",
        principal=Decimal("5000"), remaining_balance=Decimal("3000"), currency_id="EUR",
    )

    flat_assets, flat_liabilities, flat_net, _ = compute_net_worth(household)
    grouped = compute_net_worth_by_owner(household, viewer=julien)

    assert grouped["total_assets"] == flat_assets
    assert grouped["total_liabilities"] == flat_liabilities
    assert grouped["net_worth"] == flat_net


def test_the_same_household_reads_differently_from_each_session(family):
    household, julien, marie = family
    _deposit(_account(household, "Compte Julien", owner=julien), "1000")
    _deposit(_account(household, "Compte Marie", owner=marie), "600")

    seen_by_julien = compute_net_worth_by_owner(household, viewer=julien)
    seen_by_marie = compute_net_worth_by_owner(household, viewer=marie)

    assert [g.label for g in seen_by_julien["groups"]] == ["Moi", "Commun au foyer", "Marie"]
    assert [g.label for g in seen_by_marie["groups"]] == ["Moi", "Commun au foyer", "Julien"]
    # Same money either way — only the labelling and ordering move.
    assert seen_by_julien["net_worth"] == seen_by_marie["net_worth"] == Decimal("1600")
    assert _group(seen_by_julien, "Moi").net_worth == Decimal("1000")
    assert _group(seen_by_marie, "Moi").net_worth == Decimal("600")


def test_holdings_are_attributed_through_the_account_they_sit_in(family):
    """A position belongs to whoever owns the brokerage account — the same
    rule budgets use, so the two views never disagree about whose money it is."""
    household, julien, marie = family
    account = _account(
        household, "Bolero Julien", owner=julien, type=FinancialAccount.Type.INVESTMENT
    )
    security = Security.objects.create(
        identifier="IE00TEST", name="ETF Monde", type=Security.Type.ETF, currency_id="EUR"
    )
    SecurityTransaction.objects.create(
        household=household, account=account, security=security, date=date(2024, 1, 1),
        type=SecurityTransaction.Type.BUY, quantity=Decimal("100"), price=Decimal("50"),
        fees=Decimal("0"), currency_id="EUR",
    )
    PriceSnapshot.objects.create(security=security, date=date(2026, 6, 1), price=Decimal("80"))

    result = compute_net_worth_by_owner(household, viewer=julien)

    assert _group(result, "Moi").net_worth == Decimal("8000")
    assert _group(result, "Marie").net_worth == Decimal("0")


def test_a_personal_liability_reduces_only_that_member(family):
    household, julien, marie = family
    _deposit(_account(household, "Compte Marie", owner=marie), "5000")
    Liability.objects.create(
        household=household, owner=marie, type=Liability.Type.LOAN, name="Prêt auto",
        principal=Decimal("10000"), remaining_balance=Decimal("7000"), currency_id="EUR",
    )

    result = compute_net_worth_by_owner(household, viewer=julien)

    marie_group = _group(result, "Marie")
    assert marie_group.assets == Decimal("5000")
    assert marie_group.liabilities == Decimal("7000")
    assert marie_group.net_worth == Decimal("-2000")
    assert _group(result, "Moi").net_worth == Decimal("0")


def test_a_member_with_nothing_still_appears(family):
    household, julien, marie = family
    _deposit(_account(household, "Compte Julien", owner=julien), "100")

    result = compute_net_worth_by_owner(household, viewer=julien)

    assert "Marie" in [g.label for g in result["groups"]]
    assert _group(result, "Marie").net_worth == Decimal("0")


def test_grouping_stays_inside_the_household(family):
    household, julien, _ = family
    other_household = HouseholdFactory()
    outsider = UserFactory(first_name="Etranger")
    HouseholdMembershipFactory(user=outsider, household=other_household)
    _deposit(
        FinancialAccount.objects.create(
            household=other_household, name="Compte externe", owner=outsider, currency_id="EUR"
        ),
        "9999",
    )
    _deposit(_account(household, "Compte Julien", owner=julien), "100")

    result = compute_net_worth_by_owner(household, viewer=julien)

    assert result["net_worth"] == Decimal("100")
    assert "Etranger" not in [g.label for g in result["groups"]]


def test_patrimoine_page_shows_the_family_total_and_each_perimeter(client, family):
    household, julien, marie = family
    _deposit(_account(household, "Compte Julien", owner=julien), "1000")
    _deposit(_account(household, "Compte Marie", owner=marie), "600")
    _deposit(_account(household, "Compte commun"), "400")

    client.force_login(julien)
    body = client.get("/patrimoine/").content.decode()

    assert "Patrimoine net · famille" in body
    assert "2000,00" in body  # consolidated
    assert "Moi" in body and "Marie" in body and "Commun au foyer" in body
    assert "None" not in body
