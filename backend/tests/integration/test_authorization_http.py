"""Cross-org/cross-business-unit authorization, repeated at the HTTP/API
layer specifically -- test_authorization_scope.py already proves this at
the domain-service layer; this file hits the real FastAPI app (auth/DB
dependencies overridden to the test's own session, same pattern as
test_admin_users.py) so the actual route + `assert_business_unit_access`
wiring is exercised, not just the service function underneath it.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.db import get_session
from revenueflowai.main import app
from revenueflowai.models.entities import Customer, Invoice
from revenueflowai.models.ingestion import DatasetVersion, ImportJob
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


async def _make_org_with_dataset(db_session, suffix: str, role: str = "admin"):
    org = Organization(name=f"HTTP Org {suffix}", slug=f"http-org-{suffix}-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    bu = BusinessUnit(organization_id=org.id, code="BU1", name="Business Unit 1")
    db_session.add(bu)
    await db_session.flush()

    user = AppUser(
        oidc_subject=f"http-subj-{suffix}-{uuid.uuid4().hex[:8]}", email=f"http-{suffix}@example.test",
        display_name=suffix, role=role, organization_id=org.id,
    )
    db_session.add(user)
    await db_session.flush()

    job = ImportJob(
        organization_id=org.id, business_unit_id=bu.id, created_by_user_id=user.id,
        idempotency_key=f"http-authz-{suffix}-{uuid.uuid4().hex[:8]}", bundle_hash="deadbeef",
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

    amount = Decimal("12345.00") if suffix == "A" else Decimal("99999.00")
    db_session.add(Invoice(
        external_id=f"HTTP-INV-{suffix}", customer_external_id=f"HTTP-CUST-{suffix}",
        invoice_date=AS_OF - timedelta(days=10), due_date=AS_OF - timedelta(days=1),
        currency="USD", invoice_amount=amount, status="posted",
        organization_id=org.id, business_unit_id=bu.id, dataset_version_id=dv.id,
        import_job_id=job.id, source_filename="t.csv", source_row_number=1,
    ))
    db_session.add(Customer(
        external_id=f"HTTP-CUST-{suffix}", customer_name=f"Customer {suffix}",
        organization_id=org.id, business_unit_id=bu.id, dataset_version_id=dv.id,
        import_job_id=job.id, source_filename="t.csv", source_row_number=1,
    ))
    await db_session.flush()

    return org, bu, user, amount


async def _override_app(db_session, acting_user: AppUser) -> None:
    # Mirrors the real get_current_app_user dependency's eager load --
    # assert_business_unit_access reads granted_business_units synchronously
    # for non-admin roles, which would otherwise raise MissingGreenlet.
    loaded = (
        await db_session.execute(
            select(AppUser)
            .options(selectinload(AppUser.granted_business_units))
            .where(AppUser.id == acting_user.id)
        )
    ).scalar_one()

    async def _get_session_override():
        yield db_session

    async def _get_current_app_user_override() -> AppUser:
        return loaded

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_current_app_user] = _get_current_app_user_override


async def test_viewer_without_grant_gets_403_on_another_orgs_business_unit(db_session):
    org_a, bu_a, _user_a, _amount_a = await _make_org_with_dataset(db_session, "VA")
    org_b, _bu_b, user_b, _amount_b = await _make_org_with_dataset(db_session, "VB", role="viewer")
    # user_b has no grant at all on bu_a -- different organization entirely.

    await _override_app(db_session, user_b)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/dashboard/aging-summary?business_unit_id={bu_a.id}&as_of={AS_OF.isoformat()}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "business_unit_not_granted"


async def test_admin_from_org_b_sees_no_data_for_org_as_business_unit(db_session):
    """Admins bypass the explicit grant check (they're scoped to their whole
    org), but the underlying query still requires organization_id AND
    business_unit_id to match the SAME tenant -- so org B's admin querying
    org A's business_unit_id must get back "no active dataset", never org
    A's real numbers.
    """
    org_a, bu_a, _user_a, amount_a = await _make_org_with_dataset(db_session, "AA")
    _org_b, _bu_b, user_b, _amount_b = await _make_org_with_dataset(db_session, "AB", role="admin")

    await _override_app(db_session, user_b)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/dashboard/aging-summary?business_unit_id={bu_a.id}&as_of={AS_OF.isoformat()}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_version_id"] is None
    assert body["totals_by_currency_bucket"] == {}
    # Sanity: org A's real amount never appears anywhere in the response.
    assert str(amount_a) not in response.text


async def test_customer_detail_cross_org_lookup_returns_404_not_someone_elses_customer(db_session):
    org_a, bu_a, _user_a, _amount_a = await _make_org_with_dataset(db_session, "CA")
    _org_b, _bu_b, user_b, _amount_b = await _make_org_with_dataset(db_session, "CB", role="admin")

    await _override_app(db_session, user_b)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/customers/HTTP-CUST-CA?business_unit_id={bu_a.id}&as_of={AS_OF.isoformat()}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


async def test_admin_endpoints_only_ever_see_the_callers_own_organization(db_session):
    org_a, bu_a, _user_a, _ = await _make_org_with_dataset(db_session, "DA")
    _org_b, _bu_b, user_b, _ = await _make_org_with_dataset(db_session, "DB", role="admin")

    await _override_app(db_session, user_b)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            bu_response = await client.get("/api/v1/admin/business-units")
            users_response = await client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert bu_response.status_code == 200
    assert all(row["id"] != str(bu_a.id) for row in bu_response.json())

    assert users_response.status_code == 200
    assert all(row["email"] != "http-DA@example.test" for row in users_response.json())
