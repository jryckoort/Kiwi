from django import forms
from django.contrib import admin

from .models import (
    Liability,
    NetWorthSnapshot,
    PriceSnapshot,
    RealAsset,
    Security,
    SecurityTransaction,
)
from .providers import PROVIDER_CHOICES


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = (
        "identifier", "name", "type", "currency", "price_symbol", "price_provider",
        "last_synced_at", "last_sync_error",
    )
    list_filter = ("type", "price_provider")
    search_fields = ("identifier", "name", "price_symbol")
    readonly_fields = ("last_synced_at", "last_sync_error")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Offer the configured providers as a dropdown rather than free text,
        # with an example symbol for each since notations differ.
        if db_field.name == "price_provider":
            kwargs["widget"] = forms.Select(
                choices=[("", "Par défaut (SECURITY_PRICE_PROVIDER)"), *PROVIDER_CHOICES]
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("security", "date", "price")
    list_filter = ("security",)
    date_hierarchy = "date"


@admin.register(SecurityTransaction)
class SecurityTransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "household", "account", "security", "type", "quantity", "price", "amount")
    list_filter = ("household", "type")
    date_hierarchy = "date"


@admin.register(RealAsset)
class RealAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "household", "owner", "type", "current_value")
    list_filter = ("household", "type")


@admin.register(Liability)
class LiabilityAdmin(admin.ModelAdmin):
    list_display = ("name", "household", "owner", "type", "remaining_balance")
    list_filter = ("household", "type")


@admin.register(NetWorthSnapshot)
class NetWorthSnapshotAdmin(admin.ModelAdmin):
    list_display = ("household", "date", "total_assets", "total_liabilities", "net_worth")
    list_filter = ("household",)
    date_hierarchy = "date"
