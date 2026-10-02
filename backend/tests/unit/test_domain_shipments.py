"""S05, S06, S14 — partial/full/insufficient-evidence shipment reconciliation."""

from datetime import date, timedelta
from decimal import Decimal

from revenueflowai.domain.shipments import compute_unbilled_shipment

D = date(2026, 10, 2)


def test_s05_partial_billing():
    result = compute_unbilled_shipment(
        shipped_quantity=Decimal("8"),
        billed_quantity=Decimal("5"),
        unit_price=Decimal("100"),
        shipment_date=D - timedelta(days=7),
        as_of=D,
        age_threshold_days=5,
        has_sufficient_links=True,
    )
    assert result.unbilled_quantity == Decimal("3")
    assert result.estimated_value == Decimal("300")
    assert result.sufficient_evidence is True


def test_s06_fully_unbilled():
    result = compute_unbilled_shipment(
        shipped_quantity=Decimal("4"),
        billed_quantity=None,
        unit_price=Decimal("50"),
        shipment_date=D - timedelta(days=8),
        as_of=D,
        age_threshold_days=5,
        has_sufficient_links=True,
    )
    assert result.unbilled_quantity == Decimal("4")
    assert result.estimated_value == Decimal("200")


def test_s14_insufficient_billing_links_reports_unavailable_not_unbilled():
    result = compute_unbilled_shipment(
        shipped_quantity=Decimal("10"),
        billed_quantity=None,
        unit_price=Decimal("10"),
        shipment_date=D - timedelta(days=30),
        as_of=D,
        age_threshold_days=5,
        has_sufficient_links=False,
    )
    assert result.sufficient_evidence is False
    # Must not assert a definitive unbilled quantity when evidence is insufficient.
    assert result.unbilled_quantity == Decimal("0")


def test_below_age_threshold_is_not_an_exception():
    result = compute_unbilled_shipment(
        shipped_quantity=Decimal("10"),
        billed_quantity=Decimal("0"),
        unit_price=Decimal("10"),
        shipment_date=D - timedelta(days=2),
        as_of=D,
        age_threshold_days=5,
        has_sufficient_links=True,
    )
    assert result is None
