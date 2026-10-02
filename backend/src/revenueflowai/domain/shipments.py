"""Shipped/unbilled exception calculations — intent.md's partial-billing rules."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class UnbilledResult:
    unbilled_quantity: Decimal
    estimated_value: Decimal  # unbilled_quantity * order unit price — an ESTIMATE, not revenue/invoice amount
    sufficient_evidence: bool


def compute_unbilled_shipment(
    shipped_quantity: Decimal,
    billed_quantity: Decimal | None,
    unit_price: Decimal,
    shipment_date: date,
    as_of: date,
    age_threshold_days: int,
    has_sufficient_links: bool,
) -> UnbilledResult | None:
    """None if the shipment hasn't crossed the age threshold yet (not an
    exception). `has_sufficient_links=False` means the invoice line lacks a
    shipment/order link or billed quantity — intent.md requires reporting
    "insufficient evidence" rather than asserting the shipment is unbilled.
    """
    age_days = (as_of - shipment_date).days
    if age_days < age_threshold_days:
        return None

    if not has_sufficient_links:
        return UnbilledResult(
            unbilled_quantity=Decimal("0"), estimated_value=Decimal("0"), sufficient_evidence=False
        )

    billed = billed_quantity if billed_quantity is not None else Decimal("0")
    unbilled_qty = shipped_quantity - billed
    return UnbilledResult(
        unbilled_quantity=unbilled_qty,
        estimated_value=unbilled_qty * unit_price,
        sufficient_evidence=True,
    )
