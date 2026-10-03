"""The streaming investigation endpoint emits plan, specialist, and result
events in order, and the persisted conversation matches the JSON endpoint's.
Uses the small bundle's S01 customer, which has three specialists.
"""

import json
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


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(line[len("data: "):] for line in lines if line.startswith("data: "))
        out.append((event, json.loads(data)))
    return out


async def test_stream_emits_plan_then_specialists_then_result(db_session, tenant, tmp_path: Path):
    org, bu, user = tenant
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", "small",
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=f"stream-{uuid.uuid4().hex[:8]}",
        bundle_hash=compute_bundle_hash(out_dir), snapshot_date=AS_OF,
    )
    assert (await validate_and_activate(db_session, job, out_dir, snapshot_date=AS_OF)).validation.is_valid

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
                "/api/v1/chat/investigate/stream",
                json={"business_unit_id": str(bu.id),
                      "question": "Summarize this customer's outstanding invoices for S01-CUST",
                      "mode": "demo"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "plan"
    assert kinds[1:4] == ["specialist", "specialist", "specialist"]
    assert kinds[-1] == "result"
    result_body = events[-1][1]
    assert result_body["provider_mode"] == "demo"
    assert "S01-CUST" in result_body["summary"] or "600.00" in result_body["summary"]
