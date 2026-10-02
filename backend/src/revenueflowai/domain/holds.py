"""Order hold presentation — never asserts an unproven causal link.

intent.md: "Never claim an order hold was caused by an overdue invoice
unless a source record establishes that link." This module only reports
recorded facts; cause inference is explicitly out of scope.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class HoldPresentation:
    is_active: bool
    hold_reason: str
    age_days: int | None  # None if released
    linked_invoice_id: str | None  # only set if a source record explicitly links one


def present_hold(
    status: str,
    hold_reason: str,
    applied_date: date,
    released_date: date | None,
    linked_invoice_id: str | None,
    as_of: date,
) -> HoldPresentation:
    is_active = status == "active" and released_date is None
    age_days = (as_of - applied_date).days if is_active else None
    return HoldPresentation(
        is_active=is_active,
        hold_reason=hold_reason,
        age_days=age_days,
        linked_invoice_id=linked_invoice_id,
    )
