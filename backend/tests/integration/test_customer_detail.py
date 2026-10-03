"""Customer detail/timeline, verified against live Postgres using the real
generated small bundle. S01-CUST has exactly one invoice (balance 600 after
a 300 receipt + 100 credit application, per synthetic_data_requirements.md),
which this test's expected values are transcribed from directly -- not
computed by the code under test.
"""

import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from revenueflowai.domain.customer_service import compute_customer_detail
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)

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


async def test_customer_detail_matches_s01_hand_calculation(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)

    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="customer-detail-test",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)

    detail = await compute_customer_detail(db_session, org.id, bu.id, "S01-CUST", AS_OF)

    assert detail is not None
    assert detail.customer_external_id == "S01-CUST"
    assert detail.account_number == "ACC-S01"

    assert len(detail.invoices) == 1
    invoice = detail.invoices[0]
    assert invoice.invoice_external_id == "S01-INV-1000"
    assert invoice.invoice_amount == Decimal("1000.00")
    assert invoice.open_balance == Decimal("600.00")
    assert invoice.aging_bucket == "31-60"

    # Timeline includes the invoice and the receipt real events, chronologically ordered.
    event_types = [e.event_type for e in detail.timeline]
    assert "invoice" in event_types
    assert "receipt" in event_types
    dates = [e.event_date for e in detail.timeline]
    assert dates == sorted(dates)

    # One credit memo was applied against this invoice.
    assert len(detail.credit_memos) == 1
    assert detail.credit_memos[0].invoice_external_id == "S01-INV-1000"


async def test_customer_detail_returns_none_for_unknown_customer(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)

    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="customer-detail-unknown",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)

    detail = await compute_customer_detail(db_session, org.id, bu.id, "NOT-A-REAL-CUSTOMER", AS_OF)
    assert detail is None


async def test_customer_detail_with_no_active_dataset_returns_none(db_session, tenant):
    org, bu, _user = tenant
    detail = await compute_customer_detail(db_session, org.id, bu.id, "S01-CUST", AS_OF)
    assert detail is None
