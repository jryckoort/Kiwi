from django.contrib import admin

from .models import BudgetLine, Category, FinancialAccount, RecurringTransaction, Transaction


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "household", "owner", "type", "currency", "is_archived")
    list_filter = ("household", "type", "is_archived")
    search_fields = ("name", "institution")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "household", "kind", "parent")
    list_filter = ("household", "kind")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "account", "amount", "category", "description")
    list_filter = ("household", "account", "category")
    date_hierarchy = "date"
    search_fields = ("description", "counterparty")


@admin.register(RecurringTransaction)
class RecurringTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "description", "household", "account", "amount", "frequency", "start_date", "is_active"
    )
    list_filter = ("household", "frequency", "is_active")
    search_fields = ("description",)


@admin.register(BudgetLine)
class BudgetLineAdmin(admin.ModelAdmin):
    list_display = ("category", "month", "owner", "planned_amount", "household")
    list_filter = ("household", "month", "owner")
