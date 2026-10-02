"""Cash-match proposal rules — intent.md's "Cash match suggestions" section.

Candidates are limited to open invoices for the same customer/currency
(enforced by the caller's query, not here). This module only scores and
labels the candidate set it's given; it never applies a receipt.
"""

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations


@dataclass(frozen=True)
class InvoiceCandidate:
    invoice_id: str
    open_balance: Decimal


@dataclass(frozen=True)
class MatchProposal:
    invoice_ids: tuple[str, ...]
    total: Decimal
    residual: Decimal
    is_exact: bool
    evidence: str


@dataclass(frozen=True)
class MatchResult:
    proposals: list[MatchProposal]
    is_ambiguous: bool


MAX_COMBINATION_SIZE = 3
MAX_CANDIDATES_CONSIDERED = 20


def find_receipt_matches(
    receipt_amount: Decimal,
    candidates: list[InvoiceCandidate],
    remittance_referenced_invoice_ids: frozenset[str] = frozenset(),
) -> MatchResult:
    """Single-invoice exact matches first; bounded multi-invoice combinations
    if no single invoice matches exactly. Multiple equally plausible matches
    are returned together and flagged ambiguous rather than silently picking one.
    """
    bounded_candidates = candidates[:MAX_CANDIDATES_CONSIDERED]
    proposals: list[MatchProposal] = []

    for candidate in bounded_candidates:
        if candidate.open_balance == receipt_amount:
            evidence = (
                "remittance_reference" if candidate.invoice_id in remittance_referenced_invoice_ids
                else "exact_amount"
            )
            proposals.append(
                MatchProposal(
                    invoice_ids=(candidate.invoice_id,),
                    total=candidate.open_balance,
                    residual=Decimal("0"),
                    is_exact=True,
                    evidence=evidence,
                )
            )

    if not proposals:
        for size in range(2, MAX_COMBINATION_SIZE + 1):
            for combo in combinations(bounded_candidates, size):
                total = sum((c.open_balance for c in combo), start=Decimal("0"))
                if total == receipt_amount:
                    proposals.append(
                        MatchProposal(
                            invoice_ids=tuple(c.invoice_id for c in combo),
                            total=total,
                            residual=Decimal("0"),
                            is_exact=True,
                            evidence="multi_invoice_exact_sum",
                        )
                    )
            if proposals:
                break

    is_ambiguous = len(proposals) > 1
    return MatchResult(proposals=proposals, is_ambiguous=is_ambiguous)
