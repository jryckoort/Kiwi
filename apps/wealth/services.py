from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .models import Liability, NetWorthSnapshot, RealAsset, Security, SecurityTransaction


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


def _to_base_currency(amount, currency_code, base_currency, label, warnings):
    """Convert into the household's base currency, degrading gracefully.

    A missing exchange rate must never silently distort the total: the raw
    amount is still counted, but the item is recorded in ``warnings`` so the
    UI can say the figure mixes currencies.
    """
    from apps.fx.services import ExchangeRateUnavailable, convert

    if currency_code == base_currency:
        return amount
    try:
        return convert(amount, currency_code, base_currency)
    except ExchangeRateUnavailable:
        warnings.append(f"{label} : montant en {currency_code} non converti (taux indisponible)")
        return amount


def compute_net_worth(household):
    """Net worth in the household's base currency.

    Covers cash accounts, the market value of security holdings, real assets
    and liabilities. Amounts held in another currency are converted through
    the fx app; anything that could not be converted is listed in
    ``breakdown["warnings"]``.
    """
    from django.db.models import Sum

    from apps.budget.models import FinancialAccount

    base_currency = household.base_currency
    total_assets = Decimal(0)
    warnings = []
    breakdown = {
        "accounts": {},
        "securities": {},
        "real_assets": {},
        "liabilities": {},
        "warnings": warnings,
    }

    accounts = FinancialAccount.objects.for_household(household).filter(is_archived=False)
    for account in accounts:
        balance = account.transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
        balance = _to_base_currency(
            balance, account.currency_id, base_currency, account.name, warnings
        )
        total_assets += balance
        breakdown["accounts"][account.name] = str(balance)

        for holding in compute_holdings(account):
            security = Security.objects.get(pk=holding.security_id)
            price = latest_price(security)
            if price is None:
                # No quote on file — fall back to what was paid rather than
                # dropping the position out of the total entirely.
                value = holding.cost_basis
                warnings.append(f"{security.name} : aucun cours connu, valorisé au prix de revient")
            else:
                value = price * holding.quantity
            value = _to_base_currency(
                value, security.currency_id, base_currency, security.name, warnings
            )
            total_assets += value
            breakdown["securities"][f"{account.name} · {security.name}"] = str(value)

    for asset in RealAsset.objects.for_household(household):
        value = _to_base_currency(
            asset.current_value, asset.currency_id, base_currency, asset.name, warnings
        )
        total_assets += value
        breakdown["real_assets"][asset.name] = str(value)

    total_liabilities = Decimal(0)
    for liability in Liability.objects.for_household(household):
        value = _to_base_currency(
            liability.remaining_balance,
            liability.currency_id,
            base_currency,
            liability.name,
            warnings,
        )
        total_liabilities += value
        breakdown["liabilities"][liability.name] = str(value)

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
