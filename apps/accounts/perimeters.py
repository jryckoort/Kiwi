"""Grouping household data by who it belongs to.

Everything in a household is visible to every member — the household *is* the
trust boundary, and ``owner`` says who something belongs to, not who may see
it. What this module provides is a single, consistent way to present that
ownership, so accounts, budgets and net worth all read the same way.

Perimeters are ordered from the viewer outwards:

    Moi  →  Commun au foyer  →  chaque autre membre (par ordre alphabétique)

``owner = None`` means commun, matching ``PersonallyOwnedModel``.
"""

from dataclasses import dataclass, field

COMMUN_LABEL = "Commun au foyer"
COMMUN_SHORT = "Commun"


def _display_name(user):
    return user.get_short_name() or user.email


def perimeter_labels(owner, viewer):
    """Return ``(label, short_label)`` for one owner as seen by ``viewer``."""
    if owner is None:
        return COMMUN_LABEL, COMMUN_SHORT
    if viewer is not None and owner.pk == viewer.pk:
        return "Moi", "Moi"
    return _display_name(owner), _display_name(owner)


def sort_key(owner, viewer):
    """Order perimeters from the viewer outwards: me, then commun, then others."""
    if owner is not None and viewer is not None and owner.pk == viewer.pk:
        return (0, "")
    if owner is None:
        return (1, "")
    return (2, _display_name(owner).lower())


@dataclass
class Perimeter:
    """One owner's slice of the household, plus whatever rows belong to it."""

    owner: object  # User, or None for commun
    viewer: object = None
    rows: list = field(default_factory=list)

    @property
    def label(self):
        return perimeter_labels(self.owner, self.viewer)[0]

    @property
    def short_label(self):
        return perimeter_labels(self.owner, self.viewer)[1]

    @property
    def is_commun(self):
        return self.owner is None

    @property
    def is_mine(self):
        return (
            self.owner is not None
            and self.viewer is not None
            and self.owner.pk == self.viewer.pk
        )


def group_by_owner(
    items,
    viewer,
    owner_of=lambda item: item.owner,
    include_owners=(),
    include_commun=False,
):
    """Bucket ``items`` into ordered perimeters.

    ``include_owners`` forces empty perimeters to appear anyway — so a member
    with nothing yet still shows up rather than silently vanishing from the
    household view. ``include_commun`` does the same for the joint perimeter,
    which is a permanent part of a household rather than an optional member.
    """
    buckets = {}

    def bucket_for(owner):
        key = owner.pk if owner is not None else None
        if key not in buckets:
            buckets[key] = Perimeter(owner=owner, viewer=viewer)
        return buckets[key]

    if include_commun:
        bucket_for(None)
    for owner in include_owners:
        bucket_for(owner)

    for item in items:
        bucket_for(owner_of(item)).rows.append(item)

    return sorted(buckets.values(), key=lambda p: sort_key(p.owner, viewer))
