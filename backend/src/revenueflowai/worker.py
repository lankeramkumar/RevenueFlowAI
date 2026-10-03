"""Durable import-job worker: leases queued jobs from Postgres and processes them.

Uses `SELECT ... FOR UPDATE SKIP LOCKED` leases (not an external queue broker)
so job state survives worker crashes/restarts — see agent_architecture.md's
durability requirements and intent.md's import lifecycle.
"""

import asyncio
import http.server
import logging
import os
import socket
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select, update

from revenueflowai.config import get_settings
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.ingestion.activation import validate_and_activate
from revenueflowai.models.ingestion import ImportJob, ImportJobFile
from revenueflowai.observability import registry
from revenueflowai.storage.s3_store import S3CompatibleObjectStore

logging.basicConfig(level=logging.INFO)
log = structlog.get_logger()

WORKER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
LEASE_DURATION = timedelta(minutes=5)
POLL_INTERVAL_SECONDS = 2
MAX_ATTEMPTS = 5
METRICS_PORT = int(os.environ.get("WORKER_METRICS_PORT", "9100"))


async def claim_next_job() -> uuid.UUID | None:
    """Leases one queued job and returns its ID (not the ORM object — the
    session that claimed it closes immediately, so the object would be
    detached; process_job re-fetches it on its own session instead).
    """
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                select(ImportJob.id)
                .where(
                    # "queued" is a fresh job; "staging" with an expired
                    # lease is one a worker claimed and then crashed before
                    # finishing -- both are reclaimable. Without the
                    # "staging" branch, a crashed job would sit at status=
                    # "staging" forever: nothing ever moves it back to
                    # "queued", so it would never be picked up again.
                    ImportJob.status.in_(("queued", "staging")),
                    (ImportJob.lease_expires_at.is_(None)) | (ImportJob.lease_expires_at < now),
                    ImportJob.attempt_count < MAX_ATTEMPTS,
                )
                .order_by(ImportJob.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job_id = (await session.execute(stmt)).scalar_one_or_none()
            if job_id is None:
                return None

            await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id)
                .values(
                    lease_owner=WORKER_ID,
                    lease_expires_at=now + LEASE_DURATION,
                    attempt_count=ImportJob.attempt_count + 1,
                    status="staging",
                )
            )
        return job_id


async def process_job(job_id: uuid.UUID) -> None:
    started = time.perf_counter()
    settings = get_settings()
    store = S3CompatibleObjectStore()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = (
                await session.execute(select(ImportJob).where(ImportJob.id == job_id))
            ).scalar_one()
            files = (
                await session.execute(
                    select(ImportJobFile).where(ImportJobFile.import_job_id == job_id)
                )
            ).scalars().all()

            with tempfile.TemporaryDirectory(prefix=f"import-{job_id}-") as tmp:
                bundle_dir = Path(tmp)
                for f in files:
                    data = await store.get_object(settings.s3_bucket_raw_imports, f.object_key)
                    (bundle_dir / f.filename).write_bytes(data)

                outcome = await validate_and_activate(session, job, bundle_dir, job.snapshot_date)

            log.info(
                "import_job.processed", job_id=str(job_id), status=job.status,
                valid=outcome.validation.is_valid, error_count=len(outcome.validation.errors),
            )
            registry.inc("import_jobs_total", outcome=job.status)
            registry.observe("import_job_duration_seconds", time.perf_counter() - started)


def _serve_metrics(port: int = METRICS_PORT) -> http.server.ThreadingHTTPServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            body = registry.render().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def run_forever() -> None:
    log.info("worker.started", worker=WORKER_ID)
    _serve_metrics()
    while True:
        job_id = await claim_next_job()
        if job_id is None:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        registry.inc("import_jobs_claimed_total")
        try:
            await process_job(job_id)
        except Exception:
            registry.inc("import_jobs_total", outcome="failed")
            log.exception("import_job.failed", job_id=str(job_id))


if __name__ == "__main__":
    asyncio.run(run_forever())
