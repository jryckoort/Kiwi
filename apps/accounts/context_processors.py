def household_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "active_household": getattr(request, "household", None),
        "user_households": user.households.all(),
    }
