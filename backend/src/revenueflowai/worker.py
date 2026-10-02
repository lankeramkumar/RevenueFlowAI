"""Durable import-job worker: leases queued jobs from Postgres and processes them.

Uses `SELECT ... FOR UPDATE SKIP LOCKED` leases (not an external queue broker)
so job state survives worker crashes/restarts — see agent_architecture.md's
durability requirements and intent.md's import lifecycle. The actual CSV
staging/validation/activation logic is implemented in Milestone 2
(revenueflowai.ingestion); this module owns only the lease/retry/dispatch loop.
"""

import asyncio
import logging
import socket
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update

from revenueflowai.db import AsyncSessionLocal
from revenueflowai.models.ingestion import ImportJob

logging.basicConfig(level=logging.INFO)
log = structlog.get_logger()

WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
LEASE_DURATION = timedelta(minutes=5)
POLL_INTERVAL_SECONDS = 2
MAX_ATTEMPTS = 5


async def claim_next_job() -> ImportJob | None:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                select(ImportJob)
                .where(
                    ImportJob.status == "queued",
                    (ImportJob.lease_expires_at.is_(None)) | (ImportJob.lease_expires_at < now),
                    ImportJob.attempt_count < MAX_ATTEMPTS,
                )
                .order_by(ImportJob.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = (await session.execute(stmt)).scalar_one_or_none()
            if job is None:
                return None

            await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job.id)
                .values(
                    lease_owner=WORKER_ID,
                    lease_expires_at=now + LEASE_DURATION,
                    attempt_count=job.attempt_count + 1,
                    status="staging",
                )
            )
        return job


async def process_job(job: ImportJob) -> None:
    """Milestone 2 fills this in with real CSV staging/validation/activation."""
    log.info("import_job.claimed", job_id=str(job.id), worker=WORKER_ID)


async def run_forever() -> None:
    log.info("worker.started", worker=WORKER_ID)
    while True:
        job = await claim_next_job()
        if job is None:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        try:
            await process_job(job)
        except Exception:
            log.exception("import_job.failed", job_id=str(job.id))


if __name__ == "__main__":
    asyncio.run(run_forever())
