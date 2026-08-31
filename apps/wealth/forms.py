from django import forms

from .models import Liability, RealAsset, SecurityTransaction

INPUT_CLASS = "form-input"


class RealAssetForm(forms.ModelForm):
    class Meta:
        model = RealAsset
        fields = [
            "type",
            "name",
            "owner",
            "acquisition_date",
            "acquisition_value",
            "current_value",
            "currency",
            "notes",
        ]
        widgets = {
            "type": forms.Select(attrs={"class": INPUT_CLASS}),
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "owner": forms.Select(attrs={"class": INPUT_CLASS}),
            "acquisition_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "acquisition_value": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "current_value": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "currency": forms.Select(attrs={"class": INPUT_CLASS}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["owner"].queryset = household.members.all()
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "Commun au foyer"


class LiabilityForm(forms.ModelForm):
    class Meta:
        model = Liability
        fields = [
            "type",
            "name",
            "owner",
            "principal",
            "remaining_balance",
            "interest_rate",
            "currency",
            "started_at",
            "notes",
        ]
        widgets = {
            "type": forms.Select(attrs={"class": INPUT_CLASS}),
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "owner": forms.Select(attrs={"class": INPUT_CLASS}),
            "principal": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "remaining_balance": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "interest_rate": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "currency": forms.Select(attrs={"class": INPUT_CLASS}),
            "started_at": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["owner"].queryset = household.members.all()
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "Commun au foyer"


class SecurityTransactionForm(forms.ModelForm):
    class Meta:
        model = SecurityTransaction
        fields = ["account", "security", "date", "type", "quantity", "price", "fees", "amount", "notes"]
        widgets = {
            "account": forms.Select(attrs={"class": INPUT_CLASS}),
            "security": forms.Select(attrs={"class": INPUT_CLASS}),
            "date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "type": forms.Select(attrs={"class": INPUT_CLASS}),
            "quantity": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.000001"}),
            "price": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.000001"}),
            "fees": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "amount": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "notes": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            from apps.budget.models import FinancialAccount

            self.fields["account"].queryset = FinancialAccount.objects.for_household(
                household
            ).filter(type=FinancialAccount.Type.INVESTMENT)
