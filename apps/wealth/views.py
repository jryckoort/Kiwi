from django.contrib import messages
from django.shortcuts import redirect, render

from apps.accounts.decorators import household_required
from apps.budget.models import FinancialAccount

from .forms import LiabilityForm, RealAssetForm, SecurityTransactionForm
from .models import Security
from .services import (
    compute_holdings,
    compute_net_worth_by_owner,
    is_stale,
    latest_quote,
)


@household_required
def overview(request):
    accounts = FinancialAccount.objects.for_household(request.household).filter(
        type=FinancialAccount.Type.INVESTMENT
    )
    holdings_by_account = []
    for account in accounts:
        rows = []
        for holding in compute_holdings(account):
            security = Security.objects.get(pk=holding.security_id)
            price, quote_date = latest_quote(security)
            market_value = price * holding.quantity if price is not None else None
            rows.append(
                {
                    "security": security,
                    "quantity": holding.quantity,
                    "average_cost": holding.average_cost,
                    "cost_basis": holding.cost_basis,
                    "price": price,
                    "quote_date": quote_date,
                    "is_stale": is_stale(quote_date) if price is not None else False,
                    "market_value": market_value,
                    "unrealized_gain": (market_value - holding.cost_basis)
                    if market_value is not None
                    else None,
                }
            )
        if rows:
            holdings_by_account.append({"account": account, "rows": rows})

    # Same items as the family total, sliced per member — the consolidated
    # figure and the per-person ones can never disagree.
    by_owner = compute_net_worth_by_owner(request.household, viewer=request.user)

    # Nobody self-hosting reads Celery logs, so a broken price feed has to be
    # visible on the page that depends on it.
    held_security_ids = {
        row["security"].pk for group in holdings_by_account for row in group["rows"]
    }
    price_feed_errors = Security.objects.filter(
        pk__in=held_security_ids
    ).exclude(last_sync_error="")

    context = {
        "holdings_by_account": holdings_by_account,
        "groups": by_owner["groups"],
        "total_assets": by_owner["total_assets"],
        "total_liabilities": by_owner["total_liabilities"],
        "net_worth": by_owner["net_worth"],
        "base_currency": by_owner["base_currency"],
        "valuation_warnings": by_owner["warnings"],
        "price_feed_errors": price_feed_errors,
    }
    return render(request, "wealth/overview.html", context)


@household_required
def real_asset_create(request):
    if request.method == "POST":
        form = RealAssetForm(request.POST, household=request.household)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.household = request.household
            asset.save()
            messages.success(request, f"Actif « {asset.name} » ajouté.")
            return redirect("wealth:overview")
    else:
        form = RealAssetForm(household=request.household)
    return render(request, "wealth/real_asset_form.html", {"form": form})


@household_required
def liability_create(request):
    if request.method == "POST":
        form = LiabilityForm(request.POST, household=request.household)
        if form.is_valid():
            liability = form.save(commit=False)
            liability.household = request.household
            liability.save()
            messages.success(request, f"Dette « {liability.name} » ajoutée.")
            return redirect("wealth:overview")
    else:
        form = LiabilityForm(household=request.household)
    return render(request, "wealth/liability_form.html", {"form": form})


@household_required
def security_transaction_create(request):
    if request.method == "POST":
        form = SecurityTransactionForm(request.POST, household=request.household)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.household = request.household
            transaction.save()
            messages.success(request, "Opération enregistrée.")
            return redirect("wealth:overview")
    else:
        form = SecurityTransactionForm(household=request.household)
    return render(request, "wealth/security_transaction_form.html", {"form": form})
