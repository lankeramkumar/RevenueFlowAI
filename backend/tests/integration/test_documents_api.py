"""Document upload, read, and download through the real app against the local
object store (LocalStack) and live Postgres.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.config import get_settings
from revenueflowai.db import get_session
from revenueflowai.main import app
from revenueflowai.models.ingestion import AuditEvent
from revenueflowai.models.tenancy import AppUser
from revenueflowai.storage.s3_store import S3CompatibleObjectStore

pytestmark = pytest.mark.asyncio


async def _ensure_bucket() -> None:
    await S3CompatibleObjectStore().ensure_bucket(get_settings().s3_bucket_documents)


def _client_as(db_session, acting_user_id, loaded_user_holder: dict):
    async def _session_override():
        yield db_session

    async def _user_override():
        return loaded_user_holder["user"]

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_app_user] = _user_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _load(db_session, user_id) -> AppUser:
    return (await db_session.execute(
        select(AppUser).options(selectinload(AppUser.granted_business_units)).where(AppUser.id == user_id)
    )).scalar_one()


async def test_txt_upload_is_listed_read_and_downloaded_byte_for_byte(db_session, tenant):
    await _ensure_bucket()
    org, bu, user = tenant
    holder = {"user": await _load(db_session, user.id)}
    body = b"Customer confirmed a partial payment of 300 on S01-INV-1000."
    try:
        async with _client_as(db_session, user.id, holder) as client:
            upload = await client.post(
                "/api/v1/documents",
                data={"business_unit_id": str(bu.id)},
                files={"file": ("remittance.txt", body, "text/plain")},
            )
            assert upload.status_code == 201, upload.text
            doc = upload.json()

            listed = await client.get(f"/api/v1/documents?business_unit_id={bu.id}")
            assert any(row["id"] == doc["id"] for row in listed.json())

            detail = await client.get(f"/api/v1/documents/{doc['id']}")
            assert "S01-INV-1000" in detail.json()["text"]

            download = await client.get(f"/api/v1/documents/{doc['id']}/content")
            assert download.status_code == 200
            assert download.content == body

            evidence = await client.get(f"/api/v1/evidence/document/{doc['id']}?business_unit_id={bu.id}")
            assert evidence.status_code == 200
            assert "S01-INV-1000" in evidence.json()["fields"]["text"]
    finally:
        app.dependency_overrides.clear()

    audit = (await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.subject_id == doc["id"], AuditEvent.event_type == "document.uploaded"
        )
    )).scalars().all()
    assert len(audit) == 1


async def test_unsupported_upload_is_rejected_with_a_reason(db_session, tenant):
    await _ensure_bucket()
    org, bu, user = tenant
    holder = {"user": await _load(db_session, user.id)}
    try:
        async with _client_as(db_session, user.id, holder) as client:
            response = await client.post(
                "/api/v1/documents",
                data={"business_unit_id": str(bu.id)},
                files={"file": ("tool.exe", b"MZ\x90\x00", "application/octet-stream")},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "unsupported_type"


async def test_document_from_another_organization_is_not_readable(db_session, tenant):
    await _ensure_bucket()
    org, bu, user = tenant
    holder = {"user": await _load(db_session, user.id)}
    try:
        async with _client_as(db_session, user.id, holder) as client:
            upload = await client.post(
                "/api/v1/documents",
                data={"business_unit_id": str(bu.id)},
                files={"file": ("private.txt", b"Confidential note for organization A.", "text/plain")},
            )
            doc_id = upload.json()["id"]
    finally:
        app.dependency_overrides.clear()

    from revenueflowai.models.tenancy import Organization

    other_org = Organization(name=f"Other {uuid.uuid4().hex[:8]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db_session.add(other_org)
    await db_session.flush()
    from revenueflowai.models.tenancy import BusinessUnit

    other_bu = BusinessUnit(organization_id=other_org.id, code="BU1", name="Other BU")
    db_session.add(other_bu)
    await db_session.flush()
    other_user = AppUser(
        oidc_subject=f"other-{uuid.uuid4().hex[:8]}", email=f"other-{uuid.uuid4().hex[:8]}@example.test",
        display_name="Other", role="admin", organization_id=other_org.id,
    )
    db_session.add(other_user)
    await db_session.flush()

    holder = {"user": await _load(db_session, other_user.id)}
    try:
        async with _client_as(db_session, other_user.id, holder) as client:
            detail = await client.get(f"/api/v1/documents/{doc_id}")
            download = await client.get(f"/api/v1/documents/{doc_id}/content")
    finally:
        app.dependency_overrides.clear()
    assert detail.status_code == 404
    assert download.status_code == 404
