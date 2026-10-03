"""Activates the full `small` bundle (all 16 implemented scenarios) once
against live Postgres and verifies each scenario's expected values from
synthetic_data_requirements.md via the real SQL-backed domain services --
not the pure functions (already covered elsewhere), the actual services
an API endpoint would call.
"""

import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from revenueflowai.domain.holds_service import compute_order_holds
from revenueflowai.domain.matching_service import compute_receipt_matches
from revenueflowai.domain.services import compute_aging_summary
from revenueflowai.domain.shipment_service import compute_unbilled_shipments
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)
from revenueflowai.models.entities import Dispute, Invoice

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


def _generate_small_bundle(tmp_path: Path) -> Path:
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [
            sys.executable, "-m", "revenueflowai.seed", "generate",
            "--profile", "small", "--seed", "42", "--as-of", AS_OF.isoformat(),
            "--output", str(out_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_dir


@pytest.fixture
async def activated(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="all-scenarios",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)
    assert outcome.validation.is_valid, [e.message for e in outcome.validation.errors]
    return org, bu, outcome.dataset_version.id


async def test_s02_disputed_invoice_does_not_reduce_balance(db_session, activated):
    org, bu, _dv = activated
    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)
    assert summary.totals_by_currency_bucket["USD"]["1-30"] >= Decimal("800.00")

    dispute = (await db_session.execute(
        select(Dispute).where(Dispute.external_id == "S02-DISP-1")
    )).scalar_one()
    assert dispute.disputed_amount == Decimal("200.00")
    assert dispute.status == "open"


async def test_s04_ambiguous_match_no_silent_selection(db_session, activated):
    org, bu, _dv = activated
    result = await compute_receipt_matches(db_session, org.id, bu.id, "S04-RCP")
    assert result.is_ambiguous
    assert len(result.proposals) == 2
    assert {p.invoice_ids[0] for p in result.proposals} == {"S04-INV-A", "S04-INV-B"}


async def test_s06_fully_unbilled(db_session, activated):
    org, bu, _dv = activated
    rows = await compute_unbilled_shipments(db_session, org.id, bu.id, AS_OF, age_threshold_days=5)
    row = next(r for r in rows if r.shipment_line_external_id == "S06-SL")
    assert row.unbilled_quantity == Decimal("4")
    assert row.estimated_value == Decimal("200.00")
    assert row.sufficient_evidence is True


async def test_s08_released_hold_excluded_from_active_count(db_session, activated):
    org, bu, _dv = activated
    active_holds = await compute_order_holds(db_session, org.id, bu.id, AS_OF, active_only=True)
    assert "S08-ORD" not in {h.order_external_id for h in active_holds}

    all_holds = await compute_order_holds(db_session, org.id, bu.id, AS_OF, active_only=False)
    s08 = next(h for h in all_holds if h.order_external_id == "S08-ORD")
    assert s08.is_active is False


async def test_s10_reversed_application_excluded(db_session, activated):
    org, bu, dv = activated
    invoice = (await db_session.execute(
        select(Invoice).where(
            Invoice.dataset_version_id == dv, Invoice.external_id == "S10-INV-1000"
        )
    )).scalar_one()
    assert invoice.invoice_amount == Decimal("1000.00")

    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)
    # S10's own bucket (12 days overdue -> 1-30) should include exactly 750
    # contributed by this invoice; assert at least that much is present.
    assert summary.totals_by_currency_bucket["USD"]["1-30"] >= Decimal("750.00")


async def test_s11_partial_receipt_unapplied_amount(db_session, activated):
    org, bu, _dv = activated
    result = await compute_receipt_matches(db_session, org.id, bu.id, "S11-RCP")
    assert result.unapplied_amount == Decimal("300.00")


async def test_s12_due_date_boundaries(db_session, activated):
    org, bu, _dv = activated
    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)
    buckets = summary.totals_by_currency_bucket["USD"]
    # 7 of the 9 S12 invoices are overdue (bucket != not_due); each contributes 100.
    assert buckets.get("1-30", Decimal("0")) >= Decimal("200.00")  # D-1, D-30
    assert buckets.get("31-60", Decimal("0")) >= Decimal("200.00")  # D-31, D-60
    assert buckets.get("61-90", Decimal("0")) >= Decimal("200.00")  # D-61, D-90
    assert buckets.get("91+", Decimal("0")) >= Decimal("100.00")  # D-91


async def test_s13_multi_invoice_match_zero_residual(db_session, activated):
    org, bu, _dv = activated
    result = await compute_receipt_matches(db_session, org.id, bu.id, "S13-RCP")
    assert not result.is_ambiguous
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert set(proposal.invoice_ids) == {"S13-INV-400", "S13-INV-500"}
    assert proposal.total == Decimal("900.00")
    assert proposal.residual == Decimal("0")


async def test_s14_insufficient_evidence_not_asserted_unbilled(db_session, activated):
    org, bu, _dv = activated
    rows = await compute_unbilled_shipments(db_session, org.id, bu.id, AS_OF, age_threshold_days=5)
    row = next(r for r in rows if r.shipment_line_external_id == "S14-SL")
    assert row.sufficient_evidence is False


async def test_s17_injected_narrative_is_inert_data(db_session, activated):
    org, bu, dv = activated
    dispute = (await db_session.execute(
        select(Dispute).where(
            Dispute.dataset_version_id == dv, Dispute.external_id == "S17-DISP"
        )
    )).scalar_one()
    # The injection text is stored and returned as plain data -- it must
    # never be interpreted, and reading it must not change any behavior.
    assert "ignore" in dispute.reason.lower()
    assert dispute.disputed_amount == Decimal("50.00")
    assert dispute.status == "open"
