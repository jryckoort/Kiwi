from django import forms
from django.conf import settings

from apps.budget.models import FinancialAccount

from .models import ImportMappingTemplate

INPUT_CLASS = "form-input"


class UploadForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(),
        label="Compte à alimenter",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    file = forms.FileField(label="Fichier CSV", widget=forms.ClearableFileInput(attrs={"class": INPUT_CLASS}))
    template = forms.ModelChoiceField(
        queryset=ImportMappingTemplate.objects.none(),
        required=False,
        label="Modèle de mapping (optionnel)",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["account"].queryset = FinancialAccount.objects.for_household(household)
            self.fields["template"].queryset = ImportMappingTemplate.objects.for_household(household)

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(".csv"):
            raise forms.ValidationError("Le fichier doit être au format CSV.")
        # DATA_UPLOAD_MAX_MEMORY_SIZE explicitly excludes file uploads, so the
        # size cap has to be enforced here.
        max_size = settings.MAX_IMPORT_FILE_SIZE_BYTES
        if file.size > max_size:
            raise forms.ValidationError(
                f"Fichier trop volumineux ({file.size // 1024} Ko). "
                f"Maximum autorisé : {max_size // 1024 // 1024} Mo."
            )
        return file


class MappingForm(forms.Form):
    date_column = forms.ChoiceField(label="Colonne date")
    amount_column = forms.ChoiceField(label="Colonne montant")
    description_column = forms.ChoiceField(label="Colonne description", required=False)
    counterparty_column = forms.ChoiceField(label="Colonne tiers", required=False)
    date_format = forms.CharField(
        label="Format de date",
        initial="%d/%m/%Y",
        help_text="Ex: %d/%m/%Y pour 31/01/2026",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    save_as_template = forms.BooleanField(label="Enregistrer ce mapping comme modèle", required=False)
    template_name = forms.CharField(
        label="Nom du modèle", required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS})
    )

    def __init__(self, *args, headers=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(h, h) for h in (headers or [])]
        optional_choices = [("", "—")] + choices
        for field_name in ("date_column", "amount_column"):
            self.fields[field_name].choices = choices
            self.fields[field_name].widget.attrs["class"] = INPUT_CLASS
        for field_name in ("description_column", "counterparty_column"):
            self.fields[field_name].choices = optional_choices
            self.fields[field_name].widget.attrs["class"] = INPUT_CLASS

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("save_as_template") and not cleaned.get("template_name"):
            self.add_error("template_name", "Nom requis pour enregistrer un modèle.")
        return cleaned
