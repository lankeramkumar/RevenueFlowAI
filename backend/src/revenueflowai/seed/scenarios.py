"""Fixed scenario ledger (S01-S17 in synthetic_data_requirements.md).

Only S01 and S09 are implemented in this Foundation milestone, as the
smallest end-to-end proof (a partial-payment balance and a currency
boundary) for the first vertical slice. The remaining scenarios (S02-S08,
S10-S17) are tracked in docs/implementation-plan.md and implemented
alongside the full domain-logic layer in Milestone 3 — do not treat their
absence here as silent scope-dropping.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

Row = dict[str, str]


@dataclass
class ScenarioBundle:
    scenario_id: str
    description: str
    rows: dict[str, list[Row]] = field(default_factory=dict)
    expected: dict = field(default_factory=dict)

    def add(self, filename: str, row: Row) -> None:
        self.rows.setdefault(filename, []).append(row)


def _money(value) -> str:
    return f"{value:.2f}"


def build_s01_partial_payment(as_of: date) -> ScenarioBundle:
    """Invoice 1,000 due D-45; effective receipt application 300; effective
    credit application 100 -> open balance 600, 45 days overdue, bucket 31-60.
    """
    bundle = ScenarioBundle("S01", "partial payment")
    due_date = as_of - timedelta(days=45)
    invoice_date = due_date - timedelta(days=30)

    bundle.add("customers.csv", {
        "customer_id": "S01-CUST", "account_number": "ACC-S01", "customer_name": "Scenario S01 Co",
        "payment_terms_days": "30",
    })
    bundle.add("invoices.csv", {
        "invoice_id": "S01-INV-1000", "customer_id": "S01-CUST", "order_id": "",
        "invoice_date": invoice_date.isoformat(), "due_date": due_date.isoformat(),
        "currency": "USD", "invoice_amount": _money(1000), "status": "posted",
    })
    bundle.add("receipts.csv", {
        "receipt_id": "S01-RCP", "customer_id": "S01-CUST", "receipt_date": due_date.isoformat(),
        "currency": "USD", "receipt_amount": _money(300), "status": "posted",
        "remittance_reference": "S01-INV-1000",
    })
    bundle.add("receipt_applications.csv", {
        "application_id": "S01-APP-1", "receipt_id": "S01-RCP", "invoice_id": "S01-INV-1000",
        "applied_amount": _money(300), "application_date": due_date.isoformat(), "status": "posted",
    })
    bundle.add("credit_memos.csv", {
        "credit_memo_id": "S01-CM", "customer_id": "S01-CUST", "invoice_id": "S01-INV-1000",
        "currency": "USD", "credit_amount": _money(100), "status": "posted",
    })
    bundle.add("credit_applications.csv", {
        "credit_application_id": "S01-CAPP-1", "credit_memo_id": "S01-CM", "invoice_id": "S01-INV-1000",
        "applied_amount": _money(100), "application_date": due_date.isoformat(), "status": "posted",
    })

    bundle.expected = {
        "invoice_id": "S01-INV-1000",
        "open_balance": "600.00",
        "currency": "USD",
        "days_overdue": 45,
        "aging_bucket": "31-60",
    }
    return bundle


def build_s09_currency_boundary(as_of: date) -> ScenarioBundle:
    """USD invoice 100 and EUR invoice 200, both overdue -> separate per-currency totals, never summed."""
    bundle = ScenarioBundle("S09", "currency boundary")
    due_date = as_of - timedelta(days=5)
    invoice_date = due_date - timedelta(days=30)

    bundle.add("customers.csv", {
        "customer_id": "S09-CUST", "account_number": "ACC-S09", "customer_name": "Scenario S09 Co",
        "payment_terms_days": "30",
    })
    bundle.add("invoices.csv", {
        "invoice_id": "S09-INV-USD", "customer_id": "S09-CUST", "order_id": "",
        "invoice_date": invoice_date.isoformat(), "due_date": due_date.isoformat(),
        "currency": "USD", "invoice_amount": _money(100), "status": "posted",
    })
    bundle.add("invoices.csv", {
        "invoice_id": "S09-INV-EUR", "customer_id": "S09-CUST", "order_id": "",
        "invoice_date": invoice_date.isoformat(), "due_date": due_date.isoformat(),
        "currency": "EUR", "invoice_amount": _money(200), "status": "posted",
    })

    bundle.expected = {
        "totals_by_currency": {"USD": "100.00", "EUR": "200.00"},
        "note": "Never combined into a single cross-currency total.",
    }
    return bundle


IMPLEMENTED_SCENARIOS = (build_s01_partial_payment, build_s09_currency_boundary)
