"""Admin user/business-unit management endpoints, exercised through the
real FastAPI app (auth dependency overridden to the test's own admin
`AppUser`, DB dependency overridden to the shared live-Postgres test
session) -- this hits the actual route code, not a duplicate of its logic.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.db import get_session
from revenueflowai.main import app
from revenueflowai.models.tenancy import AppUser

pytestmark = pytest.mark.asyncio


@pytest.fixture
def admin_client(db_session, tenant):
    _org, _bu, admin_user = tenant

    async def _get_session_override():
        yield db_session

    async def _get_current_app_user_override() -> AppUser:
        return admin_user

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_current_app_user] = _get_current_app_user_override
    try:
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    finally:
        app.dependency_overrides.clear()


async def test_list_business_units_returns_the_tenants_bu(admin_client, tenant):
    _org, bu, _user = tenant
    async with admin_client as client:
        response = await client.get("/api/v1/admin/business-units")
    assert response.status_code == 200
    body = response.json()
    assert any(row["id"] == str(bu.id) for row in body)


async def test_create_user_then_list_includes_it(admin_client, tenant):
    _org, bu, _admin_user = tenant
    subject = f"new-subject-{uuid.uuid4().hex[:8]}"
    async with admin_client as client:
        create_response = await client.post(
            "/api/v1/admin/users",
            json={
                "oidc_subject": subject,
                "email": f"{subject}@example.test",
                "display_name": "New Analyst",
                "role": "analyst",
                "business_unit_ids": [str(bu.id)],
            },
        )
        assert create_response.status_code == 201, create_response.text
        created = create_response.json()
        assert created["role"] == "analyst"
        assert created["granted_business_unit_ids"] == [str(bu.id)]

        list_response = await client.get("/api/v1/admin/users")
        assert list_response.status_code == 200
        assert any(row["oidc_subject"] == subject for row in list_response.json())


async def test_create_user_with_duplicate_subject_conflicts(admin_client, tenant):
    _org, _bu, admin_user = tenant
    async with admin_client as client:
        response = await client.post(
            "/api/v1/admin/users",
            json={
                "oidc_subject": admin_user.oidc_subject,
                "email": "duplicate@example.test",
                "display_name": "Duplicate",
                "role": "viewer",
            },
        )
    assert response.status_code == 409


async def test_create_user_with_invalid_role_is_rejected(admin_client):
    async with admin_client as client:
        response = await client.post(
            "/api/v1/admin/users",
            json={
                "oidc_subject": f"bad-role-{uuid.uuid4().hex[:8]}",
                "email": "bad-role@example.test",
                "display_name": "Bad Role",
                "role": "superuser",
            },
        )
    assert response.status_code == 400


async def test_update_user_role_and_grants(admin_client, tenant):
    _org, bu, _admin_user = tenant
    subject = f"update-subject-{uuid.uuid4().hex[:8]}"
    async with admin_client as client:
        create_response = await client.post(
            "/api/v1/admin/users",
            json={
                "oidc_subject": subject, "email": f"{subject}@example.test",
                "display_name": "To Update", "role": "viewer",
            },
        )
        user_id = create_response.json()["id"]

        update_response = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"role": "approver", "business_unit_ids": [str(bu.id)]},
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["role"] == "approver"
        assert updated["granted_business_unit_ids"] == [str(bu.id)]


async def test_update_unknown_user_returns_404(admin_client):
    async with admin_client as client:
        response = await client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}", json={"role": "viewer"}
        )
    assert response.status_code == 404


async def test_non_admin_role_is_rejected(db_session, tenant):
    _org, _bu, admin_user = tenant
    admin_user.role = "viewer"

    async def _get_session_override():
        yield db_session

    async def _get_current_app_user_override() -> AppUser:
        return admin_user

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_current_app_user] = _get_current_app_user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
