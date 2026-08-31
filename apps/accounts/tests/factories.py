import factory

from apps.accounts.models import Household, HouseholdMembership, User
from apps.fx.models import Currency


class CurrencyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Currency
        django_get_or_create = ("code",)

    code = "EUR"
    name = "Euro"
    symbol = "€"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "testpass123")
        if create:
            self.save()


class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household

    name = factory.Sequence(lambda n: f"Foyer {n}")
    base_currency = "EUR"


class HouseholdMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HouseholdMembership

    user = factory.SubFactory(UserFactory)
    household = factory.SubFactory(HouseholdFactory)
    role = HouseholdMembership.Role.ADMIN
