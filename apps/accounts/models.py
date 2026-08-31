import secrets

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class HouseholdScopedQuerySet(models.QuerySet):
    """Every tenant-scoped model uses this so callers are forced to name a household.

    There is deliberately no ``all()``-friendly default: code should always go
    through ``for_household()`` rather than an unscoped queryset, so one household
    can never see another's data by accident.
    """

    def for_household(self, household):
        return self.filter(household=household)


class HouseholdOwnedModel(models.Model):
    household = models.ForeignKey(
        "accounts.Household", on_delete=models.CASCADE, related_name="+"
    )

    objects = HouseholdScopedQuerySet.as_manager()

    class Meta:
        abstract = True


class PersonallyOwnedModel(HouseholdOwnedModel):
    """A household-scoped record that is either personal to one member or joint.

    ``owner=None`` means the account/asset/liability is joint (common to the
    household); otherwise it belongs to that one member.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Laisser vide pour un élément commun au foyer.",
    )

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superuser doit avoir is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superuser doit avoir is_superuser=True")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("adresse email", unique=True)
    first_name = models.CharField("prénom", max_length=150, blank=True)
    last_name = models.CharField("nom", max_length=150, blank=True)
    is_staff = models.BooleanField("accès admin", default=False)
    is_active = models.BooleanField("actif", default=True)
    date_joined = models.DateTimeField("date d'inscription", default=timezone.now)

    households = models.ManyToManyField(
        "accounts.Household", through="accounts.HouseholdMembership", related_name="members"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name or self.email


class Household(models.Model):
    name = models.CharField("nom du foyer", max_length=150)
    base_currency = models.CharField(
        "devise de référence", max_length=3, default=settings.DEFAULT_BASE_CURRENCY
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "foyer"
        verbose_name_plural = "foyers"

    def __str__(self):
        return self.name


class HouseholdMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        MEMBER = "member", "Membre"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "adhésion au foyer"
        verbose_name_plural = "adhésions au foyer"
        constraints = [
            models.UniqueConstraint(fields=["user", "household"], name="unique_membership")
        ]

    def __str__(self):
        return f"{self.user} @ {self.household} ({self.get_role_display()})"


def generate_invite_token():
    return secrets.token_urlsafe(32)


class HouseholdInvite(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="invites"
    )
    email = models.EmailField("email invité")
    invited_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_invites"
    )
    token = models.CharField(max_length=64, unique=True, default=generate_invite_token)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="accepted_invites"
    )

    class Meta:
        verbose_name = "invitation au foyer"
        verbose_name_plural = "invitations au foyer"

    def __str__(self):
        return f"Invitation {self.email} → {self.household}"

    @property
    def is_accepted(self):
        return self.accepted_at is not None
