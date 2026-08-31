from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Household, HouseholdInvite, User


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")


class HouseholdCreateForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ("name", "base_currency")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex: Foyer Dupont"}),
            "base_currency": forms.TextInput(attrs={"class": "form-input", "maxlength": 3}),
        }


class HouseholdInviteForm(forms.ModelForm):
    class Meta:
        model = HouseholdInvite
        fields = ("email",)
        widgets = {
            "email": forms.EmailInput(
                attrs={"class": "form-input", "placeholder": "email@exemple.com"}
            ),
        }
