# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Kiwi is a self-hosted household budget and wealth-management app for a Belgian
household: personal and joint accounts, investments, and Belgian tax
calculators. UI strings and model labels are in **French**; code, comments and
commit messages are in English.

## Commands

```bash
# setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate

# run
python manage.py runserver

# tests
pytest                                          # whole suite
pytest apps/budget                              # one app
pytest apps/budget/tests/test_budgets.py        # one file
pytest -k test_month_end_start_clamps           # one test by name
pytest apps/taxes/tests/test_services.py::test_fifo_capital_gain_on_sale

# lint (line-length 110, migrations excluded)
ruff check apps config manage.py
ruff check --fix apps config manage.py

# migrations
python manage.py makemigrations
python manage.py makemigrations --check --dry-run   # CI-style check

# CSS — Tailwind v4 standalone binary, no Node in this project
/tmp/tailwindcss -i static_src/css/input.css -o static/css/output.css --minify
```

`static_src/css/input.css` is the Tailwind **source** and is deliberately
outside `STATICFILES_DIRS` — collectstatic chokes on its `@import "tailwindcss"`
if it is collectable. Custom classes (`.card`, `.btn-primary`, `.form-input`)
are declared with Tailwind v4's `@utility`, not `@apply` inside `@layer`.

Data-feed commands:

```bash
python manage.py update_fx_rates
python manage.py update_security_prices [--provider stooq]
python manage.py backfill_security_prices --since 2025-12-01 [--until ...] [--identifier ...]
```

## Architecture

### Multi-tenancy is the load-bearing invariant

Every tenant-scoped model inherits `HouseholdOwnedModel` (or
`PersonallyOwnedModel`) from `apps/accounts/models.py`, which supplies a
`household` FK and `HouseholdScopedQuerySet`.

- `ActiveHouseholdMiddleware` resolves `request.household` from the session,
  **re-validating membership on every request** (so removing a member revokes
  access immediately).
- Views use `@household_required` (`apps/accounts/decorators.py`) and query
  through `Model.objects.for_household(request.household)` — never an
  unscoped queryset.
- Forms take a `household=` kwarg and narrow every `ModelChoiceField`
  queryset with it. That is what stops a crafted POST from attaching a
  foreign account/category; there are tests asserting exactly this.

`apps/accounts/tests/test_household_isolation.py` is the guardrail. Keep it
passing.

### `owner = None` means "commun au foyer"

`PersonallyOwnedModel.owner` is nullable and `on_delete=PROTECT`. PROTECT is
deliberate: `SET_NULL` would silently turn a member's **private** account into
a **shared** one when their user is deleted. Used by `FinancialAccount`,
`RealAsset`, `Liability`, `BudgetLine`.

Actuals are attributed to a person **through the account** a transaction sits
on — personal account → that member's budget, joint account → commun. Nothing
extra is tagged at entry or import time. Security holdings follow the same
rule, via the brokerage account they sit in.

`apps/accounts/perimeters.py` is the single place that labels and orders those
owners: **Moi → Commun au foyer → autres membres**. It is presentation only —
every member still sees everything, the household is the trust boundary. Pass
`viewer=request.user` to get the "Moi" labelling; omit it (as background jobs
do) and the neutral commun-first ordering is used instead. Reuse
`group_by_owner()` rather than re-deriving this per page.

### Money-correctness rules that are easy to break

These are decisions, not accidents. Changing them silently corrupts figures:

1. **Recurring transactions never create `Transaction` rows.** They are
   forecast-only (`apps/budget/recurring.py`). Real movements come from the
   CSV import or manual entry; materializing recurrences too would
   double-count every rent and salary.
2. **Projections only count occurrences strictly after today**
   (`apps/budget/projections.py`), for the same reason — anything earlier this
   month is assumed already in the balance. Future-dated transactions the user
   entered *are* counted.
3. **Occurrences are `start_date + n × period`**, never stepped from the
   previous one, so a rent due on the 31st clamps to the 28th in February and
   returns to the 31st instead of drifting.
4. **Any change to a `SecurityTransaction` recomputes every later sale** on
   that account+security (`apps/taxes/signals.py` → `recompute_capital_gains_for`).
   FIFO makes each sale's cost basis depend on the whole prior history, so
   recomputing only the saved row leaves stale tax figures.
5. **A price quote whose currency disagrees with `Security.currency` is
   refused**, not stored — a USD quote on a EUR-denominated holding would
   inflate net worth invisibly.
6. **Degraded valuations are surfaced, never silent.** No quote → valued at
   cost basis; no FX rate → counted unconverted; stale quote → flagged. Each
   appends to a `warnings` list rendered on the page.

### Service layer

Business logic lives in modules beside the models, and views stay thin. When
adding behaviour, extend these rather than the views:

| Module | Responsibility |
|---|---|
| `apps/budget/budgets.py` | budget vs actuals for a month, per member + commun |
| `apps/budget/recurring.py` | occurrence maths |
| `apps/budget/projections.py` | projected end-of-month balances |
| `apps/wealth/services.py` | FIFO holdings, net worth, quote staleness |
| `apps/wealth/pricing.py` | fetch/store prices, currency guard, error isolation |
| `apps/taxes/services.py` | Belgian TOB / précompte / plus-value calculations |
| `apps/imports_app/services.py` | CSV parsing, duplicate detection, import |
| `apps/fx/services.py` | `convert()` and the shared `to_base_currency()` |

`to_base_currency(amount, code, base, label, warnings)` is the one conversion
entry point — both `wealth` and `budget` use it. It only resolves **direct or
inverse** rates (no triangulation), which covers every EUR↔X case.

### Pluggable price providers

`apps/wealth/providers/` holds one class per market-data source (`yahoo`,
`stooq`, `twelvedata`), selected by `SECURITY_PRICE_PROVIDER` in `.env` and
overridable per security via `Security.price_provider`. Nothing outside that
package imports a provider library.

- Symbols are **provider-specific** (`IWDA.AS` on Yahoo, `iwda.nl` on Stooq)
  and distinct from the ISIN stored in `Security.identifier`.
- Providers return `currency=None` when they don't know (Stooq); the caller
  then trusts the configured currency instead of refusing the quote.
- Adding a source = a class with `fetch_quote` / `fetch_history` plus a
  registry entry.

**Tests must never hit the network.** Pass a fake provider into
`sync_security_price(security, provider=...)`; provider parsing is tested
against realistically-shaped payloads in `apps/wealth/tests/test_providers.py`,
including failures that arrive as HTTP 200 (Stooq's `N/D` body, Twelve Data's
quota errors).

### Belgian tax rules are data, not constants

`TOBRate`, `PrecompteMobilierRule` and `PlusValueTaxRule` are DB rows seeded by
`apps/taxes/migrations/0002_seed_2026_tax_rules.py` and editable in the Django
admin, so rates and indexed thresholds change without a deploy. Seeded values
are best-effort and carry an in-app disclaimer — treat them as configuration to
verify, not as authoritative law.

The plus-value calculation grandfathers pre-2026 holdings by using the higher
of the FIFO cost basis or the 31/12/2025 reference `PriceSnapshot`;
`backfill_security_prices --since 2025-12-01` is how that reference price gets
populated.

### Conventions

- Settings split under `config/settings/` (`base` / `dev` / `prod`), env-driven
  via `django-environ`; `manage.py` defaults to `config.settings.dev`.
- Money is always `Decimal`. Transaction amounts are **signed** (negative =
  outflow); `BudgetLine.planned_amount` is a positive magnitude, and
  `budgets.py` normalizes actuals to magnitudes for comparison.
- Tests use `pytest-django` + `factory_boy`; shared factories live in
  `apps/accounts/tests/factories.py`.
- The CSV import app is `imports_app` (not `imports`) with `app_name =
  "imports_app"` in its URLconf.
