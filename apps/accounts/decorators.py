from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def household_required(view_func):
    """Redirects to household creation when the user has no active household.

    Use on every household-scoped view alongside ``login_required`` so
    ``request.household`` is always a real Household by the time the view body
    runs.
    """

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.household is None:
            return redirect("accounts:household_create")
        return view_func(request, *args, **kwargs)

    return wrapper
