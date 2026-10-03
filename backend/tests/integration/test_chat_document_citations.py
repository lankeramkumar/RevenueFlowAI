"""A chat answer cites uploaded documents whose text mentions an ID the
investigation resolved, and leaves unrelated documents out.
"""

import hashlib
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
from revenueflowai.models.documents import Document
from revenueflowai.models.tenancy import AppUser

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


async def test_answer_cites_only_documents_that_mention_the_resolved_invoice(
    db_session, tenant, tmp_path: Path,
):
    org, bu, user = tenant
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", "small",
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=f"doc-cite-{uuid.uuid4().hex[:8]}",
        bundle_hash=compute_bundle_hash(out_dir), snapshot_date=AS_OF,
    )
    assert (await validate_and_activate(db_session, job, out_dir, snapshot_date=AS_OF)).validation.is_valid

    relevant = Document(
        organization_id=org.id, business_unit_id=bu.id, uploaded_by_user_id=user.id,
        filename="remittance-note.txt", content_type="text/plain", byte_size=10,
        sha256=hashlib.sha256(b"x").hexdigest(), storage_key=f"test/{uuid.uuid4()}",
        extracted_text="Customer confirmed a partial payment against S01-INV-1000.",
    )
    unrelated = Document(
        organization_id=org.id, business_unit_id=bu.id, uploaded_by_user_id=user.id,
        filename="policy.txt", content_type="text/plain", byte_size=10,
        sha256=hashlib.sha256(b"y").hexdigest(), storage_key=f"test/{uuid.uuid4()}",
        extracted_text="Net 30 terms apply to all wholesale accounts.",
    )
    db_session.add_all([relevant, unrelated])
    await db_session.flush()

    loaded = (await db_session.execute(
        select(AppUser).options(selectinload(AppUser.granted_business_units)).where(AppUser.id == user.id)
    )).scalar_one()

    async def _session_override():
        yield db_session

    async def _user_override():
        return loaded

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_app_user] = _user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/investigate",
                json={
                    "business_unit_id": str(bu.id),
                    "question": "Why is S01-INV-1000 overdue?",
                    "mode": "demo",
                },
            )
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    cited = [
        e["record_id"] for f in body["findings"] for e in f["evidence"] if e["record_type"] == "document"
    ]
    assert cited == [str(relevant.id)]
    assert any("remittance-note.txt" in f["statement"] for f in body["findings"])
    assert str(unrelated.id) not in response.text
