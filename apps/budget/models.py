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


class RecurringTransaction(HouseholdOwnedModel):
    """A repeating income or expense used for forecasting only.

    Deliberately never creates Transaction rows: the real movements come from
    the bank CSV import or manual entry, so materializing these too would
    double-count every rent and salary. What it feeds instead is the expected
    side of the budget and the list of upcoming due dates.
    """

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Hebdomadaire"
        MONTHLY = "monthly", "Mensuelle"
        QUARTERLY = "quarterly", "Trimestrielle"
        YEARLY = "yearly", "Annuelle"

    account = models.ForeignKey(
        FinancialAccount,
        verbose_name="compte",
        on_delete=models.CASCADE,
        related_name="recurring_transactions",
    )
    category = models.ForeignKey(
        Category,
        verbose_name="catégorie",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurring_transactions",
    )
    description = models.CharField("description", max_length=255)
    amount = models.DecimalField(
        "montant",
        max_digits=14,
        decimal_places=2,
        help_text="Positif pour une entrée d'argent, négatif pour une sortie.",
    )
    currency = models.ForeignKey("fx.Currency", on_delete=models.PROTECT, related_name="+")
    frequency = models.CharField("fréquence", max_length=10, choices=Frequency.choices)
    interval = models.PositiveSmallIntegerField(
        "intervalle", default=1, help_text="Toutes les N périodes (1 = chaque période)."
    )
    start_date = models.DateField("première échéance")
    end_date = models.DateField("dernière échéance", null=True, blank=True)
    is_active = models.BooleanField("active", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "transaction récurrente"
        verbose_name_plural = "transactions récurrentes"
        ordering = ["description"]

    def __str__(self):
        return f"{self.description} ({self.get_frequency_display()})"

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("La dernière échéance ne peut pas précéder la première.")
        if self.interval < 1:
            raise ValidationError("L'intervalle doit valoir au moins 1.")
        if self.account_id and self.household_id and self.account.household_id != self.household_id:
            raise ValidationError("Le compte doit appartenir au même foyer que la récurrence.")

    def save(self, *args, **kwargs):
        if self.account_id and not self.household_id:
            self.household_id = self.account.household_id
        if not self.currency_id and self.account_id:
            self.currency_id = self.account.currency_id
        super().save(*args, **kwargs)

    @property
    def owner(self):
        """Who this recurrence belongs to — None means the household's joint budget."""
        return self.account.owner


class BudgetLine(PersonallyOwnedModel):
    """A planned amount for one category, one month, and one member.

    ``owner=None`` means the joint (commun) budget, matching how accounts and
    assets already express personal-vs-joint ownership.
    """

    category = models.ForeignKey(
        Category, verbose_name="catégorie", on_delete=models.CASCADE, related_name="budget_lines"
    )
    month = models.DateField("mois", help_text="Premier jour du mois budgété.")
    planned_amount = models.DecimalField(
        "montant prévu",
        max_digits=14,
        decimal_places=2,
        help_text="Montant attendu, en valeur absolue (600 pour 600 € de courses).",
    )

    class Meta:
        verbose_name = "ligne de budget"
        verbose_name_plural = "lignes de budget"
        ordering = ["month", "category__name"]
        constraints = [
            # Split in two because SQL treats NULLs as distinct, which would
            # otherwise let the joint (owner=NULL) line be created twice.
            models.UniqueConstraint(
                fields=["household", "category", "month", "owner"],
                condition=models.Q(owner__isnull=False),
                name="unique_personal_budget_line",
            ),
            models.UniqueConstraint(
                fields=["household", "category", "month"],
                condition=models.Q(owner__isnull=True),
                name="unique_joint_budget_line",
            ),
        ]

    def __str__(self):
        who = self.owner.get_short_name() if self.owner else "Commun"
        return f"{self.category} · {self.month:%Y-%m} · {who} : {self.planned_amount}"

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError("Le mois budgété doit pointer sur le premier jour du mois.")
        if self.planned_amount is not None and self.planned_amount < 0:
            raise ValidationError("Le montant prévu s'exprime en valeur absolue (positif).")
