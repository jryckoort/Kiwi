from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import HouseholdOwnedModel, PersonallyOwnedModel


class Security(models.Model):
    """Reference data shared across households — a stock/ETF/fund isn't owned
    by any one household, only the transactions and holdings referencing it are.
    """

    class Type(models.TextChoices):
        STOCK = "stock", "Action"
        ETF = "etf", "ETF"
        FUND = "fund", "Fonds"
        BOND = "bond", "Obligation"
        CRYPTO = "crypto", "Crypto-actif"

    identifier = models.CharField(
        "ISIN / ticker", max_length=20, unique=True, help_text="Ex: IE00B4L5Y983"
    )
    name = models.CharField("nom", max_length=150)
    type = models.CharField("type", max_length=10, choices=Type.choices, default=Type.ETF)
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    price_symbol = models.CharField(
        "symbole du fournisseur de cours",
        max_length=30,
        blank=True,
        help_text=(
            "Distinct de l'ISIN : les fournisseurs ne savent pas chercher par ISIN, et "
            "chacun a sa propre notation (IWDA.AS chez Yahoo, iwda.nl chez Stooq). "
            "Laissez vide pour saisir les cours à la main."
        ),
    )
    price_provider = models.CharField(
        "fournisseur de cours",
        max_length=20,
        blank=True,
        help_text="Laissez vide pour utiliser le fournisseur configuré dans SECURITY_PRICE_PROVIDER.",
    )
    last_synced_at = models.DateTimeField("dernière synchro", null=True, blank=True)
    last_sync_error = models.CharField("dernière erreur de synchro", max_length=255, blank=True)

    class Meta:
        verbose_name = "valeur mobilière"
        verbose_name_plural = "valeurs mobilières"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.identifier})"

    @property
    def is_auto_priced(self):
        return bool(self.price_symbol)


class PriceSnapshot(models.Model):
    security = models.ForeignKey(Security, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    price = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        verbose_name = "cours"
        verbose_name_plural = "cours"
        constraints = [
            models.UniqueConstraint(fields=["security", "date"], name="unique_price_per_day")
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.security} @ {self.date} = {self.price}"


class SecurityTransaction(HouseholdOwnedModel):
    class Type(models.TextChoices):
        BUY = "buy", "Achat"
        SELL = "sell", "Vente"
        DIVIDEND = "dividend", "Dividende"
        FEE = "fee", "Frais"

    account = models.ForeignKey(
        "budget.FinancialAccount", on_delete=models.CASCADE, related_name="security_transactions"
    )
    security = models.ForeignKey(
        Security, on_delete=models.PROTECT, related_name="transactions"
    )
    date = models.DateField("date")
    type = models.CharField("type", max_length=10, choices=Type.choices)
    quantity = models.DecimalField(
        "quantité", max_digits=18, decimal_places=6, null=True, blank=True
    )
    price = models.DecimalField(
        "prix unitaire", max_digits=18, decimal_places=6, null=True, blank=True
    )
    fees = models.DecimalField("frais", max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(
        "montant",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Montant brut pour un dividende ou des frais.",
    )
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "opération sur titres"
        verbose_name_plural = "opérations sur titres"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} {self.security} {self.date}"

    def clean(self):
        if self.type in (self.Type.BUY, self.Type.SELL):
            if self.quantity is None or self.price is None:
                raise ValidationError("Quantité et prix unitaire sont requis pour un achat/vente.")
        elif self.type in (self.Type.DIVIDEND, self.Type.FEE):
            if self.amount is None:
                raise ValidationError("Le montant est requis pour un dividende ou des frais.")
        if self.account_id and self.household_id and self.account.household_id != self.household_id:
            raise ValidationError("Le compte doit appartenir au même foyer que l'opération.")

    def save(self, *args, **kwargs):
        if self.account_id and not self.household_id:
            self.household_id = self.account.household_id
        if not self.currency_id and self.security_id:
            self.currency_id = self.security.currency_id
        super().save(*args, **kwargs)

    @property
    def gross_amount(self):
        if self.type in (self.Type.BUY, self.Type.SELL) and self.quantity and self.price:
            return self.quantity * self.price
        return self.amount or 0

    @property
    def cash_flow(self):
        """Signed cash impact: negative = money leaving the account."""
        if self.type == self.Type.BUY:
            return -(self.gross_amount + self.fees)
        if self.type == self.Type.SELL:
            return self.gross_amount - self.fees
        if self.type == self.Type.DIVIDEND:
            return self.amount or 0
        if self.type == self.Type.FEE:
            return -(self.amount or 0)
        return 0


class RealAsset(PersonallyOwnedModel):
    class Type(models.TextChoices):
        REAL_ESTATE = "real_estate", "Immobilier"
        VEHICLE = "vehicle", "Véhicule"
        OTHER = "other", "Autre"

    type = models.CharField("type", max_length=20, choices=Type.choices)
    name = models.CharField("nom", max_length=150)
    acquisition_date = models.DateField("date d'acquisition", null=True, blank=True)
    acquisition_value = models.DecimalField("valeur d'acquisition", max_digits=14, decimal_places=2)
    current_value = models.DecimalField(
        "valeur actuelle estimée", max_digits=14, decimal_places=2
    )
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    current_value_updated_at = models.DateField("valeur estimée au", null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "actif réel"
        verbose_name_plural = "actifs réels"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Liability(PersonallyOwnedModel):
    class Type(models.TextChoices):
        MORTGAGE = "mortgage", "Crédit hypothécaire"
        LOAN = "loan", "Prêt personnel"
        CREDIT = "credit", "Crédit renouvelable"

    type = models.CharField("type", max_length=20, choices=Type.choices)
    name = models.CharField("nom", max_length=150)
    principal = models.DecimalField("montant emprunté", max_digits=14, decimal_places=2)
    remaining_balance = models.DecimalField("solde restant dû", max_digits=14, decimal_places=2)
    interest_rate = models.DecimalField(
        "taux d'intérêt (%)", max_digits=5, decimal_places=2, null=True, blank=True
    )
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    started_at = models.DateField("date de départ", null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "dette"
        verbose_name_plural = "dettes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class NetWorthSnapshot(HouseholdOwnedModel):
    date = models.DateField()
    total_assets = models.DecimalField(max_digits=16, decimal_places=2)
    total_liabilities = models.DecimalField(max_digits=16, decimal_places=2)
    net_worth = models.DecimalField(max_digits=16, decimal_places=2)
    breakdown = models.JSONField(
        default=dict, blank=True, help_text="Détail par propriétaire / classe d'actif."
    )

    class Meta:
        verbose_name = "photo du patrimoine"
        verbose_name_plural = "photos du patrimoine"
        constraints = [
            models.UniqueConstraint(fields=["household", "date"], name="unique_snapshot_per_day")
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.household} @ {self.date} : {self.net_worth}"
