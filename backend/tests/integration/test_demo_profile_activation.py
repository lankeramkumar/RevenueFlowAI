"""Demo profile activated for real against live Postgres, including the
"second organization/business unit for isolation tests" property from
synthetic_data_requirements.md: the same bundle uploaded into two
different organizations must never leak between them.
"""

import csv
from datetime import date

import pytest

from revenueflowai.domain.services import compute_aging_summary
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)
from revenueflowai.models.entities import Customer
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization
from revenueflowai.seed.demo import generate_demo_bundle
from revenueflowai.seed.schema import CSV_COLUMNS

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


def _write_demo_bundle(out_dir) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = generate_demo_bundle(seed=42, as_of=AS_OF)
    for filename, columns in CSV_COLUMNS.items():
        with (out_dir / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in bundle.rows.get(filename, []):
                writer.writerow(row)


async def _make_tenant(db_session, suffix: str):
    import uuid

    org = Organization(name=f"Demo Org {suffix}", slug=f"demo-org-{suffix}-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    bu = BusinessUnit(organization_id=org.id, code="BU1", name="Business Unit 1")
    db_session.add(bu)
    await db_session.flush()
    user = AppUser(
        oidc_subject=f"demo-subj-{suffix}-{uuid.uuid4().hex[:8]}", email=f"demo-{suffix}@example.test",
        display_name=suffix, role="admin", organization_id=org.id,
    )
    db_session.add(user)
    await db_session.flush()
    return org, bu, user


async def test_demo_bundle_activates_with_real_row_counts(db_session, tmp_path):
    org, bu, user = await _make_tenant(db_session, "A")
    bundle_dir = tmp_path / "demo"
    _write_demo_bundle(bundle_dir)

    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="demo-activate",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)

    assert outcome.validation.is_valid, [e.message for e in outcome.validation.errors]
    assert outcome.row_counts["customers.csv"] >= 30
    assert outcome.row_counts["orders.csv"] >= 200

    summary = await compute_aging_summary(db_session, org.id, bu.id, AS_OF)
    # Real demo data has open balances in both currencies somewhere.
    assert "USD" in summary.totals_by_currency_bucket or "EUR" in summary.totals_by_currency_bucket


async def test_demo_bundle_isolated_across_two_organizations(db_session, tmp_path):
    """The same bundle, uploaded into two different real organizations,
    must never let one see the other's rows -- even though the external
    customer IDs are identical strings in both uploads.
    """
    bundle_dir = tmp_path / "demo"
    _write_demo_bundle(bundle_dir)
    bundle_hash = compute_bundle_hash(bundle_dir)

    org_a, bu_a, user_a = await _make_tenant(db_session, "Iso1")
    job_a, _ = await get_or_create_import_job(
        db_session, org_a.id, bu_a.id, user_a.id, idempotency_key="demo-iso-a",
        bundle_hash=bundle_hash, snapshot_date=AS_OF,
    )
    outcome_a = await validate_and_activate(db_session, job_a, bundle_dir, snapshot_date=AS_OF)
    assert outcome_a.validation.is_valid

    org_b, bu_b, user_b = await _make_tenant(db_session, "Iso2")
    job_b, _ = await get_or_create_import_job(
        db_session, org_b.id, bu_b.id, user_b.id, idempotency_key="demo-iso-b",
        bundle_hash=bundle_hash, snapshot_date=AS_OF,
    )
    outcome_b = await validate_and_activate(db_session, job_b, bundle_dir, snapshot_date=AS_OF)
    assert outcome_b.validation.is_valid

    from sqlalchemy import select

    customers_a = (await db_session.execute(
        select(Customer).where(Customer.organization_id == org_a.id, Customer.external_id == "DEMO-CUST-001")
    )).scalars().all()
    customers_b = (await db_session.execute(
        select(Customer).where(Customer.organization_id == org_b.id, Customer.external_id == "DEMO-CUST-001")
    )).scalars().all()

    assert len(customers_a) == 1
    assert len(customers_b) == 1
    assert customers_a[0].id != customers_b[0].id  # same external_id, genuinely different rows
    assert customers_a[0].dataset_version_id != customers_b[0].dataset_version_id

    summary_a = await compute_aging_summary(db_session, org_a.id, bu_a.id, AS_OF)
    summary_b = await compute_aging_summary(db_session, org_b.id, bu_b.id, AS_OF)
    # Scoping org_b's query with org_a's business_unit_id must find nothing.
    cross_scoped = await compute_aging_summary(db_session, org_b.id, bu_a.id, AS_OF)
    assert cross_scoped.dataset_version_id is None
    assert summary_a.dataset_version_id is not None
    assert summary_b.dataset_version_id is not None
