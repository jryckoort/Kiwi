from django.conf import settings
from django.db import models

from apps.accounts.models import HouseholdOwnedModel


def import_upload_path(instance, filename):
    return f"imports/household_{instance.household_id}/{filename}"


class ImportMappingTemplate(HouseholdOwnedModel):
    name = models.CharField("nom", max_length=100)
    column_mapping = models.JSONField(
        help_text="Association champ Kiwi -> nom de colonne du CSV.",
    )
    date_format = models.CharField(max_length=20, default="%d/%m/%Y")
    delimiter = models.CharField(max_length=1, default=",")

    class Meta:
        verbose_name = "modèle de mapping d'import"
        verbose_name_plural = "modèles de mapping d'import"
        constraints = [
            models.UniqueConstraint(fields=["household", "name"], name="unique_template_per_household")
        ]

    def __str__(self):
        return self.name


class ImportBatch(HouseholdOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente de mapping"
        MAPPED = "mapped", "Mappé, en attente de confirmation"
        CONFIRMED = "confirmed", "Importé"
        FAILED = "failed", "Échec"

    account = models.ForeignKey(
        "budget.FinancialAccount", on_delete=models.CASCADE, related_name="import_batches"
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to=import_upload_path)
    column_mapping = models.JSONField(default=dict, blank=True)
    date_format = models.CharField(max_length=20, default="%d/%m/%Y")
    delimiter = models.CharField(max_length=1, default=",")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    imported_count = models.PositiveIntegerField(default=0)
    skipped_duplicate_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "import CSV"
        verbose_name_plural = "imports CSV"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.account} du {self.created_at:%Y-%m-%d}"
