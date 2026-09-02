"""Occurrence maths for recurring transactions.

Every occurrence is computed as ``start_date + n * period`` rather than by
stepping from the previous occurrence. That anchoring matters: stepping would
drift a rent due on the 31st down to the 28th permanently after one February,
whereas anchoring clamps only the short months and comes back to 31 after.
"""

from dateutil.relativedelta import relativedelta

from .models import RecurringTransaction

_STEP = {
    RecurringTransaction.Frequency.WEEKLY: lambda n: relativedelta(weeks=n),
    RecurringTransaction.Frequency.MONTHLY: lambda n: relativedelta(months=n),
    RecurringTransaction.Frequency.QUARTERLY: lambda n: relativedelta(months=3 * n),
    RecurringTransaction.Frequency.YEARLY: lambda n: relativedelta(years=n),
}

# Guards against an accidentally huge window (or interval=1 weekly over a
# decade) turning into an unbounded loop.
MAX_OCCURRENCES = 1000


def occurrences_between(recurrence, start, end):
    """Every due date of ``recurrence`` falling within [start, end] inclusive."""
    if start > end:
        return []

    step = _STEP[recurrence.frequency]
    interval = max(recurrence.interval, 1)
    last_allowed = min(end, recurrence.end_date) if recurrence.end_date else end

    dates = []
    n = 0
    while n < MAX_OCCURRENCES:
        occurrence = recurrence.start_date + step(n * interval)
        if occurrence > last_allowed:
            break
        if occurrence >= start:
            dates.append(occurrence)
        n += 1
    return dates


def expected_amount_between(recurrence, start, end):
    """Total amount this recurrence is expected to move over the window."""
    return recurrence.amount * len(occurrences_between(recurrence, start, end))


def upcoming_occurrences(household, start, end):
    """Flat, date-sorted list of every active recurrence due in the window."""
    recurrences = (
        RecurringTransaction.objects.for_household(household)
        .filter(is_active=True)
        .select_related("account", "account__owner", "category", "currency")
    )

    upcoming = []
    for recurrence in recurrences:
        for occurrence in occurrences_between(recurrence, start, end):
            upcoming.append({"date": occurrence, "recurrence": recurrence})
    return sorted(upcoming, key=lambda row: row["date"])
