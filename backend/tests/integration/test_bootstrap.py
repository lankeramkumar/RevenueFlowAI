"""First-tenant bootstrap against live Postgres: creates the org, BU, and
admin, and a second run with the same arguments creates nothing new.
"""

import uuid

import pytest
from sqlalchemy import func, select

from revenueflowai.bootstrap import _bootstrap
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization

pytestmark = pytest.mark.asyncio


async def test_bootstrap_is_idempotent(db_session):
    slug = f"boot-{uuid.uuid4().hex[:8]}"
    subject = f"boot-sub-{uuid.uuid4().hex[:8]}"
    args = dict(
        org_name=f"Boot {slug}", org_slug=slug, bu_code="BU1", bu_name="Business Unit 1",
        admin_subject=subject, admin_email=f"{slug}@example.test", admin_name="Admin",
    )

    await _bootstrap(**args)
    await _bootstrap(**args)

    async with AsyncSessionLocal() as s:
        org = (await s.execute(select(Organization).where(Organization.slug == slug))).scalar_one()
        bu_count = (await s.execute(
            select(func.count()).select_from(BusinessUnit).where(BusinessUnit.organization_id == org.id)
        )).scalar_one()
        users = (await s.execute(select(AppUser).where(AppUser.oidc_subject == subject))).scalars().all()

    assert bu_count == 1
    assert len(users) == 1
    assert users[0].role == "admin"
    assert users[0].organization_id == org.id
