"""Domain balance/aging tests mapped to the S01-S17 scenario ledger in
synthetic_data_requirements.md. Expected values are transcribed directly
from that table, not computed by the code under test.
"""

from datetime import date, timedelta
from decimal import Decimal

from revenueflowai.domain.balances import (
    Application,
    annotate_dispute,
    check_overapplication,
    compute_aging_bucket,
    compute_days_overdue,
    compute_invoice_open_balance,
    compute_unapplied_receipt_amount,
)

D = date(2026, 10, 2)  # arbitrary fixed as-of date


def test_s01_partial_payment():
    due = D - timedelta(days=45)
    days_overdue = compute_days_overdue(D, due)
    balance = compute_invoice_open_balance(
        Decimal("1000"), "posted",
        receipt_applications=[Application(Decimal("300"), "posted")],
        credit_applications=[Application(Decimal("100"), "posted")],
    )
    assert balance == Decimal("600")
    assert days_overdue == 45
    assert compute_aging_bucket(days_overdue) == "31-60"


def test_s02_disputed_invoice_does_not_reduce_balance():
    due = D - timedelta(days=20)
    balance = compute_invoice_open_balance(Decimal("800"), "posted", [], [])
    dispute = annotate_dispute([(Decimal("200"), "open")])

    assert balance == Decimal("800")  # dispute annotates, never reduces
    assert dispute.open_dispute_amount == Decimal("200")
    assert compute_aging_bucket(compute_days_overdue(D, due)) == "1-30"


def test_s09_currency_boundary_totals_stay_separate():
    due = D - timedelta(days=5)
    usd_balance = compute_invoice_open_balance(Decimal("100"), "posted", [], [])
    eur_balance = compute_invoice_open_balance(Decimal("200"), "posted", [], [])
    totals_by_currency = {"USD": usd_balance, "EUR": eur_balance}

    assert totals_by_currency == {"USD": Decimal("100"), "EUR": Decimal("200")}
    assert compute_days_overdue(D, due) == 5


def test_s10_reversed_application_excluded():
    balance = compute_invoice_open_balance(
        Decimal("1000"), "posted",
        receipt_applications=[
            Application(Decimal("250"), "posted"),
            Application(Decimal("100"), "reversed"),  # excluded
        ],
        credit_applications=[],
    )
    assert balance == Decimal("750")


def test_s11_partial_receipt_unapplied_amount():
    unapplied = compute_unapplied_receipt_amount(
        Decimal("1000"), "posted", [Application(Decimal("700"), "posted")]
    )
    assert unapplied == Decimal("300")


def test_s12_due_date_boundaries():
    # due_date = D + offset (so offset=-30 means "due 30 days before D", i.e. D-30)
    offsets_and_expected = [
        (1, 0), (0, 0), (-1, 1), (-30, 30), (-31, 31),
        (-60, 60), (-61, 61), (-90, 90), (-91, 91),
    ]
    for offset, expected_days in offsets_and_expected:
        due = D + timedelta(days=offset)
        assert compute_days_overdue(D, due) == expected_days

    bucket_expectations = {
        0: "not_due", 1: "1-30", 30: "1-30", 31: "31-60",
        60: "31-60", 61: "61-90", 90: "61-90", 91: "91+",
    }
    for days, bucket in bucket_expectations.items():
        assert compute_aging_bucket(days) == bucket


def test_overapplication_is_flagged_not_clamped():
    balance = compute_invoice_open_balance(
        Decimal("100"), "posted",
        receipt_applications=[Application(Decimal("150"), "posted")],
        credit_applications=[],
    )
    flag = check_overapplication(Decimal("100"), balance)

    assert balance == Decimal("-50")  # not clamped to 0
    assert flag is not None
    assert flag.excess == Decimal("50")


def test_draft_invoice_has_no_open_balance():
    assert compute_invoice_open_balance(Decimal("500"), "draft", [], []) is None


def test_cancelled_receipt_contributes_no_available_cash():
    assert compute_unapplied_receipt_amount(Decimal("500"), "cancelled", []) is None


def test_overlapping_open_disputes_are_flagged():
    dispute = annotate_dispute([(Decimal("100"), "open"), (Decimal("50"), "open")])
    assert dispute.open_dispute_amount == Decimal("150")
    assert dispute.flagged_overlapping is True
