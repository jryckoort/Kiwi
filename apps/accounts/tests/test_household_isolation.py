import pytest

from apps.accounts.tests.factories import (
    CurrencyFactory,
    HouseholdFactory,
    HouseholdMembershipFactory,
    UserFactory,
)
from apps.budget.models import Category, FinancialAccount, Transaction
from apps.wealth.models import RealAsset

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_households():
    CurrencyFactory()
    user_a = UserFactory()
    household_a = HouseholdFactory(name="Foyer A")
    HouseholdMembershipFactory(user=user_a, household=household_a)

    user_b = UserFactory()
    household_b = HouseholdFactory(name="Foyer B")
    HouseholdMembershipFactory(user=user_b, household=household_b)

    return user_a, household_a, user_b, household_b


def test_queryset_for_household_never_leaks(two_households):
    _, household_a, _, household_b = two_households
    account_a = FinancialAccount.objects.create(
        household=household_a, name="Compte A", currency_id="EUR"
    )
    FinancialAccount.objects.create(household=household_b, name="Compte B", currency_id="EUR")

    visible_to_a = FinancialAccount.objects.for_household(household_a)
    assert list(visible_to_a) == [account_a]

    visible_to_b = FinancialAccount.objects.for_household(household_b)
    assert account_a not in visible_to_b


def test_account_list_view_only_shows_own_household(client, two_households):
    user_a, household_a, user_b, household_b = two_households
    FinancialAccount.objects.create(household=household_a, name="Compte A", currency_id="EUR")
    FinancialAccount.objects.create(household=household_b, name="Compte B", currency_id="EUR")

    client.force_login(user_b)
    response = client.get("/budget/comptes/")

    assert response.status_code == 200
    assert b"Compte B" in response.content
    assert b"Compte A" not in response.content


def test_cannot_fetch_another_households_account_detail(client, two_households):
    user_a, household_a, user_b, household_b = two_households
    account_a = FinancialAccount.objects.create(
        household=household_a, name="Compte A", currency_id="EUR"
    )

    client.force_login(user_b)
    response = client.get(f"/budget/comptes/{account_a.pk}/")

    assert response.status_code == 404


def test_cannot_create_transaction_on_foreign_account(client, two_households):
    """The transaction form scopes its account choices to the caller's
    household, so posting a foreign account id must be rejected as invalid
    rather than silently accepted.
    """
    user_a, household_a, user_b, household_b = two_households
    account_a = FinancialAccount.objects.create(
        household=household_a, name="Compte A", currency_id="EUR"
    )

    client.force_login(user_b)
    response = client.post(
        "/budget/transactions/nouvelle/",
        {
            "account": account_a.pk,
            "date": "2026-01-01",
            "amount": "-10.00",
            "description": "Tentative intrusion",
        },
    )

    assert response.status_code == 200  # form re-rendered with an error, no redirect
    assert not Transaction.objects.filter(account=account_a).exists()


def test_real_asset_isolated_between_households(two_households):
    _, household_a, _, household_b = two_households
    asset_a = RealAsset.objects.create(
        household=household_a,
        type=RealAsset.Type.REAL_ESTATE,
        name="Maison",
        acquisition_value=200000,
        current_value=250000,
        currency_id="EUR",
    )

    assert asset_a in RealAsset.objects.for_household(household_a)
    assert asset_a not in RealAsset.objects.for_household(household_b)


def test_category_names_can_collide_across_households(two_households):
    """The uniqueness constraint on Category is scoped per household, so two
    households can each have their own "Courses" category without conflict.
    """
    _, household_a, _, household_b = two_households
    Category.objects.create(household=household_a, name="Courses", kind=Category.Kind.EXPENSE)
    Category.objects.create(household=household_b, name="Courses", kind=Category.Kind.EXPENSE)

    assert Category.objects.for_household(household_a).count() == 1
    assert Category.objects.for_household(household_b).count() == 1
