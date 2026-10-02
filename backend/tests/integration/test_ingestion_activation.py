"""End-to-end ingestion tests against a real Postgres: generate the small
bundle, activate it, verify rows landed with correct scope/lineage, verify
idempotent replay doesn't duplicate, and verify an invalid bundle is
rejected without touching the previously active dataset.
"""

import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)
from revenueflowai.models.entities import Invoice
from revenueflowai.models.ingestion import DatasetVersion

pytestmark = pytest.mark.asyncio


def _generate_small_bundle(tmp_path: Path) -> Path:
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [
            sys.executable, "-m", "revenueflowai.seed", "generate",
            "--profile", "small", "--seed", "42", "--as-of", "2026-10-02",
            "--output", str(out_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_dir


async def test_valid_bundle_activates_and_loads_rows(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)
    bundle_hash = compute_bundle_hash(bundle_dir)

    job, was_existing = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="upload-1", bundle_hash=bundle_hash
    )
    assert not was_existing

    outcome = await validate_and_activate(db_session, job, bundle_dir, snapshot_date=date(2026, 10, 2))

    assert outcome.validation.is_valid
    assert outcome.dataset_version is not None
    assert outcome.dataset_version.is_active is True
    assert job.status == "activated"
    assert outcome.row_counts["invoices.csv"] == 3  # S01 + S09 (2 invoices)

    invoice_count = (
        await db_session.execute(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.dataset_version_id == outcome.dataset_version.id)
        )
    ).scalar_one()
    assert invoice_count == 3

    s01_invoice = (
        await db_session.execute(
            select(Invoice).where(
                Invoice.dataset_version_id == outcome.dataset_version.id,
                Invoice.external_id == "S01-INV-1000",
            )
        )
    ).scalar_one()
    assert s01_invoice.invoice_amount == Decimal("1000.00")
    assert s01_invoice.organization_id == org.id
    assert s01_invoice.business_unit_id == bu.id
    assert s01_invoice.source_filename == "invoices.csv"


async def test_repeated_upload_is_idempotent(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)
    bundle_hash = compute_bundle_hash(bundle_dir)

    job1, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="same-key", bundle_hash=bundle_hash
    )
    await validate_and_activate(db_session, job1, bundle_dir, snapshot_date=date(2026, 10, 2))

    job2, was_existing = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="same-key", bundle_hash=bundle_hash
    )
    assert was_existing
    assert job2.id == job1.id

    outcome2 = await validate_and_activate(db_session, job2, bundle_dir, snapshot_date=date(2026, 10, 2))
    assert outcome2.was_idempotent_replay

    active_versions = (
        await db_session.execute(
            select(func.count()).select_from(DatasetVersion).where(
                DatasetVersion.organization_id == org.id,
                DatasetVersion.business_unit_id == bu.id,
                DatasetVersion.is_active.is_(True),
            )
        )
    ).scalar_one()
    assert active_versions == 1  # no duplicate dataset version from the replay


async def test_invalid_bundle_is_rejected_without_touching_active_dataset(db_session, tenant, tmp_path):
    org, bu, user = tenant
    valid_bundle = _generate_small_bundle(tmp_path / "valid")

    first_job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="valid-upload",
        bundle_hash=compute_bundle_hash(valid_bundle),
    )
    first_outcome = await validate_and_activate(
        db_session, first_job, valid_bundle, snapshot_date=date(2026, 10, 2)
    )
    active_version_id = first_outcome.dataset_version.id

    # Break the bundle: delete customers.csv so orders.csv's FK is broken.
    invalid_bundle = tmp_path / "invalid"
    import shutil

    shutil.copytree(valid_bundle, invalid_bundle)
    (invalid_bundle / "customers.csv").write_text(
        "customer_id,account_number,customer_name,payment_terms_days\n"
    )

    second_job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="invalid-upload",
        bundle_hash=compute_bundle_hash(invalid_bundle),
    )
    second_outcome = await validate_and_activate(
        db_session, second_job, invalid_bundle, snapshot_date=date(2026, 10, 3)
    )

    assert not second_outcome.validation.is_valid
    assert second_job.status == "rejected"
    assert second_outcome.dataset_version is None

    still_active = (
        await db_session.execute(
            select(DatasetVersion).where(
                DatasetVersion.organization_id == org.id,
                DatasetVersion.business_unit_id == bu.id,
                DatasetVersion.is_active.is_(True),
            )
        )
    ).scalar_one()
    assert still_active.id == active_version_id  # unchanged
