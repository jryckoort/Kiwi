from datetime import date

from django.db import models

from apps.accounts.models import HouseholdOwnedModel


class TOBRate(models.Model):
    """Taxe sur les opérations de bourse — rate + cap per instrument type.

    Caps are indexed periodically by royal decree; verify against the current
    SPF Finances schedule before relying on this for a real declaration.
    """

    class InstrumentType(models.TextChoices):
        BONDS = "bonds", "Obligations"
        SHARES = "shares", "Actions / parts de distribution"
        CAPITALIZATION = "capitalization", "Fonds de capitalisation"

    instrument_type = models.CharField(max_length=20, choices=InstrumentType.choices, unique=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=3)
    cap_amount = models.DecimalField(max_digits=8, decimal_places=2)
    effective_from = models.DateField()

    class Meta:
        verbose_name = "taux TOB"
        verbose_name_plural = "taux TOB"

    def __str__(self):
        return f"{self.get_instrument_type_display()} — {self.rate_percent}% (max {self.cap_amount}€)"


class PrecompteMobilierRule(models.Model):
    """Withholding tax on dividends/interest. The regulated-savings-account
    exemption threshold is indexed yearly — verify the current amount.
    """

    year = models.PositiveIntegerField(unique=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    savings_account_exempt_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Première tranche d'intérêts de compte d'épargne réglementé exonérée de précompte.",
    )

    class Meta:
        verbose_name = "règle précompte mobilier"
        verbose_name_plural = "règles précompte mobilier"
        ordering = ["-year"]

    def __str__(self):
        return f"Précompte mobilier {self.year} — {self.rate_percent}%"


class PlusValueTaxRule(models.Model):
    """The new tax on capital gains realized on financial instruments,
    effective from 2026. Pre-existing holdings are grandfathered: the cost
    basis used for tax purposes is the higher of the actual acquisition cost
    or the market value on ``reference_date``.
    """

    year = models.PositiveIntegerField(unique=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    annual_exemption = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=10000,
        help_text="Exonération annuelle par contribuable (indexée chaque année).",
    )
    reference_date = models.DateField(
        default=date(2025, 12, 31),
        help_text="Date de référence pour la valeur de grandfathering des positions existantes.",
    )

    class Meta:
        verbose_name = "règle taxe plus-value"
        verbose_name_plural = "règles taxe plus-value"
        ordering = ["-year"]

    def __str__(self):
        return f"Taxe plus-value {self.year} — {self.rate_percent}%"


class CapitalGainRecord(HouseholdOwnedModel):
    security_transaction = models.OneToOneField(
        "wealth.SecurityTransaction", on_delete=models.CASCADE, related_name="capital_gain"
    )
    cost_basis = models.DecimalField(max_digits=14, decimal_places=2)
    proceeds = models.DecimalField(max_digits=14, decimal_places=2)
    realized_gain = models.DecimalField(max_digits=14, decimal_places=2)
    tax_year = models.PositiveIntegerField()
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "plus-value réalisée"
        verbose_name_plural = "plus-values réalisées"
        ordering = ["-tax_year"]

    def __str__(self):
        return f"{self.security_transaction} → {self.realized_gain}"
