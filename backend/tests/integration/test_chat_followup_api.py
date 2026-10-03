"""Persisted follow-ups through the real chat endpoints: a pronoun-only
follow-up in the same conversation must resolve to the invoice from the
prior turn, and the conversation must reload with the same structure.
Uses the small bundle's S01-INV-1000 (hand-calculated balance 600.00 USD).
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


async def test_pronoun_follow_up_resolves_prior_invoice_through_the_api(db_session, tenant, tmp_path: Path):
    org, bu, user = tenant
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", "small",
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=f"chat-followup-{uuid.uuid4().hex[:8]}",
        bundle_hash=compute_bundle_hash(out_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, out_dir, snapshot_date=AS_OF)
    assert outcome.validation.is_valid

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
            first = await client.post(
                "/api/v1/chat/investigate",
                json={
                    "business_unit_id": str(bu.id),
                    "question": "Why is S01-INV-1000 overdue?",
                    "mode": "demo",
                },
            )
            assert first.status_code == 200, first.text
            conversation_id = first.json()["conversation_id"]

            follow = await client.post(
                "/api/v1/chat/investigate",
                json={"business_unit_id": str(bu.id), "question": "Is there a dispute on it?",
                      "conversation_id": conversation_id, "mode": "demo"},
            )
            assert follow.status_code == 200, follow.text
            body = follow.json()
            assert body["conversation_id"] == conversation_id
            assert {e["record_id"] for e in body["evidence"]} == {"S01-INV-1000"}
            assert body["missing_data"] == []

            history = await client.get(f"/api/v1/chat/{conversation_id}/messages")
            assert history.status_code == 200
            messages = history.json()
            assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
            assert messages[1]["findings"], "stored assistant turn should keep structured findings"
            assert messages[3]["evidence"][0]["record_id"] == "S01-INV-1000"
    finally:
        app.dependency_overrides.clear()
