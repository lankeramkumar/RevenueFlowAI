"""Unbilled-shipment exceptions against live Postgres.

Small profile: S05 (8 shipped, 5 billed -> 3 unbilled, 300.00), S06 (4 shipped,
none billed -> 4 unbilled, 200.00), S14 (no order-line link -> insufficient
evidence). Expected values are transcribed from synthetic_data_requirements.md.

Demo profile: every shipment line is fully billed or below the age threshold,
so the exception list must be empty -- fully billed lines are not exceptions.
"""

import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from revenueflowai.domain.shipment_service import compute_unbilled_shipments
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


def _generate(profile: str, out_dir: Path) -> Path:
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", profile,
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_dir


async def _activate(db_session, tenant, bundle_dir: Path) -> None:
    org, bu, user = tenant
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=f"unbilled-{uuid.uuid4().hex[:8]}",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)
    assert outcome.validation.is_valid


async def test_small_profile_unbilled_exceptions_match_hand_calculation(db_session, tenant, tmp_path):
    org, bu, _user = tenant
    await _activate(db_session, tenant, _generate("small", tmp_path / "small"))

    rows = await compute_unbilled_shipments(db_session, org.id, bu.id, AS_OF, age_threshold_days=5)
    by_line = {r.shipment_line_external_id: r for r in rows}

    assert by_line["S05-SL"].unbilled_quantity == Decimal("3")
    assert by_line["S05-SL"].estimated_value == Decimal("300.00")
    assert by_line["S06-SL"].unbilled_quantity == Decimal("4")
    assert by_line["S06-SL"].estimated_value == Decimal("200.00")
    assert by_line["S14-SL"].sufficient_evidence is False


async def test_fully_billed_lines_are_never_reported_as_exceptions(db_session, tenant, tmp_path):
    org, bu, _user = tenant
    await _activate(db_session, tenant, _generate("demo", tmp_path / "demo"))

    rows = await compute_unbilled_shipments(db_session, org.id, bu.id, AS_OF, age_threshold_days=5)
    assert [r for r in rows if r.sufficient_evidence and r.unbilled_quantity <= 0] == []
