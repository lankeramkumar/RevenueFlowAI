"""Scenario fixtures against activated data. Every expected value below is
transcribed from the scenario builders' `expected` blocks in
src/revenueflowai/seed/scenarios.py (which mirror synthetic_data_requirements.md),
then compared with what the SQL-backed domain services compute from the
activated small bundle. Scenarios with no domain service yet (S16 staleness
display, S15 cross-org) are covered elsewhere and noted in the report.
"""

import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from revenueflowai.domain.customer_service import compute_customer_detail
from revenueflowai.domain.holds_service import compute_order_holds
from revenueflowai.domain.matching_service import compute_receipt_matches
from revenueflowai.domain.services import compute_aging_summary, get_active_dataset_version
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)
from revenueflowai.models.entities import Dispute

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


async def _activate_small(db_session, tenant, tmp_path: Path):
    org, bu, user = tenant
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", "small",
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=f"scenarios-{uuid.uuid4().hex[:8]}",
        bundle_hash=compute_bundle_hash(out_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, out_dir, snapshot_date=AS_OF)
    assert outcome.validation.is_valid, [e.message for e in outcome.validation.errors]


async def _invoice(db_session, org, bu, customer: str, invoice_id: str):
    detail = await compute_customer_detail(db_session, org.id, bu.id, customer, AS_OF)
    assert detail is not None, customer
    return next(i for i in detail.invoices if i.invoice_external_id == invoice_id)


async def test_scenario_expectations_match_activated_domain_output(db_session, tenant, tmp_path):
    org, bu, _user = tenant
    await _activate_small(db_session, tenant, tmp_path)

    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)
    assert "S01-INV-1000" in summary.invoices_by_currency_bucket["USD"]["31-60"]
    assert summary.invoices_by_currency_bucket["EUR"]["1-30"] == ["S09-INV-EUR"]

    # S02: disputed invoice; the dispute annotates but does not reduce the balance.
    s02 = await _invoice(db_session, org, bu, "S02-CUST", "S02-INV-800")
    assert s02.open_balance == Decimal("800.00")
    assert s02.aging_bucket == "1-30"
    dv = await get_active_dataset_version(db_session, org.id, bu.id)
    dispute = (await db_session.execute(select(Dispute).where(
        Dispute.dataset_version_id == dv.id, Dispute.invoice_external_id == "S02-INV-800"
    ))).scalar_one()
    assert dispute.disputed_amount == Decimal("200.00")

    # S03: exact receipt match on the remittance reference.
    s03 = await compute_receipt_matches(db_session, org.id, bu.id, "S03-RCP")
    assert s03.unapplied_amount == Decimal("600.00")
    assert not s03.is_ambiguous
    assert any(p.invoice_ids == ("S03-INV-600",) and p.is_exact for p in s03.proposals)

    # S04: two equal candidates -> ambiguity is reported, never silently chosen.
    s04 = await compute_receipt_matches(db_session, org.id, bu.id, "S04-RCP")
    assert s04.unapplied_amount == Decimal("500.00")
    assert s04.is_ambiguous

    # S07 / S08: active hold reported with its recorded reason; released hold excluded.
    active = await compute_order_holds(db_session, org.id, bu.id, AS_OF, active_only=True)
    s07 = next(h for h in active if h.order_external_id == "S07-ORD")
    assert s07.hold_reason == "MISSING_SHIP_TO"
    assert s07.is_active is True
    assert s07.linked_invoice_id is None
    assert all(h.order_external_id != "S08-ORD" for h in active)

    # S10: reversed application is excluded from the open balance.
    s10 = await _invoice(db_session, org, bu, "S10-CUST", "S10-INV-1000")
    assert s10.open_balance == Decimal("750.00")

    # S11: partial receipt leaves 300.00 unapplied on the receipt.
    s11 = await compute_receipt_matches(db_session, org.id, bu.id, "S11-RCP")
    assert s11.unapplied_amount == Decimal("300.00")

    # S12: due-date boundaries -- days overdue and aging bucket per invoice.
    detail = await compute_customer_detail(db_session, org.id, bu.id, "S12-CUST", AS_OF)
    expected_buckets = {
        "S12-INV-0": "not_due", "S12-INV-1": "not_due", "S12-INV-2": "1-30", "S12-INV-3": "1-30",
        "S12-INV-4": "31-60", "S12-INV-5": "31-60", "S12-INV-6": "61-90", "S12-INV-7": "61-90",
        "S12-INV-8": "91+",
    }
    actual_buckets = {i.invoice_external_id: i.aging_bucket for i in detail.invoices}
    assert actual_buckets == expected_buckets

    # S13: exact two-invoice combination with zero residual.
    s13 = await compute_receipt_matches(db_session, org.id, bu.id, "S13-RCP")
    assert s13.unapplied_amount == Decimal("900.00")
    assert any(
        set(p.invoice_ids) == {"S13-INV-400", "S13-INV-500"} and p.total == Decimal("900.00")
        and p.residual == Decimal("0.00")
        for p in s13.proposals
    )

    # S17: injected narrative text is data; the dispute amount is still computed normally.
    dispute_17 = (await db_session.execute(select(Dispute).where(
        Dispute.dataset_version_id == dv.id, Dispute.invoice_external_id == "S17-INV"
    ))).scalar_one()
    assert dispute_17.disputed_amount == Decimal("50.00")
