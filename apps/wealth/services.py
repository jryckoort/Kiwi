from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings

from apps.fx.services import to_base_currency

from .models import Liability, NetWorthSnapshot, RealAsset, Security, SecurityTransaction


def latest_price(security):
    snapshot = security.prices.order_by("-date").first()
    return snapshot.price if snapshot else None


def latest_quote(security):
    """Most recent price with its date, so callers can judge staleness."""
    snapshot = security.prices.order_by("-date").first()
    if snapshot is None:
        return None, None
    return snapshot.price, snapshot.date


def is_stale(quote_date, as_of=None):
    if quote_date is None:
        return True
    as_of = as_of or date.today()
    return (as_of - quote_date).days > settings.STALE_PRICE_AFTER_DAYS


@dataclass
class Holding:
    security_id: int
    quantity: Decimal
    cost_basis: Decimal

    @property
    def average_cost(self):
        if self.quantity:
            return self.cost_basis / self.quantity
        return Decimal(0)


def compute_holdings(account):
    """Current open positions for one investment account, FIFO-costed."""
    lots_by_security = defaultdict(list)  # security_id -> list of [qty, unit_cost]

    txs = SecurityTransaction.objects.filter(
        account=account, type__in=[SecurityTransaction.Type.BUY, SecurityTransaction.Type.SELL]
    ).order_by("date", "id")

    for tx in txs:
        lots = lots_by_security[tx.security_id]
        if tx.type == SecurityTransaction.Type.BUY:
            unit_cost = (tx.quantity * tx.price + tx.fees) / tx.quantity
            lots.append([tx.quantity, unit_cost])
        else:
            _consume_fifo(lots, tx.quantity)

    holdings = []
    for security_id, lots in lots_by_security.items():
        quantity = sum((lot[0] for lot in lots), Decimal(0))
        cost_basis = sum((lot[0] * lot[1] for lot in lots), Decimal(0))
        if quantity > 0:
            holdings.append(Holding(security_id=security_id, quantity=quantity, cost_basis=cost_basis))
    return holdings


def fifo_cost_basis_for_sale(sell_tx):
    """Replay every buy/sell for this account+security up to and including
    ``sell_tx`` and return the total FIFO cost basis consumed by that sale.
    """
    lots = []
    txs = SecurityTransaction.objects.filter(
        account=sell_tx.account,
        security=sell_tx.security,
        type__in=[SecurityTransaction.Type.BUY, SecurityTransaction.Type.SELL],
        date__lte=sell_tx.date,
    ).order_by("date", "id")

    cost_for_target = Decimal(0)
    for tx in txs:
        if tx.type == SecurityTransaction.Type.BUY:
            unit_cost = (tx.quantity * tx.price + tx.fees) / tx.quantity
            lots.append([tx.quantity, unit_cost])
        else:
            cost_removed = _consume_fifo(lots, tx.quantity)
            if tx.id == sell_tx.id:
                cost_for_target = cost_removed
    return cost_for_target


def _consume_fifo(lots, quantity):
    remaining = quantity
    cost_removed = Decimal(0)
    while remaining > 0 and lots:
        lot = lots[0]
        take = min(lot[0], remaining)
        cost_removed += take * lot[1]
        lot[0] -= take
        remaining -= take
        if lot[0] <= 0:
            lots.pop(0)
    return cost_removed


@dataclass
class NetWorthItem:
    """One line of net worth, already converted to the household's base currency.

    ``owner`` is who it belongs to (None = commun). A security holding is
    attributed through the account it sits in — the same rule budgets use for
    actuals, so the two views never disagree about whose money is whose.
    """

    owner: object  # User, or None for commun
    kind: str  # account | security | real_asset | liability
    label: str
    value: Decimal  # positive magnitude; liabilities are flagged, not negated

    @property
    def is_liability(self):
        return self.kind == "liability"


def collect_net_worth_items(household):
    """Every net worth line for a household, plus the warnings raised on the way.

    Both the flat total and the per-owner breakdown are built from this, so
    they can never drift apart.
    """
    from django.db.models import Sum

    from apps.budget.models import FinancialAccount

    base_currency = household.base_currency
    warnings = []
    items = []

    accounts = (
        FinancialAccount.objects.for_household(household)
        .filter(is_archived=False)
        .select_related("owner", "currency")
    )
    for account in accounts:
        balance = account.transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
        balance = to_base_currency(
            balance, account.currency_id, base_currency, account.name, warnings
        )
        items.append(
            NetWorthItem(owner=account.owner, kind="account", label=account.name, value=balance)
        )

        for holding in compute_holdings(account):
            security = Security.objects.get(pk=holding.security_id)
            price, quote_date = latest_quote(security)
            if price is None:
                # No quote on file — fall back to what was paid rather than
                # dropping the position out of the total entirely.
                value = holding.cost_basis
                warnings.append(f"{security.name} : aucun cours connu, valorisé au prix de revient")
            else:
                value = price * holding.quantity
                if is_stale(quote_date):
                    warnings.append(
                        f"{security.name} : cours du {quote_date:%d/%m/%Y}, potentiellement périmé"
                    )
            value = to_base_currency(
                value, security.currency_id, base_currency, security.name, warnings
            )
            items.append(
                NetWorthItem(
                    owner=account.owner,
                    kind="security",
                    label=f"{account.name} · {security.name}",
                    value=value,
                )
            )

    for asset in RealAsset.objects.for_household(household).select_related("owner"):
        value = to_base_currency(
            asset.current_value, asset.currency_id, base_currency, asset.name, warnings
        )
        items.append(
            NetWorthItem(owner=asset.owner, kind="real_asset", label=asset.name, value=value)
        )

    for liability in Liability.objects.for_household(household).select_related("owner"):
        value = to_base_currency(
            liability.remaining_balance,
            liability.currency_id,
            base_currency,
            liability.name,
            warnings,
        )
        items.append(
            NetWorthItem(
                owner=liability.owner, kind="liability", label=liability.name, value=value
            )
        )

    return items, list(dict.fromkeys(warnings))


@dataclass
class OwnerNetWorth:
    """One perimeter's slice of the household net worth."""

    perimeter: object  # accounts.perimeters.Perimeter

    @property
    def label(self):
        return self.perimeter.label

    @property
    def is_mine(self):
        return self.perimeter.is_mine

    @property
    def is_commun(self):
        return self.perimeter.is_commun

    @property
    def assets(self):
        return sum((i.value for i in self.perimeter.rows if not i.is_liability), Decimal(0))

    @property
    def liabilities(self):
        return sum((i.value for i in self.perimeter.rows if i.is_liability), Decimal(0))

    @property
    def net_worth(self):
        return self.assets - self.liabilities

    def rows_of_kind(self, kind):
        return [i for i in self.perimeter.rows if i.kind == kind]


def compute_net_worth_by_owner(household, viewer=None):
    """Net worth split per member and commun, ordered from the viewer outwards.

    The family total is the sum of the groups — the consolidated view and the
    per-person views are the same numbers, sliced differently.
    """
    from apps.accounts.perimeters import group_by_owner

    items, warnings = collect_net_worth_items(household)
    perimeters = group_by_owner(
        items,
        viewer,
        owner_of=lambda item: item.owner,
        include_owners=household.members.all(),
        include_commun=True,
    )
    groups = [OwnerNetWorth(perimeter=perimeter) for perimeter in perimeters]

    return {
        "groups": groups,
        "total_assets": sum((g.assets for g in groups), Decimal(0)),
        "total_liabilities": sum((g.liabilities for g in groups), Decimal(0)),
        "net_worth": sum((g.net_worth for g in groups), Decimal(0)),
        "base_currency": household.base_currency,
        "warnings": warnings,
    }


def compute_net_worth(household):
    """Flat household net worth in the base currency.

    Kept as the simple entry point used by the dashboard and the monthly
    snapshot; ``compute_net_worth_by_owner`` slices the same items per member.
    """
    items, warnings = collect_net_worth_items(household)

    total_assets = sum((i.value for i in items if not i.is_liability), Decimal(0))
    total_liabilities = sum((i.value for i in items if i.is_liability), Decimal(0))

    breakdown = {
        "accounts": {},
        "securities": {},
        "real_assets": {},
        "liabilities": {},
        "warnings": warnings,
    }
    section = {
        "account": "accounts",
        "security": "securities",
        "real_asset": "real_assets",
        "liability": "liabilities",
    }
    for item in items:
        breakdown[section[item.kind]][item.label] = str(item.value)

    net_worth = total_assets - total_liabilities
    return total_assets, total_liabilities, net_worth, breakdown


def snapshot_net_worth(household, on_date):
    total_assets, total_liabilities, net_worth, breakdown = compute_net_worth(household)
    return NetWorthSnapshot.objects.update_or_create(
        household=household,
        date=on_date,
        defaults={
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": net_worth,
            "breakdown": breakdown,
        },
    )
