"""Import-job orchestration: raw storage, validation gate, and transactional
dataset activation. Per intent.md: reject invalid bundles atomically, never
partially overwrite the active dataset, and make repeated uploads
idempotent via (organization, idempotency_key).
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.ingestion.loader import load_bundle_into_dataset
from revenueflowai.ingestion.validator import ValidationResult, validate_bundle
from revenueflowai.models.ingestion import DatasetVersion, ImportJob


def compute_bundle_hash(bundle_dir: Path) -> str:
    """Stable hash of a bundle's file contents, independent of filesystem
    metadata — used for the idempotency/duplicate-upload check.
    """
    digest = hashlib.sha256()
    for path in sorted(bundle_dir.glob("*.csv")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class ActivationOutcome:
    import_job: ImportJob
    dataset_version: DatasetVersion | None
    validation: ValidationResult
    row_counts: dict[str, int] | None
    was_idempotent_replay: bool


async def get_or_create_import_job(
    session: AsyncSession,
    organization_id: UUID,
    business_unit_id: UUID,
    created_by_user_id: UUID,
    idempotency_key: str,
    bundle_hash: str,
    snapshot_date: date,
) -> tuple[ImportJob, bool]:
    """Returns (job, is_existing). A repeated upload with the same
    idempotency_key returns the original job untouched rather than creating
    a duplicate — intent.md's "Repeated uploads must not duplicate records
    or jobs."
    """
    existing = (
        await session.execute(
            select(ImportJob).where(
                ImportJob.organization_id == organization_id,
                ImportJob.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, True

    job = ImportJob(
        organization_id=organization_id,
        business_unit_id=business_unit_id,
        created_by_user_id=created_by_user_id,
        idempotency_key=idempotency_key,
        bundle_hash=bundle_hash,
        snapshot_date=snapshot_date,
        status="queued",
    )
    session.add(job)
    await session.flush()
    return job, False


async def _supersede_active_dataset(
    session: AsyncSession, organization_id: UUID, business_unit_id: UUID
) -> None:
    await session.execute(
        update(DatasetVersion)
        .where(
            DatasetVersion.organization_id == organization_id,
            DatasetVersion.business_unit_id == business_unit_id,
            DatasetVersion.is_active.is_(True),
        )
        .values(is_active=False, superseded_at=datetime.now(UTC))
    )


async def validate_and_activate(
    session: AsyncSession,
    import_job: ImportJob,
    bundle_dir: Path,
    snapshot_date: date,
) -> ActivationOutcome:
    """The whole import lifecycle from staging through activation, as one
    call: validate; if invalid, reject (job marked 'rejected', previous
    active dataset untouched); if valid, activate transactionally.
    """
    if import_job.status == "activated":
        # Idempotent replay of an already-activated job: don't reprocess.
        existing_version = (
            await session.execute(
                select(DatasetVersion).where(DatasetVersion.id == import_job.activated_dataset_version_id)
            )
        ).scalar_one_or_none()
        return ActivationOutcome(import_job, existing_version, ValidationResult(), None, True)

    result = validate_bundle(bundle_dir)
    import_job.validation_summary = {
        "error_count": len(result.errors),
        "errors": [
            {"file": e.file, "row": e.row_number, "column": e.column, "code": e.code, "message": e.message}
            for e in result.errors[:200]  # cap the persisted summary; full detail stays in logs
        ],
    }

    if not result.is_valid:
        import_job.status = "rejected"
        import_job.error_code = "validation_failed"
        await session.flush()
        return ActivationOutcome(import_job, None, result, None, False)

    await _supersede_active_dataset(session, import_job.organization_id, import_job.business_unit_id)

    dataset_version = DatasetVersion(
        organization_id=import_job.organization_id,
        business_unit_id=import_job.business_unit_id,
        source_import_job_id=import_job.id,
        snapshot_date=snapshot_date,
        is_active=True,
    )
    session.add(dataset_version)
    await session.flush()  # assign dataset_version.id before loading rows

    row_counts = await load_bundle_into_dataset(
        session=session,
        bundle_dir=bundle_dir,
        organization_id=import_job.organization_id,
        business_unit_id=import_job.business_unit_id,
        dataset_version_id=dataset_version.id,
        import_job_id=import_job.id,
    )

    import_job.status = "activated"
    import_job.activated_dataset_version_id = dataset_version.id
    await session.flush()

    return ActivationOutcome(import_job, dataset_version, result, row_counts, False)
