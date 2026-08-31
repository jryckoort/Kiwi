from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import HouseholdCreateForm, HouseholdInviteForm, SignupForm
from .middleware import ActiveHouseholdMiddleware
from .models import HouseholdInvite, HouseholdMembership


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    next_url = request.POST.get("next") or request.GET.get("next")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if next_url:
                return redirect(next_url)
            if not user.memberships.exists():
                return redirect("accounts:household_create")
            return redirect("dashboard:home")
    else:
        form = SignupForm()

    return render(request, "accounts/signup.html", {"form": form, "next": next_url})


@login_required
def household_create(request):
    if request.method == "POST":
        form = HouseholdCreateForm(request.POST)
        if form.is_valid():
            household = form.save()
            HouseholdMembership.objects.create(
                user=request.user, household=household, role=HouseholdMembership.Role.ADMIN
            )
            request.session[ActiveHouseholdMiddleware.SESSION_KEY] = household.id
            messages.success(request, f"Foyer « {household.name} » créé.")
            return redirect("dashboard:home")
    else:
        form = HouseholdCreateForm()

    return render(request, "accounts/household_create.html", {"form": form})


@login_required
def household_settings(request):
    household = request.household
    if household is None:
        return redirect("accounts:household_create")

    membership = get_object_or_404(HouseholdMembership, user=request.user, household=household)
    is_admin = membership.role == HouseholdMembership.Role.ADMIN

    invite_form = HouseholdInviteForm()
    if request.method == "POST" and is_admin:
        invite_form = HouseholdInviteForm(request.POST)
        if invite_form.is_valid():
            invite = invite_form.save(commit=False)
            invite.household = household
            invite.invited_by = request.user
            invite.save()
            messages.success(
                request,
                f"Invitation créée pour {invite.email}. Partagez-lui ce lien : "
                f"{request.build_absolute_uri(f'/accounts/invites/{invite.token}/')}",
            )
            return redirect("accounts:household_settings")

    context = {
        "household": household,
        "is_admin": is_admin,
        "memberships": household.memberships.select_related("user"),
        "pending_invites": household.invites.filter(accepted_at__isnull=True),
        "invite_form": invite_form,
    }
    return render(request, "accounts/household_settings.html", context)


@login_required
@require_POST
def household_switch(request, household_id):
    membership = get_object_or_404(
        HouseholdMembership, user=request.user, household_id=household_id
    )
    request.session[ActiveHouseholdMiddleware.SESSION_KEY] = membership.household_id
    messages.info(request, f"Foyer actif : {membership.household.name}")
    return redirect(request.META.get("HTTP_REFERER", "dashboard:home"))


@login_required
def invite_accept(request, token):
    invite = get_object_or_404(HouseholdInvite, token=token)

    if invite.is_accepted:
        messages.warning(request, "Cette invitation a déjà été utilisée.")
        return redirect("dashboard:home")

    if request.user.email.lower() != invite.email.lower():
        messages.error(
            request,
            f"Cette invitation a été envoyée à {invite.email}, connectez-vous avec cette adresse.",
        )
        return redirect("dashboard:home")

    HouseholdMembership.objects.get_or_create(
        user=request.user,
        household=invite.household,
        defaults={"role": HouseholdMembership.Role.MEMBER},
    )
    invite.accepted_at = timezone.now()
    invite.accepted_by = request.user
    invite.save(update_fields=["accepted_at", "accepted_by"])

    request.session[ActiveHouseholdMiddleware.SESSION_KEY] = invite.household_id
    messages.success(request, f"Vous avez rejoint le foyer « {invite.household.name} ».")
    return redirect("dashboard:home")
