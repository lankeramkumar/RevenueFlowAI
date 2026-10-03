"""First-sign-in binding of pre-provisioned users, and the idempotent demo seed,
against live Postgres.
"""

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from revenueflowai.auth.deps import get_current_app_user, pending_subject_for
from revenueflowai.bootstrap import _bootstrap
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.demo_seed import _seed
from revenueflowai.models.tenancy import AppUser

pytestmark = pytest.mark.asyncio


async def _provision(email: str, slug: str) -> None:
    await _bootstrap(
        org_name=f"Org {slug}", org_slug=slug, bu_code="BU1", bu_name="BU1",
        admin_subject=pending_subject_for(email), admin_email=email, admin_name="Pending Admin",
    )


async def test_verified_first_sign_in_binds_the_pending_admin(db_session):
    email = f"bind-{uuid.uuid4().hex[:8]}@example.test"
    await _provision(email, f"bind-{uuid.uuid4().hex[:8]}")
    real_sub = f"kc-{uuid.uuid4().hex[:8]}"

    principal = SimpleNamespace(subject=real_sub, email=email, email_verified=True)
    user = await get_current_app_user(principal=principal, session=db_session)

    assert user.oidc_subject == real_sub
    assert user.role == "admin"


async def test_unverified_email_cannot_claim_a_pending_account(db_session):
    email = f"claim-{uuid.uuid4().hex[:8]}@example.test"
    await _provision(email, f"claim-{uuid.uuid4().hex[:8]}")

    principal = SimpleNamespace(subject=f"attacker-{uuid.uuid4().hex[:8]}", email=email, email_verified=False)
    with pytest.raises(HTTPException) as err:
        await get_current_app_user(principal=principal, session=db_session)
    assert err.value.status_code == 403

    async with AsyncSessionLocal() as s:
        still_pending = (await s.execute(
            select(AppUser).where(AppUser.oidc_subject == pending_subject_for(email))
        )).scalar_one_or_none()
    assert still_pending is not None


async def test_demo_seed_is_idempotent_by_admin_email():
    email = f"seed-{uuid.uuid4().hex[:8]}@example.test"
    slug = f"seed-{uuid.uuid4().hex[:8]}"

    first = await _seed(slug, email, 42, date(2026, 10, 2), "demo")
    second = await _seed(slug, email, 42, date(2026, 10, 2), "demo")

    assert first.startswith("Seeded organization")
    assert second.startswith("Skipped")
