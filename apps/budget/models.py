from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import HouseholdOwnedModel, PersonallyOwnedModel


class FinancialAccount(PersonallyOwnedModel):
    class Type(models.TextChoices):
        CHECKING = "checking", "Compte courant"
        SAVINGS = "savings", "Compte épargne"
        CREDIT_CARD = "credit_card", "Carte de crédit"
        CASH = "cash", "Espèces"
        INVESTMENT = "investment", "Compte-titres"
        OTHER = "other", "Autre"

    name = models.CharField("nom", max_length=100)
    type = models.CharField("type", max_length=20, choices=Type.choices, default=Type.CHECKING)
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    institution = models.CharField("banque / courtier", max_length=100, blank=True)
    is_archived = models.BooleanField("archivé", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "compte financier"
        verbose_name_plural = "comptes financiers"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_joint(self):
        return self.owner_id is None


class Category(HouseholdOwnedModel):
    class Kind(models.TextChoices):
        INCOME = "income", "Revenu"
        EXPENSE = "expense", "Dépense"

    name = models.CharField("nom", max_length=100)
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    color = models.CharField("couleur", max_length=7, default="#10b981")

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "name", "kind"], name="unique_category_per_household"
            )
        ]

    def __str__(self):
        return self.name


class Transaction(HouseholdOwnedModel):
    account = models.ForeignKey(
        FinancialAccount, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField("date")
    amount = models.DecimalField(
        "montant",
        max_digits=14,
        decimal_places=2,
        help_text="Positif pour une entrée d'argent, négatif pour une sortie.",
    )
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    description = models.CharField("description", max_length=255, blank=True)
    counterparty = models.CharField("tiers", max_length=150, blank=True)
    import_batch = models.ForeignKey(
        "imports_app.ImportBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "transaction"
        verbose_name_plural = "transactions"
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["household", "date"])]

    def __str__(self):
        return f"{self.date} · {self.description or self.counterparty} · {self.amount}"

    def clean(self):
        if self.account_id and self.household_id and self.account.household_id != self.household_id:
            raise ValidationError("Le compte doit appartenir au même foyer que la transaction.")

    def save(self, *args, **kwargs):
        if self.account_id and not self.household_id:
            self.household_id = self.account.household_id
        if not self.currency_id and self.account_id:
            self.currency_id = self.account.currency_id
        super().save(*args, **kwargs)
