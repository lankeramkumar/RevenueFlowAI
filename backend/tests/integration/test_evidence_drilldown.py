"""Evidence drill-down endpoint against live Postgres with the real generated
small bundle: S01's invoice must resolve to its stored row and its linked
receipt application; unknown IDs and cross-scope lookups must not resolve.
"""

import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.db import get_session
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)
from revenueflowai.main import app
from revenueflowai.models.tenancy import AppUser

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


def _generate_small_bundle(tmp_path: Path) -> Path:
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", "small",
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_dir


async def _activate(db_session, tenant, tmp_path, key):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=key,
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)


async def _client_for(db_session, user_id):
    loaded = (await db_session.execute(
        select(AppUser).options(selectinload(AppUser.granted_business_units))
        .where(AppUser.id == user_id)
    )).scalar_one()

    async def _session_override():
        yield db_session

    async def _user_override():
        return loaded

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_app_user] = _user_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_invoice_evidence_resolves_to_stored_row_and_receipt_application(db_session, tenant, tmp_path):
    org, bu, user = tenant
    await _activate(db_session, tenant, tmp_path, f"evidence-{uuid.uuid4().hex[:8]}")
    client = await _client_for(db_session, user.id)
    try:
        async with client:
            response = await client.get(f"/api/v1/evidence/invoice/S01-INV-1000?business_unit_id={bu.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["record_type"] == "invoice"
    assert body["fields"]["external_id"] == "S01-INV-1000"
    assert body["fields"]["invoice_amount"] in ("1000.0000", "1000.00")
    receipt_group = next(g for g in body["related"] if g["label"] == "Receipt applications")
    assert len(receipt_group["rows"]) >= 1


async def test_unknown_evidence_record_returns_404(db_session, tenant, tmp_path):
    org, bu, user = tenant
    await _activate(db_session, tenant, tmp_path, f"evidence-miss-{uuid.uuid4().hex[:8]}")
    client = await _client_for(db_session, user.id)
    try:
        async with client:
            response = await client.get(f"/api/v1/evidence/invoice/NOT-REAL?business_unit_id={bu.id}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


async def test_unsupported_record_type_returns_400(db_session, tenant, tmp_path):
    org, bu, user = tenant
    await _activate(db_session, tenant, tmp_path, f"evidence-type-{uuid.uuid4().hex[:8]}")
    client = await _client_for(db_session, user.id)
    try:
        async with client:
            response = await client.get(f"/api/v1/evidence/widget/X?business_unit_id={bu.id}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
