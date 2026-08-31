from django.contrib import admin

from .models import (
    Liability,
    NetWorthSnapshot,
    PriceSnapshot,
    RealAsset,
    Security,
    SecurityTransaction,
)


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ("identifier", "name", "type", "currency")
    search_fields = ("identifier", "name")


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
