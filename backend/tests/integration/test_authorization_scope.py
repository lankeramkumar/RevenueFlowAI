"""Cross-organization / cross-business-unit authorization: a user from one
organization must never see another organization's data, even when IDs are
known. intent.md: "Scope every API, tool, document lookup, export, object
access, and job to authorized organization/business units."
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from revenueflowai.domain.services import compute_aging_summary, get_active_dataset_version
from revenueflowai.models.entities import Invoice
from revenueflowai.models.ingestion import DatasetVersion, ImportJob
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


async def _make_org_with_dataset(db_session, suffix: str):
    org = Organization(name=f"Org {suffix}", slug=f"org-{suffix}-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    bu = BusinessUnit(organization_id=org.id, code="BU1", name="Business Unit 1")
    db_session.add(bu)
    await db_session.flush()

    user = AppUser(
        oidc_subject=f"subj-{suffix}-{uuid.uuid4().hex[:8]}", email=f"{suffix}@example.test",
        display_name=suffix, role="admin", organization_id=org.id,
    )
    db_session.add(user)
    await db_session.flush()

    job = ImportJob(
        organization_id=org.id, business_unit_id=bu.id, created_by_user_id=user.id,
        idempotency_key=f"authz-test-{suffix}", bundle_hash="deadbeef",
        snapshot_date=AS_OF, status="activated",
    )
    db_session.add(job)
    await db_session.flush()

    dv = DatasetVersion(
        organization_id=org.id, business_unit_id=bu.id,
        source_import_job_id=job.id, snapshot_date=AS_OF, is_active=True,
    )
    db_session.add(dv)
    await db_session.flush()

    # A distinctive invoice amount per org, so cross-org leakage would be obvious.
    amount = Decimal("12345.00") if suffix == "A" else Decimal("99999.00")
    db_session.add(Invoice(
        external_id=f"INV-{suffix}", customer_external_id=f"CUST-{suffix}",
        invoice_date=AS_OF - timedelta(days=10), due_date=AS_OF - timedelta(days=1),
        currency="USD", invoice_amount=amount, status="posted",
        organization_id=org.id, business_unit_id=bu.id, dataset_version_id=dv.id,
        import_job_id=job.id, source_filename="t.csv", source_row_number=1,
    ))
    await db_session.flush()

    return org, bu, user, amount


async def test_aging_summary_scoped_to_organization_never_leaks_another_orgs_data(db_session):
    org_a, bu_a, _user_a, amount_a = await _make_org_with_dataset(db_session, "A")
    org_b, bu_b, _user_b, amount_b = await _make_org_with_dataset(db_session, "B")

    summary_a = await compute_aging_summary(db_session, org_a.id, bu_a.id, AS_OF)
    summary_b = await compute_aging_summary(db_session, org_b.id, bu_b.id, AS_OF)

    total_a = sum(summary_a.totals_by_currency_bucket.get("USD", {}).values())
    total_b = sum(summary_b.totals_by_currency_bucket.get("USD", {}).values())

    assert total_a == amount_a
    assert total_b == amount_b
    assert total_a != total_b  # sanity: distinct fixtures, not accidentally identical


async def test_get_active_dataset_version_requires_matching_organization(db_session):
    """Even a forged/guessed business_unit_id from another organization
    must not resolve a dataset: the query requires organization_id AND
    business_unit_id to match the SAME tenant, not just the BU id alone.
    """
    org_a, bu_a, _user_a, _ = await _make_org_with_dataset(db_session, "C")
    org_b, _bu_b, _user_b, _ = await _make_org_with_dataset(db_session, "D")

    result = await get_active_dataset_version(db_session, org_b.id, bu_a.id)
    assert result is None
