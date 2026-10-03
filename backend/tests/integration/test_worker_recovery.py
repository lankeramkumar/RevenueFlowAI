"""Worker crash recovery: a job claimed by a worker that crashes before
finishing (so it's stuck at status='staging') must be reclaimable once its
lease expires -- verified against live Postgres using the real claim_next_job
query, not a mock.

claim_next_job opens its own session (it must, to faithfully simulate a
separate worker process), so these tests commit real rows rather than
relying on the usual rollback-based fixture cleanup -- each test tears
down what it created explicitly.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, update

from revenueflowai.models.ingestion import ImportJob
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization
from revenueflowai.worker import MAX_ATTEMPTS, claim_next_job

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


async def _queued_job(db_session, tenant) -> ImportJob:
    org, bu, user = tenant
    job = ImportJob(
        organization_id=org.id, business_unit_id=bu.id, created_by_user_id=user.id,
        idempotency_key="recovery-test", bundle_hash="deadbeef",
        snapshot_date=AS_OF, status="queued",
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.commit()  # claim_next_job runs in its own session/connection
    return job


async def _cleanup(db_session, tenant, job_id) -> None:
    org, bu, user = tenant
    await db_session.execute(delete(ImportJob).where(ImportJob.id == job_id))
    await db_session.execute(delete(AppUser).where(AppUser.id == user.id))
    await db_session.execute(delete(BusinessUnit).where(BusinessUnit.id == bu.id))
    await db_session.execute(delete(Organization).where(Organization.id == org.id))
    await db_session.commit()


async def test_crashed_job_stuck_at_staging_is_reclaimed_after_lease_expires(db_session, tenant):
    job = await _queued_job(db_session, tenant)
    try:
        first_claim = await claim_next_job()
        assert first_claim == job.id

        # Simulate the worker crashing: status is now "staging" with a live
        # lease, exactly as claim_next_job left it, and nothing ever moves
        # it back to "queued". Without the fix, a second claim attempt
        # (even after the lease has long expired) would never see this job
        # again.
        await db_session.execute(
            update(ImportJob)
            .where(ImportJob.id == job.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db_session.commit()

        second_claim = await claim_next_job()
        assert second_claim == job.id
    finally:
        await _cleanup(db_session, tenant, job.id)


async def test_job_with_an_unexpired_lease_is_not_reclaimed(db_session, tenant):
    job = await _queued_job(db_session, tenant)
    try:
        first_claim = await claim_next_job()
        assert first_claim == job.id
        # lease_expires_at is now + 5 minutes (LEASE_DURATION) -- still valid.

        second_claim = await claim_next_job()
        assert second_claim is None  # nothing else queued; the live lease must not be reclaimed
    finally:
        await _cleanup(db_session, tenant, job.id)


async def test_attempt_count_is_capped(db_session, tenant):
    job = await _queued_job(db_session, tenant)
    try:
        await db_session.execute(
            update(ImportJob).where(ImportJob.id == job.id).values(attempt_count=MAX_ATTEMPTS)
        )
        await db_session.commit()

        claim = await claim_next_job()
        assert claim is None  # exhausted its retry budget; must not be claimed again
    finally:
        await _cleanup(db_session, tenant, job.id)
