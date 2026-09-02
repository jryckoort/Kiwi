"""Budget-versus-actuals for one month.

Actuals are attributed to a person through the account a transaction sits on:
spending on a personal account counts against that member's budget, spending
on a joint account counts against the household's commun budget. That keeps
attribution automatic — there is nothing extra to tag when entering or
importing a transaction.

Planned amounts are stored as positive magnitudes ("Courses : 600"), so
actuals are normalized to magnitudes too: expenses are sign-flipped, income
is taken as-is. A category with no budget line still shows up with planned=0
so overspending outside the plan can't hide.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from apps.fx.services import to_base_currency

from .models import BudgetLine, Category, RecurringTransaction, Transaction
from .recurring import expected_amount_between


def month_bounds(month):
    """First and last day of the month ``month`` falls in."""
    first = month.replace(day=1)
    return first, first + relativedelta(months=1) - relativedelta(days=1)


def current_month():
    return date.today().replace(day=1)


@dataclass
class BudgetRow:
    category: Category
    owner: object  # User or None (None = commun)
    planned: Decimal = Decimal(0)
    actual: Decimal = Decimal(0)
    recurring_expected: Decimal = Decimal(0)

    @property
    def variance(self):
        """Positive means room left in the budget, negative means overspent."""
        return self.planned - self.actual

    @property
    def progress_percent(self):
        if not self.planned:
            return None
        return int(min(self.actual / self.planned * 100, 999))

    @property
    def is_over_budget(self):
        return bool(self.planned) and self.actual > self.planned


@dataclass
class BudgetGroup:
    """All rows belonging to one member, or to the commun budget."""

    owner: object  # User or None
    rows: list = field(default_factory=list)

    @property
    def label(self):
        return self.owner.get_short_name() if self.owner else "Commun"

    @property
    def planned_total(self):
        return sum((row.planned for row in self.rows), Decimal(0))

    @property
    def actual_total(self):
        return sum((row.actual for row in self.rows), Decimal(0))

    @property
    def variance_total(self):
        return self.planned_total - self.actual_total


def _magnitude(amount, kind):
    """Planned amounts are positive, so actuals are compared as magnitudes."""
    return -amount if kind == Category.Kind.EXPENSE else amount


def budget_vs_actuals(household, month):
    """Return (groups, warnings) comparing plan and reality for one month."""
    start, end = month_bounds(month)
    base_currency = household.base_currency
    warnings = []

    rows = {}  # (category_id or None, owner_id or None) -> BudgetRow

    def row_for(category, owner):
        key = (category.id if category else None, owner.id if owner else None)
        if key not in rows:
            rows[key] = BudgetRow(category=category, owner=owner)
        return rows[key]

    for line in BudgetLine.objects.for_household(household).filter(
        month=start
    ).select_related("category", "owner"):
        row_for(line.category, line.owner).planned += line.planned_amount

    transactions = (
        Transaction.objects.for_household(household)
        .filter(date__gte=start, date__lte=end)
        .select_related("category", "account", "account__owner", "currency")
    )
    for transaction in transactions:
        amount = to_base_currency(
            transaction.amount,
            transaction.currency_id,
            base_currency,
            transaction.description or transaction.account.name,
            warnings,
            on_date=transaction.date,
        )
        kind = transaction.category.kind if transaction.category else Category.Kind.EXPENSE
        row = row_for(transaction.category, transaction.account.owner)
        row.actual += _magnitude(amount, kind)

    for recurrence in (
        RecurringTransaction.objects.for_household(household)
        .filter(is_active=True)
        .select_related("category", "account", "account__owner", "currency")
    ):
        expected = expected_amount_between(recurrence, start, end)
        if not expected:
            continue
        expected = to_base_currency(
            expected,
            recurrence.currency_id,
            base_currency,
            recurrence.description,
            warnings,
            on_date=start,
        )
        kind = recurrence.category.kind if recurrence.category else Category.Kind.EXPENSE
        row = row_for(recurrence.category, recurrence.owner)
        row.recurring_expected += _magnitude(expected, kind)

    groups = {}
    for row in rows.values():
        owner_id = row.owner.id if row.owner else None
        if owner_id not in groups:
            groups[owner_id] = BudgetGroup(owner=row.owner)
        groups[owner_id].rows.append(row)

    for group in groups.values():
        group.rows.sort(key=lambda r: (r.category is None, r.category.name if r.category else ""))

    # Commun first, then members by name.
    ordered = sorted(
        groups.values(), key=lambda g: (g.owner is not None, g.label.lower() if g.owner else "")
    )
    # Deduplicate identical warnings from many transactions in one currency.
    return ordered, list(dict.fromkeys(warnings))


def copy_budget_from_previous_month(household, month):
    """Seed a month's budget from the previous one. Existing lines are kept."""
    start, _ = month_bounds(month)
    previous = start - relativedelta(months=1)

    created = 0
    for line in BudgetLine.objects.for_household(household).filter(month=previous):
        _, was_created = BudgetLine.objects.get_or_create(
            household=household,
            category=line.category,
            owner=line.owner,
            month=start,
            defaults={"planned_amount": line.planned_amount},
        )
        created += was_created
    return created
