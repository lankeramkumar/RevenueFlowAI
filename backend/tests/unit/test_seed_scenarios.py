"""Unit tests for the synthetic data generator (Foundation milestone: S01, S09 only).

Expected values are hand-authored from synthetic_data_requirements.md's
scenario ledger, independently of the generator — per the spec's "expected
values must not be calculated by the domain implementation under test" rule.
"""

from datetime import date
from decimal import Decimal

from revenueflowai.seed.scenarios import build_s01_partial_payment, build_s09_currency_boundary

AS_OF = date(2026, 10, 2)


def test_s01_partial_payment_open_balance_matches_hand_calculation():
    bundle = build_s01_partial_payment(AS_OF)

    invoice_amount = Decimal(bundle.rows["invoices.csv"][0]["invoice_amount"])
    applied = Decimal(bundle.rows["receipt_applications.csv"][0]["applied_amount"])
    credited = Decimal(bundle.rows["credit_applications.csv"][0]["applied_amount"])

    open_balance = invoice_amount - applied - credited

    assert open_balance == Decimal("600.00")
    assert bundle.expected["open_balance"] == "600.00"
    assert bundle.expected["days_overdue"] == 45
    assert bundle.expected["aging_bucket"] == "31-60"

    due_date = date.fromisoformat(bundle.rows["invoices.csv"][0]["due_date"])
    assert (AS_OF - due_date).days == 45


def test_s09_currency_totals_are_never_combined():
    bundle = build_s09_currency_boundary(AS_OF)

    invoices = bundle.rows["invoices.csv"]
    totals_by_currency = {row["currency"]: Decimal(row["invoice_amount"]) for row in invoices}

    assert totals_by_currency == {"USD": Decimal("100.00"), "EUR": Decimal("200.00")}
    assert bundle.expected["totals_by_currency"] == {"USD": "100.00", "EUR": "200.00"}
    # No combined cross-currency total should ever be computed from this fixture.
    assert "300.00" not in bundle.expected["totals_by_currency"].values()
