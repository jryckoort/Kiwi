"""Perimeters group a household's data by who it belongs to.

Nothing is hidden here — the household is the trust boundary and both members
see everything. What is viewer-dependent is only *presentation*: your own
slice is labelled « Moi » and listed first.
"""

import pytest

from apps.accounts.perimeters import (
    Perimeter,
    group_by_owner,
    perimeter_labels,
    sort_key,
)
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class Item:
    """Anything with an owner can be grouped; the helper is model-agnostic."""

    def __init__(self, owner, name):
        self.owner = owner
        self.name = name


def test_my_own_perimeter_is_labelled_moi():
    me = UserFactory(first_name="Julien")

    assert perimeter_labels(me, me) == ("Moi", "Moi")


def test_another_member_is_labelled_by_name():
    me = UserFactory(first_name="Julien")
    her = UserFactory(first_name="Marie")

    assert perimeter_labels(her, me) == ("Marie", "Marie")


def test_none_owner_is_commun():
    me = UserFactory()

    assert perimeter_labels(None, me) == ("Commun au foyer", "Commun")


def test_order_is_me_then_commun_then_others():
    me = UserFactory(first_name="Julien")
    marie = UserFactory(first_name="Marie")
    alice = UserFactory(first_name="Alice")

    owners = [marie, None, alice, me]
    ordered = sorted(owners, key=lambda o: sort_key(o, me))

    assert ordered == [me, None, alice, marie]


def test_the_same_household_reads_differently_from_each_session():
    """Julien sees his own accounts as « Moi »; Marie sees hers as « Moi ».
    Same data, different vantage point."""
    julien = UserFactory(first_name="Julien")
    marie = UserFactory(first_name="Marie")
    items = [Item(julien, "Compte Julien"), Item(None, "Commun"), Item(marie, "Compte Marie")]

    seen_by_julien = [p.label for p in group_by_owner(items, julien)]
    seen_by_marie = [p.label for p in group_by_owner(items, marie)]

    assert seen_by_julien == ["Moi", "Commun au foyer", "Marie"]
    assert seen_by_marie == ["Moi", "Commun au foyer", "Julien"]


def test_without_a_viewer_commun_comes_first_and_nobody_is_moi():
    julien = UserFactory(first_name="Julien")
    items = [Item(julien, "Compte Julien"), Item(None, "Commun")]

    labels = [p.label for p in group_by_owner(items, viewer=None)]

    assert labels == ["Commun au foyer", "Julien"]


def test_items_land_in_their_owner_bucket():
    julien = UserFactory(first_name="Julien")
    marie = UserFactory(first_name="Marie")
    items = [
        Item(julien, "Compte Julien"),
        Item(None, "Commun"),
        Item(marie, "Compte Marie"),
        Item(julien, "Livret Julien"),
    ]

    groups = {p.label: [i.name for i in p.rows] for p in group_by_owner(items, julien)}

    assert groups["Moi"] == ["Compte Julien", "Livret Julien"]
    assert groups["Commun au foyer"] == ["Commun"]
    assert groups["Marie"] == ["Compte Marie"]


def test_a_member_with_nothing_still_gets_a_perimeter():
    """Otherwise a spouse who hasn't added an account yet would silently
    disappear from the household view."""
    julien = UserFactory(first_name="Julien")
    marie = UserFactory(first_name="Marie")

    groups = group_by_owner(
        [Item(julien, "Compte")], julien, include_owners=[julien, marie], include_commun=True
    )

    assert [p.label for p in groups] == ["Moi", "Commun au foyer", "Marie"]
    assert next(p for p in groups if p.label == "Marie").rows == []


def test_owner_of_can_reach_through_a_relation():
    """Holdings and projections carry their owner via the account they sit on."""
    julien = UserFactory(first_name="Julien")

    class Wrapper:
        def __init__(self, account_owner):
            self.account = Item(account_owner, "compte")

    groups = group_by_owner(
        [Wrapper(julien), Wrapper(None)], julien, owner_of=lambda w: w.account.owner
    )

    assert [p.label for p in groups] == ["Moi", "Commun au foyer"]


def test_perimeter_flags():
    me = UserFactory()
    her = UserFactory()

    assert Perimeter(owner=me, viewer=me).is_mine is True
    assert Perimeter(owner=her, viewer=me).is_mine is False
    assert Perimeter(owner=None, viewer=me).is_mine is False
    assert Perimeter(owner=None, viewer=me).is_commun is True
    assert Perimeter(owner=me, viewer=me).is_commun is False


def test_a_member_without_a_first_name_falls_back_to_email():
    me = UserFactory(first_name="Julien")
    anonymous = UserFactory(first_name="", last_name="", email="x@example.com")

    assert perimeter_labels(anonymous, me) == ("x@example.com", "x@example.com")
