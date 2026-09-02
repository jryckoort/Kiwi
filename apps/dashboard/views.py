import json
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from django.shortcuts import render

from apps.accounts.decorators import household_required
from apps.budget.models import Transaction
from apps.budget.projections import project_household
from apps.wealth.models import NetWorthSnapshot
from apps.wealth.services import compute_net_worth


def _next_occurrences(projection, limit):
    """Flatten the per-account occurrences into one date-sorted shortlist."""
    occurrences = [
        occurrence
        for account_projection in projection["projections"]
        for occurrence in account_projection.occurrences
    ]
    occurrences.sort(key=lambda row: row["date"])
    return occurrences[:limit]


@household_required
def home(request):
    household = request.household
    today = date.today()

    monthly_labels, monthly_income, monthly_expense = [], [], []
    for i in range(5, -1, -1):
        month_start = today.replace(day=1) - relativedelta(months=i)
        month_end = month_start + relativedelta(months=1)
        qs = Transaction.objects.for_household(household).filter(
            date__gte=month_start, date__lt=month_end
        )
        income = qs.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
        expense = qs.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal(0)
        monthly_labels.append(month_start.strftime("%b %Y"))
        monthly_income.append(float(income))
        monthly_expense.append(float(-expense))

    total_assets, total_liabilities, net_worth, breakdown = compute_net_worth(household)
    projection = project_household(household, as_of=today)

    history = list(
        NetWorthSnapshot.objects.for_household(household).order_by("date").values("date", "net_worth")
    )

    allocation_labels, allocation_values = [], []
    for section in ("accounts", "real_assets"):
        for name, value in breakdown.get(section, {}).items():
            if float(value) > 0:
                allocation_labels.append(name)
                allocation_values.append(float(value))

    recent_transactions = (
        Transaction.objects.for_household(household)
        .select_related("account", "category")
        .order_by("-date")[:8]
    )

    context = {
        "monthly_labels": json.dumps(monthly_labels),
        "monthly_income": json.dumps(monthly_income),
        "monthly_expense": json.dumps(monthly_expense),
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "net_worth_history_labels": json.dumps([str(row["date"]) for row in history]),
        "net_worth_history_values": json.dumps([float(row["net_worth"]) for row in history]),
        "allocation_labels": json.dumps(allocation_labels),
        "allocation_values": json.dumps(allocation_values),
        "recent_transactions": recent_transactions,
        "projection": projection,
        "upcoming_occurrences": _next_occurrences(projection, limit=5),
    }
    return render(request, "dashboard/home.html", context)
