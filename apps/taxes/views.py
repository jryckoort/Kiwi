from datetime import date

from django.shortcuts import render

from apps.accounts.decorators import household_required

from .forms import PlusValueWhatIfForm, PrecompteMobilierForm, TOBForm
from .models import CapitalGainRecord
from .services import (
    compute_annual_plus_value_tax,
    compute_plus_value_whatif,
    compute_precompte_mobilier,
    compute_tob,
)


@household_required
def overview(request):
    current_year = date.today().year
    try:
        annual_summary = compute_annual_plus_value_tax(request.household, current_year)
    except ValueError:
        annual_summary = None

    recent_gains = (
        CapitalGainRecord.objects.for_household(request.household)
        .select_related("security_transaction__security")
        .order_by("-tax_year", "-computed_at")[:10]
    )
    return render(
        request,
        "taxes/overview.html",
        {"annual_summary": annual_summary, "recent_gains": recent_gains, "current_year": current_year},
    )


@household_required
def plus_value_calculator(request):
    result = None
    if request.method == "POST":
        form = PlusValueWhatIfForm(request.POST)
        if form.is_valid():
            result = compute_plus_value_whatif(
                form.cleaned_data["acquisition_value"],
                form.cleaned_data["sale_value"],
                form.cleaned_data["year"],
            )
    else:
        form = PlusValueWhatIfForm(initial={"year": date.today().year})
    return render(request, "taxes/plus_value_calculator.html", {"form": form, "result": result})


@household_required
def tob_calculator(request):
    result = None
    if request.method == "POST":
        form = TOBForm(request.POST)
        if form.is_valid():
            result = compute_tob(form.cleaned_data["instrument_type"], form.cleaned_data["gross_amount"])
    else:
        form = TOBForm()
    return render(request, "taxes/tob_calculator.html", {"form": form, "result": result})


@household_required
def precompte_calculator(request):
    result = None
    if request.method == "POST":
        form = PrecompteMobilierForm(request.POST)
        if form.is_valid():
            result = compute_precompte_mobilier(
                form.cleaned_data["gross_income"],
                form.cleaned_data["is_regulated_savings"],
                form.cleaned_data["year"],
            )
    else:
        form = PrecompteMobilierForm(initial={"year": date.today().year})
    return render(request, "taxes/precompte_calculator.html", {"form": form, "result": result})
