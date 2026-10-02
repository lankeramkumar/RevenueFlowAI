"""Import endpoints: upload a CSV bundle, check job status.

Upload only stores raw files and queues a durable job — it does not
validate/activate inline. The worker (revenueflowai.worker) picks the job
up and runs the real pipeline, so a crash mid-processing is recoverable
via the lease mechanism rather than losing an in-flight HTTP request.
"""

import hashlib
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.config import get_settings
from revenueflowai.db import get_session
from revenueflowai.ingestion.activation import get_or_create_import_job
from revenueflowai.models.ingestion import ImportJob, ImportJobFile
from revenueflowai.models.tenancy import AppUser
from revenueflowai.storage.s3_store import S3CompatibleObjectStore

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])


class ImportJobResponse(BaseModel):
    id: UUID
    status: str
    snapshot_date: date
    error_code: str | None
    validation_summary: dict | None
    activated_dataset_version_id: UUID | None


def _to_response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id, status=job.status, snapshot_date=job.snapshot_date,
        error_code=job.error_code, validation_summary=job.validation_summary,
        activated_dataset_version_id=job.activated_dataset_version_id,
    )


@router.post("", response_model=ImportJobResponse, status_code=status.HTTP_201_CREATED)
async def upload_import(
    business_unit_id: UUID,
    idempotency_key: str,
    snapshot_date: date,
    files: list[UploadFile],
    app_user: AppUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> ImportJobResponse:
    """Admin-only (intent.md: dataset activation is an admin capability).
    Stores each uploaded file in the object store, computes a stable
    bundle hash from their contents, and creates (or reuses, if the
    idempotency key already exists) a queued ImportJob for the worker.
    """
    assert_business_unit_access(app_user, business_unit_id)

    settings = get_settings()
    store = S3CompatibleObjectStore()

    contents: dict[str, bytes] = {}
    for f in files:
        data = await f.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error_code": "file_too_large", "message": f"{f.filename} exceeds the upload limit."},
            )
        contents[f.filename or "unnamed.csv"] = data

    bundle_digest = hashlib.sha256()
    for filename in sorted(contents):
        bundle_digest.update(filename.encode("utf-8"))
        bundle_digest.update(contents[filename])
    bundle_hash = bundle_digest.hexdigest()

    job, was_existing = await get_or_create_import_job(
        session, app_user.organization_id, business_unit_id, app_user.id,
        idempotency_key=idempotency_key, bundle_hash=bundle_hash, snapshot_date=snapshot_date,
    )

    if not was_existing:
        for filename, data in contents.items():
            object_key = f"{app_user.organization_id}/{job.id}/{filename}"
            await store.put_object(settings.s3_bucket_raw_imports, object_key, data, content_type="text/csv")
            session.add(ImportJobFile(
                import_job_id=job.id, filename=filename, object_key=object_key,
                file_hash=hashlib.sha256(data).hexdigest(), byte_size=len(data),
            ))
        await session.commit()

    return _to_response(job)


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_status(
    job_id: UUID,
    app_user: AppUser = Depends(require_role("admin", "analyst", "approver", "viewer")),
    session: AsyncSession = Depends(get_session),
) -> ImportJobResponse:
    job = (
        await session.execute(
            select(ImportJob).where(
                ImportJob.id == job_id, ImportJob.organization_id == app_user.organization_id
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "not_found"})
    assert_business_unit_access(app_user, job.business_unit_id)
    return _to_response(job)
