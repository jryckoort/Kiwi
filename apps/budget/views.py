from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import household_required

from .budgets import budget_vs_actuals, copy_budget_from_previous_month, current_month
from .forms import (
    BudgetLineForm,
    CategoryForm,
    FinancialAccountForm,
    RecurringTransactionForm,
    TransactionForm,
)
from .models import BudgetLine, Category, FinancialAccount, RecurringTransaction, Transaction
from .recurring import upcoming_occurrences


@household_required
def account_list(request):
    accounts = (
        FinancialAccount.objects.for_household(request.household)
        .filter(is_archived=False)
        .select_related("owner", "currency")
        .annotate(balance=Sum("transactions__amount"))
    )
    return render(request, "budget/account_list.html", {"accounts": accounts})


@household_required
def account_create(request):
    if request.method == "POST":
        form = FinancialAccountForm(request.POST, household=request.household)
        if form.is_valid():
            account = form.save(commit=False)
            account.household = request.household
            account.save()
            messages.success(request, f"Compte « {account.name} » créé.")
            return redirect("budget:account_list")
    else:
        form = FinancialAccountForm(household=request.household)
    return render(request, "budget/account_form.html", {"form": form})


@household_required
def account_detail(request, pk):
    account = get_object_or_404(
        FinancialAccount.objects.for_household(request.household), pk=pk
    )
    transactions = account.transactions.select_related("category").order_by("-date")
    balance = transactions.aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "budget/account_detail.html",
        {"account": account, "transactions": transactions, "balance": balance},
    )


@household_required
def transaction_create(request):
    if request.method == "POST":
        form = TransactionForm(request.POST, household=request.household)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.household = request.household
            transaction.save()
            messages.success(request, "Transaction ajoutée.")
            return redirect("budget:account_detail", pk=transaction.account_id)
    else:
        initial = {}
        account_id = request.GET.get("account")
        if account_id:
            initial["account"] = account_id
        form = TransactionForm(household=request.household, initial=initial)
    return render(request, "budget/transaction_form.html", {"form": form})


@household_required
def transaction_edit(request, pk):
    transaction = get_object_or_404(Transaction.objects.for_household(request.household), pk=pk)
    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction, household=request.household)
        if form.is_valid():
            form.save()
            messages.success(request, "Transaction mise à jour.")
            return redirect("budget:account_detail", pk=transaction.account_id)
    else:
        form = TransactionForm(instance=transaction, household=request.household)
    return render(request, "budget/transaction_form.html", {"form": form, "transaction": transaction})


@household_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction.objects.for_household(request.household), pk=pk)
    account_id = transaction.account_id
    if request.method == "POST":
        transaction.delete()
        messages.success(request, "Transaction supprimée.")
        return redirect("budget:account_detail", pk=account_id)
    return render(request, "budget/transaction_confirm_delete.html", {"transaction": transaction})


@household_required
def category_list(request):
    categories = Category.objects.for_household(request.household).select_related("parent")
    if request.method == "POST":
        form = CategoryForm(request.POST, household=request.household)
        if form.is_valid():
            category = form.save(commit=False)
            category.household = request.household
            category.save()
            messages.success(request, f"Catégorie « {category.name} » créée.")
            return redirect("budget:category_list")
    else:
        form = CategoryForm(household=request.household)
    return render(request, "budget/category_list.html", {"categories": categories, "form": form})


@household_required
def recurring_list(request):
    recurrences = (
        RecurringTransaction.objects.for_household(request.household)
        .select_related("account", "account__owner", "category", "currency")
    )
    today = date.today()
    horizon_start, horizon_end = today, today + relativedelta(months=3)
    return render(
        request,
        "budget/recurring_list.html",
        {
            "recurrences": recurrences,
            "upcoming": upcoming_occurrences(request.household, horizon_start, horizon_end),
            "horizon_end": horizon_end,
        },
    )


@household_required
def recurring_create(request):
    if request.method == "POST":
        form = RecurringTransactionForm(request.POST, household=request.household)
        if form.is_valid():
            recurrence = form.save(commit=False)
            recurrence.household = request.household
            recurrence.save()
            messages.success(request, f"Récurrence « {recurrence.description} » créée.")
            return redirect("budget:recurring_list")
    else:
        form = RecurringTransactionForm(household=request.household)
    return render(request, "budget/recurring_form.html", {"form": form})


@household_required
def recurring_edit(request, pk):
    recurrence = get_object_or_404(
        RecurringTransaction.objects.for_household(request.household), pk=pk
    )
    if request.method == "POST":
        form = RecurringTransactionForm(
            request.POST, instance=recurrence, household=request.household
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Récurrence mise à jour.")
            return redirect("budget:recurring_list")
    else:
        form = RecurringTransactionForm(instance=recurrence, household=request.household)
    return render(
        request, "budget/recurring_form.html", {"form": form, "recurrence": recurrence}
    )


@household_required
def recurring_delete(request, pk):
    recurrence = get_object_or_404(
        RecurringTransaction.objects.for_household(request.household), pk=pk
    )
    if request.method == "POST":
        recurrence.delete()
        messages.success(request, "Récurrence supprimée.")
        return redirect("budget:recurring_list")
    return render(request, "budget/recurring_confirm_delete.html", {"recurrence": recurrence})


def _parse_month(raw):
    """Accept ?mois=YYYY-MM, falling back to the current month."""
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m").date().replace(day=1)
        except ValueError:
            pass
    return current_month()


@household_required
def budget_overview(request):
    month = _parse_month(request.GET.get("mois"))

    if request.method == "POST":
        form = BudgetLineForm(request.POST, household=request.household)
        if form.is_valid():
            line = form.save(commit=False)
            line.household = request.household
            line.month = month
            # Editing an existing line rather than failing on the unique
            # constraint is what a user expects when re-entering an amount.
            existing = BudgetLine.objects.for_household(request.household).filter(
                category=line.category, owner=line.owner, month=month
            ).first()
            if existing:
                existing.planned_amount = line.planned_amount
                existing.save(update_fields=["planned_amount"])
                messages.success(request, "Budget mis à jour.")
            else:
                line.save()
                messages.success(request, "Ligne de budget ajoutée.")
            return redirect(f"{reverse('budget:budget_overview')}?mois={month:%Y-%m}")
    else:
        form = BudgetLineForm(household=request.household)

    groups, warnings = budget_vs_actuals(request.household, month)
    return render(
        request,
        "budget/budget_overview.html",
        {
            "month": month,
            "previous_month": month - relativedelta(months=1),
            "next_month": month + relativedelta(months=1),
            "groups": groups,
            "warnings": warnings,
            "form": form,
            "base_currency": request.household.base_currency,
        },
    )


@household_required
@require_POST
def budget_copy_previous(request):
    month = _parse_month(request.POST.get("mois"))
    created = copy_budget_from_previous_month(request.household, month)
    if created:
        messages.success(request, f"{created} ligne(s) reprises du mois précédent.")
    else:
        messages.info(request, "Rien à reprendre : le mois précédent n'a pas de budget.")
    return redirect(f"{reverse('budget:budget_overview')}?mois={month:%Y-%m}")


@household_required
def budget_line_delete(request, pk):
    line = get_object_or_404(BudgetLine.objects.for_household(request.household), pk=pk)
    month = line.month
    if request.method == "POST":
        line.delete()
        messages.success(request, "Ligne de budget supprimée.")
        return redirect(f"{reverse('budget:budget_overview')}?mois={month:%Y-%m}")
    return render(request, "budget/budget_line_confirm_delete.html", {"line": line})
