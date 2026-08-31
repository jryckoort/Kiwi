from django import forms

from .models import TOBRate

INPUT_CLASS = "form-input"


class PlusValueWhatIfForm(forms.Form):
    acquisition_value = forms.DecimalField(
        label="Valeur d'acquisition (ou valeur au 31/12/2025)",
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
    )
    sale_value = forms.DecimalField(
        label="Valeur de vente",
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
    )
    year = forms.IntegerField(
        label="Année d'imposition",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )


class TOBForm(forms.Form):
    instrument_type = forms.ChoiceField(
        label="Type d'instrument",
        choices=TOBRate.InstrumentType.choices,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    gross_amount = forms.DecimalField(
        label="Montant brut de l'ordre",
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
    )


class PrecompteMobilierForm(forms.Form):
    gross_income = forms.DecimalField(
        label="Montant brut (dividende / intérêts)",
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
    )
    is_regulated_savings = forms.BooleanField(
        label="Intérêts d'un compte d'épargne réglementé",
        required=False,
    )
    year = forms.IntegerField(
        label="Année",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )
