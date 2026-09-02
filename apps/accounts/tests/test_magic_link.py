from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import MagicLoginToken
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_requesting_a_magic_link_emails_a_token(client):
    user = UserFactory(email="julien@example.com")

    response = client.post("/accounts/magic-login/", {"email": "julien@example.com"})

    assert response.status_code == 200
    assert MagicLoginToken.objects.filter(user=user).count() == 1
    assert len(mail.outbox) == 1
    token = MagicLoginToken.objects.get(user=user)
    assert token.token in mail.outbox[0].body


def test_requesting_a_link_for_unknown_email_sends_nothing_but_looks_identical(client):
    response = client.post("/accounts/magic-login/", {"email": "nobody@example.com"})

    assert response.status_code == 200
    assert len(mail.outbox) == 0
    # Same template/content as the real case — no user enumeration.
    assert b"Si cette adresse correspond" in response.content


def test_repeated_requests_within_a_minute_do_not_spam_new_tokens(client):
    UserFactory(email="julien@example.com")

    client.post("/accounts/magic-login/", {"email": "julien@example.com"})
    client.post("/accounts/magic-login/", {"email": "julien@example.com"})

    assert MagicLoginToken.objects.count() == 1
    assert len(mail.outbox) == 1


def test_valid_token_logs_the_user_in(client):
    user = UserFactory()
    token = MagicLoginToken.objects.create(user=user)

    response = client.get(f"/accounts/magic-login/{token.token}/", follow=True)

    assert response.wsgi_request.user == user
    token.refresh_from_db()
    assert token.used_at is not None


def test_used_token_cannot_be_replayed(client):
    user = UserFactory()
    token = MagicLoginToken.objects.create(user=user, used_at=timezone.now())

    response = client.get(f"/accounts/magic-login/{token.token}/", follow=True)

    assert not response.wsgi_request.user.is_authenticated


def test_expired_token_is_rejected(client):
    user = UserFactory()
    token = MagicLoginToken.objects.create(user=user)
    token.created_at = timezone.now() - timedelta(minutes=30)
    token.save(update_fields=["created_at"])

    response = client.get(f"/accounts/magic-login/{token.token}/", follow=True)

    assert not response.wsgi_request.user.is_authenticated


def test_unknown_token_returns_404(client):
    response = client.get("/accounts/magic-login/does-not-exist/")
    assert response.status_code == 404
