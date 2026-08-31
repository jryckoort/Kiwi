from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .models import Liability, NetWorthSnapshot, RealAsset, SecurityTransaction


def latest_price(security):
    snapshot = security.prices.order_by("-date").first()
    return snapshot.price if snapshot else None


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


def compute_net_worth(household):
    """Best-effort net worth in the household's base currency, ignoring FX
    conversion for now (v1 assumes accounts mostly share the base currency —
    proper multi-currency roll-up is a follow-up).
    """
    from django.db.models import Sum

    from apps.budget.models import FinancialAccount

    total_assets = Decimal(0)
    breakdown = {"accounts": {}, "real_assets": {}, "liabilities": {}}

    for account in FinancialAccount.objects.for_household(household).filter(is_archived=False):
        balance = account.transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
        total_assets += balance
        breakdown["accounts"][account.name] = str(balance)

    for asset in RealAsset.objects.for_household(household):
        total_assets += asset.current_value
        breakdown["real_assets"][asset.name] = str(asset.current_value)

    total_liabilities = Decimal(0)
    for liability in Liability.objects.for_household(household):
        total_liabilities += liability.remaining_balance
        breakdown["liabilities"][liability.name] = str(liability.remaining_balance)

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
