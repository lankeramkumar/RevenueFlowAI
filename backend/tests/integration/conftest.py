"""Integration test fixtures: a real connection to the Compose Postgres.

These tests need a live database (`docker compose up` in `infra/`, which
exposes Postgres on localhost:5432 — the same default DATABASE_URL as
backend/.env.example). If the DB is unreachable, every test in this
package is skipped rather than failed, so the DB-independent unit suite
stays green without Docker running.
"""

import socket
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.config import get_settings
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization


def _db_reachable() -> bool:
    """A plain TCP probe, deliberately not using the shared async `engine`:
    that object's connection pool binds to whichever event loop first uses
    it, and this check runs at collection time (its own throwaway loop),
    before pytest-asyncio creates the loop the actual tests run on —
    reusing the pooled engine across both would break asyncpg on Windows.
    """
    settings = get_settings()
    # database_url looks like postgresql+asyncpg://user:pass@host:port/db
    hostport = settings.database_url.split("@")[-1].split("/")[0]
    host, _, port = hostport.partition(":")
    try:
        with socket.create_connection((host, int(port) if port else 5432), timeout=2):
            return True
    except OSError:
        return False


_REACHABLE = _db_reachable()

pytestmark = pytest.mark.skipif(not _REACHABLE, reason="No live Postgres reachable at DATABASE_URL")


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def tenant(db_session: AsyncSession):
    """A throwaway organization/business_unit/user, cleaned up after the test."""
    org = Organization(name=f"Test Org {uuid.uuid4().hex[:8]}", slug=f"test-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    bu = BusinessUnit(organization_id=org.id, code="BU1", name="Business Unit 1")
    db_session.add(bu)
    await db_session.flush()

    user = AppUser(
        oidc_subject=f"test-subject-{uuid.uuid4().hex[:8]}",
        email=f"test-{uuid.uuid4().hex[:8]}@example.test",
        display_name="Test User", role="admin", organization_id=org.id,
    )
    db_session.add(user)
    await db_session.flush()

    yield org, bu, user
