from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import household_required

from .forms import CategoryForm, FinancialAccountForm, TransactionForm
from .models import Category, FinancialAccount, Transaction


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
