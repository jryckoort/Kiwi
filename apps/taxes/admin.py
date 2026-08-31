from django.contrib import admin

from .models import CapitalGainRecord, PlusValueTaxRule, PrecompteMobilierRule, TOBRate


@admin.register(TOBRate)
class TOBRateAdmin(admin.ModelAdmin):
    list_display = ("instrument_type", "rate_percent", "cap_amount", "effective_from")


@admin.register(PrecompteMobilierRule)
class PrecompteMobilierRuleAdmin(admin.ModelAdmin):
    list_display = ("year", "rate_percent", "savings_account_exempt_threshold")


@admin.register(PlusValueTaxRule)
class PlusValueTaxRuleAdmin(admin.ModelAdmin):
    list_display = ("year", "rate_percent", "annual_exemption", "reference_date")


@admin.register(CapitalGainRecord)
class CapitalGainRecordAdmin(admin.ModelAdmin):
    list_display = ("household", "security_transaction", "tax_year", "realized_gain")
    list_filter = ("household", "tax_year")
