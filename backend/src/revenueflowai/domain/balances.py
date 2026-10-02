"""Deterministic invoice balance and aging calculations — pure Decimal
arithmetic, no LLM involvement, per intent.md's "Deterministic business
calculations" section. These operate on plain values so they're testable
without a database; Milestone 3's continuation wraps them with SQL queries
that select the right effective applications for a given dataset version.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

AGING_BUCKETS = ("not_due", "1-30", "31-60", "61-90", "91+")

# Only these statuses count as "effective" per intent.md: reversed/draft/void
# applications and invoices never contribute to a balance calculation.
EFFECTIVE_INVOICE_STATUSES = frozenset({"posted"})
EFFECTIVE_APPLICATION_STATUSES = frozenset({"posted"})
EFFECTIVE_RECEIPT_STATUSES = frozenset({"posted"})


@dataclass(frozen=True)
class Application:
    amount: Decimal
    status: str


def compute_days_overdue(as_of: date, due_date: date) -> int:
    """max(0, as_of - due_date). An invoice due today is not overdue."""
    return max(0, (as_of - due_date).days)


def compute_aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "not_due"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "91+"


def compute_invoice_open_balance(
    invoice_amount: Decimal,
    invoice_status: str,
    receipt_applications: list[Application],
    credit_applications: list[Application],
) -> Decimal | None:
    """Open balance = posted invoice amount - effective receipt applications
    - effective credit applications. Returns None for a non-posted invoice
    (draft/void), since it has no open balance to report. Disputes are
    deliberately not a parameter here — they annotate a balance, never
    reduce it (see `annotate_dispute` below).
    """
    if invoice_status not in EFFECTIVE_INVOICE_STATUSES:
        return None

    effective_receipts = sum(
        (a.amount for a in receipt_applications if a.status in EFFECTIVE_APPLICATION_STATUSES),
        start=Decimal("0"),
    )
    effective_credits = sum(
        (a.amount for a in credit_applications if a.status in EFFECTIVE_APPLICATION_STATUSES),
        start=Decimal("0"),
    )
    return invoice_amount - effective_receipts - effective_credits


@dataclass(frozen=True)
class OverapplicationFlag:
    invoice_amount: Decimal
    total_applied: Decimal
    excess: Decimal


def check_overapplication(
    invoice_amount: Decimal, open_balance: Decimal
) -> OverapplicationFlag | None:
    """Flag (never silently clamp) when applications exceed the invoice amount."""
    if open_balance >= 0:
        return None
    total_applied = invoice_amount - open_balance
    return OverapplicationFlag(invoice_amount, total_applied, excess=-open_balance)


def compute_unapplied_receipt_amount(
    receipt_amount: Decimal, receipt_status: str, applications: list[Application]
) -> Decimal | None:
    """Unapplied = effective receipt amount - effective applications.
    None for a cancelled receipt (it contributes no available cash).
    """
    if receipt_status not in EFFECTIVE_RECEIPT_STATUSES:
        return None
    effective_applied = sum(
        (a.amount for a in applications if a.status in EFFECTIVE_APPLICATION_STATUSES),
        start=Decimal("0"),
    )
    return receipt_amount - effective_applied


@dataclass(frozen=True)
class DisputeAnnotation:
    open_dispute_amount: Decimal
    flagged_overlapping: bool


def annotate_dispute(disputed_amounts: list[tuple[Decimal, str]]) -> DisputeAnnotation:
    """Sum amounts of *open* disputes; flag (don't silently resolve) if more
    than one open dispute exists for the same invoice, since overlapping
    disputes need human review rather than a summed guess.
    """
    open_amounts = [amount for amount, status in disputed_amounts if status == "open"]
    return DisputeAnnotation(
        open_dispute_amount=sum(open_amounts, start=Decimal("0")),
        flagged_overlapping=len(open_amounts) > 1,
    )
