from datetime import date
from decimal import Decimal

from apps.wealth.models import PriceSnapshot, SecurityTransaction
from apps.wealth.services import fifo_cost_basis_for_sale

from .models import CapitalGainRecord, PlusValueTaxRule, PrecompteMobilierRule, TOBRate

TWO_PLACES = Decimal("0.01")


def _rule_for_year(model, year):
    return model.objects.filter(year=year).first() or model.objects.order_by("-year").first()


def compute_and_store_capital_gain(sell_tx):
    """Called whenever a SecurityTransaction of type SELL is saved — turns it
    into a CapitalGainRecord using FIFO cost basis, grandfathered against the
    31/12/2025 reference value when one is on file for that security.
    """
    if sell_tx.type != SecurityTransaction.Type.SELL:
        return None

    fifo_cost = fifo_cost_basis_for_sale(sell_tx)

    rule = _rule_for_year(PlusValueTaxRule, sell_tx.date.year)
    reference_date = rule.reference_date if rule else date(2025, 12, 31)
    reference_snapshot = PriceSnapshot.objects.filter(
        security=sell_tx.security, date=reference_date
    ).first()

    cost_basis = fifo_cost
    if reference_snapshot and sell_tx.quantity:
        reference_cost = sell_tx.quantity * reference_snapshot.price
        cost_basis = max(fifo_cost, reference_cost)

    proceeds = sell_tx.gross_amount - sell_tx.fees
    realized_gain = proceeds - cost_basis

    record, _ = CapitalGainRecord.objects.update_or_create(
        security_transaction=sell_tx,
        defaults={
            "household_id": sell_tx.household_id,
            "cost_basis": cost_basis,
            "proceeds": proceeds,
            "realized_gain": realized_gain,
            "tax_year": sell_tx.date.year,
        },
    )
    return record


def compute_annual_plus_value_tax(household, year):
    """Aggregates realized gains for the household over a calendar year.

    Belgian law grants the annual exemption per taxpayer, not per household;
    this v1 aggregates at household level as a simplification — splitting
    per member is a follow-up once holdings are attributed per person.
    """
    records = CapitalGainRecord.objects.for_household(household).filter(tax_year=year)
    total_gain = sum((r.realized_gain for r in records), Decimal(0))

    rule = _rule_for_year(PlusValueTaxRule, year)
    if rule is None:
        raise ValueError("Aucun barème de taxe sur la plus-value n'est configuré.")

    taxable = max(total_gain - rule.annual_exemption, Decimal(0))
    tax_due = (taxable * rule.rate_percent / 100).quantize(TWO_PLACES)
    return {
        "year": year,
        "total_gain": total_gain,
        "exemption": rule.annual_exemption,
        "taxable": taxable,
        "rate_percent": rule.rate_percent,
        "tax_due": tax_due,
    }


def compute_plus_value_whatif(acquisition_value: Decimal, sale_value: Decimal, year=None):
    """Simulate the plus-value tax for a hypothetical sale, ignoring any other
    gains already realized that year (use compute_annual_plus_value_tax for
    the real, holdings-based figure).
    """
    year = year or date.today().year
    rule = _rule_for_year(PlusValueTaxRule, year)
    if rule is None:
        raise ValueError("Aucun barème de taxe sur la plus-value n'est configuré.")

    gain = max(sale_value - acquisition_value, Decimal(0))
    taxable = max(gain - rule.annual_exemption, Decimal(0))
    tax_due = (taxable * rule.rate_percent / 100).quantize(TWO_PLACES)
    return {
        "gain": gain,
        "exemption": rule.annual_exemption,
        "taxable": taxable,
        "rate_percent": rule.rate_percent,
        "tax_due": tax_due,
        "net_proceeds": sale_value - tax_due,
    }


def compute_tob(instrument_type: str, gross_amount: Decimal):
    rate = TOBRate.objects.filter(instrument_type=instrument_type).first()
    if rate is None:
        raise ValueError("Type d'instrument TOB inconnu.")

    raw_tax = (gross_amount * rate.rate_percent / 100).quantize(TWO_PLACES)
    tax_due = min(raw_tax, rate.cap_amount)
    return {
        "rate_percent": rate.rate_percent,
        "cap_amount": rate.cap_amount,
        "raw_tax": raw_tax,
        "tax_due": tax_due,
        "capped": tax_due < raw_tax,
    }


def compute_precompte_mobilier(gross_income: Decimal, is_regulated_savings: bool, year=None):
    year = year or date.today().year
    rule = _rule_for_year(PrecompteMobilierRule, year)
    if rule is None:
        raise ValueError("Aucune règle de précompte mobilier n'est configurée.")

    if is_regulated_savings:
        taxable = max(gross_income - rule.savings_account_exempt_threshold, Decimal(0))
    else:
        taxable = gross_income

    tax_due = (taxable * rule.rate_percent / 100).quantize(TWO_PLACES)
    return {
        "rate_percent": rule.rate_percent,
        "exempt_threshold": rule.savings_account_exempt_threshold if is_regulated_savings else Decimal(0),
        "taxable": taxable,
        "tax_due": tax_due,
        "net_income": gross_income - tax_due,
    }
