from django.contrib import messages
from django.shortcuts import redirect, render

from apps.accounts.decorators import household_required
from apps.budget.models import FinancialAccount

from .forms import LiabilityForm, RealAssetForm, SecurityTransactionForm
from .models import Liability, RealAsset, Security
from .services import compute_holdings, compute_net_worth, latest_price


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
            price = latest_price(security)
            market_value = price * holding.quantity if price is not None else None
            rows.append(
                {
                    "security": security,
                    "quantity": holding.quantity,
                    "average_cost": holding.average_cost,
                    "cost_basis": holding.cost_basis,
                    "price": price,
                    "market_value": market_value,
                    "unrealized_gain": (market_value - holding.cost_basis)
                    if market_value is not None
                    else None,
                }
            )
        if rows:
            holdings_by_account.append({"account": account, "rows": rows})

    real_assets = RealAsset.objects.for_household(request.household).select_related("owner")
    liabilities = Liability.objects.for_household(request.household).select_related("owner")
    total_assets, total_liabilities, net_worth, breakdown = compute_net_worth(request.household)

    context = {
        "holdings_by_account": holdings_by_account,
        "real_assets": real_assets,
        "liabilities": liabilities,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "base_currency": request.household.base_currency,
        "valuation_warnings": breakdown.get("warnings", []),
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
