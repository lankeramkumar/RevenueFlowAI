"""SQL-backed aging summary, verified against live Postgres using the real
generated small bundle — expected values transcribed directly from
synthetic_data_requirements.md's scenario ledger. The bundle now contains
16 scenarios sharing currency/bucket combinations, so assertions check
"at least" the S01/S09 contribution rather than an exact bucket total
(test_all_scenarios.py covers the other scenarios individually via
specific record lookups, not aggregate totals).
"""

import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from revenueflowai.domain.services import compute_aging_summary
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


async def test_aging_summary_matches_s01_s09_hand_calculation(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)

    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="aging-test",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)

    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)

    assert summary.dataset_version_id is not None
    # S01: invoice 1000, due D-45, effective applications 300+100 -> balance 600, bucket 31-60
    assert summary.totals_by_currency_bucket["USD"]["31-60"] >= Decimal("600.00")
    # S09: USD invoice 100 due D-5 -> bucket 1-30; EUR invoice 200 due D-5 -> bucket 1-30, separate currency
    assert summary.totals_by_currency_bucket["USD"]["1-30"] >= Decimal("100.00")
    assert summary.totals_by_currency_bucket["EUR"]["1-30"] == Decimal("200.00")  # only S09 uses EUR
    # Currencies are never combined into one total; no scenario uses a third currency.
    assert "USD" in summary.totals_by_currency_bucket
    assert "EUR" in summary.totals_by_currency_bucket
    assert set(summary.totals_by_currency_bucket.keys()) == {"USD", "EUR"}


async def test_aging_summary_with_no_active_dataset_returns_empty(db_session, tenant):
    org, bu, _user = tenant
    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)

    assert summary.dataset_version_id is None
    assert summary.totals_by_currency_bucket == {}
