"""A caller-supplied redirect target must never leave this site — otherwise
a crafted link could bounce a freshly-signed-in user onto a phishing page.
"""

import pytest

from apps.accounts.tests.factories import HouseholdFactory, HouseholdMembershipFactory, UserFactory

pytestmark = pytest.mark.django_db

SIGNUP_PAYLOAD = {
    "first_name": "V",
    "last_name": "T",
    "password1": "SuperSecret123!",
    "password2": "SuperSecret123!",
}


def test_signup_ignores_external_next_target(client):
    response = client.post(
        "/accounts/signup/?next=https://evil.example.com/phishing",
        {**SIGNUP_PAYLOAD, "email": "victim@example.com"},
    )

    assert response.status_code == 302
    assert not response["Location"].startswith("https://evil.example.com")


def test_signup_still_honours_an_internal_next_target(client):
    response = client.post(
        "/accounts/signup/?next=/budget/comptes/",
        {**SIGNUP_PAYLOAD, "email": "someone@example.com"},
    )

    assert response.status_code == 302
    assert response["Location"] == "/budget/comptes/"


def test_household_switch_ignores_external_referer(client):
    user = UserFactory()
    household = HouseholdFactory()
    HouseholdMembershipFactory(user=user, household=household)
    client.force_login(user)

    response = client.post(
        f"/accounts/household/{household.id}/switch/",
        HTTP_REFERER="https://evil.example.com/phishing",
    )

    assert response.status_code == 302
    assert not response["Location"].startswith("https://evil.example.com")


def test_household_switch_returns_to_internal_referer(client):
    user = UserFactory()
    household = HouseholdFactory()
    HouseholdMembershipFactory(user=user, household=household)
    client.force_login(user)

    response = client.post(
        f"/accounts/household/{household.id}/switch/",
        HTTP_REFERER="/patrimoine/",
    )

    assert response["Location"] == "/patrimoine/"
