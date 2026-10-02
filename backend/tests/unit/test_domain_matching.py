"""S03, S04, S13 — exact, ambiguous, and bounded multi-invoice receipt matches."""

from decimal import Decimal

from revenueflowai.domain.matching import InvoiceCandidate, find_receipt_matches


def test_s03_exact_receipt_match_with_remittance_reference():
    candidates = [InvoiceCandidate("INV-ONLY", Decimal("600"))]
    result = find_receipt_matches(
        Decimal("600"), candidates, remittance_referenced_invoice_ids=frozenset({"INV-ONLY"})
    )

    assert not result.is_ambiguous
    assert len(result.proposals) == 1
    assert result.proposals[0].invoice_ids == ("INV-ONLY",)
    assert result.proposals[0].evidence == "remittance_reference"


def test_s04_ambiguous_match_no_silent_selection():
    candidates = [InvoiceCandidate("INV-A", Decimal("500")), InvoiceCandidate("INV-B", Decimal("500"))]
    result = find_receipt_matches(Decimal("500"), candidates)

    assert result.is_ambiguous
    assert len(result.proposals) == 2
    assert {p.invoice_ids[0] for p in result.proposals} == {"INV-A", "INV-B"}


def test_s13_multi_invoice_match_totals_with_zero_residual():
    candidates = [
        InvoiceCandidate("INV-400", Decimal("400")),
        InvoiceCandidate("INV-500", Decimal("500")),
        InvoiceCandidate("INV-999", Decimal("999")),  # decoy, shouldn't be selected
    ]
    result = find_receipt_matches(
        Decimal("900"), candidates,
        remittance_referenced_invoice_ids=frozenset({"INV-400", "INV-500"}),
    )

    assert not result.is_ambiguous
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert set(proposal.invoice_ids) == {"INV-400", "INV-500"}
    assert proposal.total == Decimal("900")
    assert proposal.residual == Decimal("0")


def test_no_match_returns_empty_proposals():
    candidates = [InvoiceCandidate("INV-A", Decimal("123"))]
    result = find_receipt_matches(Decimal("999"), candidates)

    assert result.proposals == []
    assert not result.is_ambiguous
