class ActiveHouseholdMiddleware:
    """Resolves ``request.household`` for the logged-in user on every request.

    Views must filter household-scoped querysets through
    ``Model.objects.for_household(request.household)`` — never an unscoped
    queryset — so one household's data can never leak into another's view.
    """

    SESSION_KEY = "active_household_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.household = None
        if request.user.is_authenticated:
            request.household = self._resolve_household(request)
        return self.get_response(request)

    def _resolve_household(self, request):
        memberships = list(request.user.memberships.select_related("household"))
        if not memberships:
            return None

        wanted_id = request.session.get(self.SESSION_KEY)
        for membership in memberships:
            if membership.household_id == wanted_id:
                return membership.household

        household = memberships[0].household
        request.session[self.SESSION_KEY] = household.id
        return household
