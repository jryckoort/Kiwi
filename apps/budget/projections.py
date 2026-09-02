"""Projected end-of-month balances.

The projection is deliberately decomposed into three parts so the figure can
be explained rather than trusted blindly:

    solde à aujourd'hui
  + transactions déjà saisies mais datées dans le futur
  + échéances récurrentes restantes
  = solde projeté en fin de mois

Only occurrences *strictly after* today are projected. Anything due earlier
this month is assumed to be already reflected in the balance — it was either
imported from the bank or entered by hand — so projecting it again would
double-count exactly the way materializing recurrences would have.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from apps.fx.services import to_base_currency

from .budgets import month_bounds
from .models import FinancialAccount, RecurringTransaction
from .recurring import occurrences_between


@dataclass
class AccountProjection:
    account: FinancialAccount
    current_balance: Decimal = Decimal(0)
    scheduled_total: Decimal = Decimal(0)
    recurring_total: Decimal = Decimal(0)
    occurrences: list = field(default_factory=list)

    @property
    def projected_balance(self):
        return self.current_balance + self.scheduled_total + self.recurring_total

    @property
    def movement(self):
        """What the projection adds on top of today's balance."""
        return self.scheduled_total + self.recurring_total

    @property
    def goes_negative(self):
        return self.projected_balance < 0


def project_account(account, as_of=None, horizon_end=None):
    """Project one account's balance out to ``horizon_end`` (end of month)."""
    as_of = as_of or date.today()
    if horizon_end is None:
        _, horizon_end = month_bounds(as_of)

    projection = AccountProjection(account=account)

    projection.current_balance = account.transactions.filter(date__lte=as_of).aggregate(
        total=Sum("amount")
    )["total"] or Decimal(0)

    # Movements the user already knows about because they entered them with a
    # future date — ignoring these would understate the projection.
    projection.scheduled_total = account.transactions.filter(
        date__gt=as_of, date__lte=horizon_end
    ).aggregate(total=Sum("amount"))["total"] or Decimal(0)

    recurrences = RecurringTransaction.objects.filter(
        account=account, is_active=True
    ).select_related("category")
    for recurrence in recurrences:
        for occurrence in occurrences_between(recurrence, as_of, horizon_end):
            if occurrence <= as_of:
                continue
            projection.recurring_total += recurrence.amount
            projection.occurrences.append({"date": occurrence, "recurrence": recurrence})

    projection.occurrences.sort(key=lambda row: row["date"])
    return projection


def project_household(household, as_of=None, horizon_end=None):
    """Per-account projections plus a household total in the base currency."""
    as_of = as_of or date.today()
    if horizon_end is None:
        _, horizon_end = month_bounds(as_of)

    base_currency = household.base_currency
    warnings = []

    projections = []
    totals = {"current": Decimal(0), "movement": Decimal(0), "projected": Decimal(0)}

    accounts = (
        FinancialAccount.objects.for_household(household)
        .filter(is_archived=False)
        .select_related("owner", "currency")
    )
    for account in accounts:
        projection = project_account(account, as_of=as_of, horizon_end=horizon_end)
        projections.append(projection)

        totals["current"] += to_base_currency(
            projection.current_balance, account.currency_id, base_currency, account.name, warnings
        )
        totals["movement"] += to_base_currency(
            projection.movement, account.currency_id, base_currency, account.name, warnings
        )

    totals["projected"] = totals["current"] + totals["movement"]

    return {
        "as_of": as_of,
        "horizon_end": horizon_end,
        "projections": projections,
        "totals": totals,
        "base_currency": base_currency,
        "warnings": list(dict.fromkeys(warnings)),
    }
