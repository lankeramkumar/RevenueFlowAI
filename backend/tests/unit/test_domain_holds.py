"""S07, S08 — recorded hold reasons, never an asserted cause."""

from datetime import date, timedelta

from revenueflowai.domain.holds import present_hold

D = date(2026, 10, 2)


def test_s07_recorded_hold_states_reason_not_overdue_invoice_as_cause():
    result = present_hold(
        status="active", hold_reason="MISSING_SHIP_TO",
        applied_date=D - timedelta(days=10), released_date=None,
        linked_invoice_id=None,  # no source record links this hold to an invoice
        as_of=D,
    )
    assert result.is_active is True
    assert result.hold_reason == "MISSING_SHIP_TO"
    assert result.linked_invoice_id is None  # never asserted without source evidence
    assert result.age_days == 10


def test_s08_released_hold_excluded_from_active_count():
    result = present_hold(
        status="released", hold_reason="CREDIT_LIMIT",
        applied_date=D - timedelta(days=20), released_date=D - timedelta(days=1),
        linked_invoice_id=None,
        as_of=D,
    )
    assert result.is_active is False
    assert result.age_days is None
