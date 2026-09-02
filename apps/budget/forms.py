from django import forms

from .models import BudgetLine, Category, FinancialAccount, RecurringTransaction, Transaction

INPUT_CLASS = "form-input"


class FinancialAccountForm(forms.ModelForm):
    class Meta:
        model = FinancialAccount
        fields = ["name", "type", "currency", "institution", "owner"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "type": forms.Select(attrs={"class": INPUT_CLASS}),
            "currency": forms.Select(attrs={"class": INPUT_CLASS}),
            "institution": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "owner": forms.Select(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["owner"].queryset = household.members.all()
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "Commun au foyer"


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "parent", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "kind": forms.Select(attrs={"class": INPUT_CLASS}),
            "parent": forms.Select(attrs={"class": INPUT_CLASS}),
            "color": forms.TextInput(attrs={"class": INPUT_CLASS, "type": "color"}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["parent"].queryset = Category.objects.for_household(household)
        self.fields["parent"].required = False


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["account", "date", "amount", "category", "description", "counterparty"]
        widgets = {
            "account": forms.Select(attrs={"class": INPUT_CLASS}),
            "date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "description": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "counterparty": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["account"].queryset = FinancialAccount.objects.for_household(household)
            self.fields["category"].queryset = Category.objects.for_household(household)
        self.fields["category"].required = False


class RecurringTransactionForm(forms.ModelForm):
    class Meta:
        model = RecurringTransaction
        fields = [
            "description",
            "account",
            "category",
            "amount",
            "frequency",
            "interval",
            "start_date",
            "end_date",
            "is_active",
        ]
        widgets = {
            "description": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "account": forms.Select(attrs={"class": INPUT_CLASS}),
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "amount": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
            "frequency": forms.Select(attrs={"class": INPUT_CLASS}),
            "interval": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "start_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["account"].queryset = FinancialAccount.objects.for_household(
                household
            ).filter(is_archived=False)
            self.fields["category"].queryset = Category.objects.for_household(household)
        self.fields["category"].required = False
        self.fields["end_date"].required = False
        self.fields["account"].help_text = (
            "Le compte détermine à qui la récurrence est rattachée : un compte "
            "perso alimente le budget de cette personne, un compte commun le budget commun."
        )


class BudgetLineForm(forms.ModelForm):
    class Meta:
        model = BudgetLine
        fields = ["category", "owner", "planned_amount"]
        widgets = {
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "owner": forms.Select(attrs={"class": INPUT_CLASS}),
            "planned_amount": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["category"].queryset = Category.objects.for_household(household)
            self.fields["owner"].queryset = household.members.all()
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "Commun au foyer"
