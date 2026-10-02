"""Import jobs, dataset versions, and audit events — durable workflow state.

Per intent.md: import jobs and dataset activation must be persisted (never
process-memory state), support idempotency keys + bundle hashes, and leave
the previous active dataset intact on failure.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from revenueflowai.db import Base
from revenueflowai.models.base import PrimaryKeyMixin, TimestampMixin

IMPORT_JOB_STATES = (
    "queued", "staging", "validating", "awaiting_activation", "activated", "rejected", "failed",
)


class ImportJob(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_import_job_idempotency"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_units.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    bundle_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Worker lease fields for crash recovery (SELECT ... FOR UPDATE SKIP LOCKED pattern).
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)

    activated_dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=True
    )

    validation_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ImportJobFile(PrimaryKeyMixin, TimestampMixin, Base):
    """One raw CSV file within an import job's bundle, stored immutably in object storage."""

    __tablename__ = "import_job_files"

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    byte_size: Mapped[int] = mapped_column(nullable=False)


class DatasetVersion(PrimaryKeyMixin, TimestampMixin, Base):
    """An immutable, activated snapshot of imported data that investigations pin to."""

    __tablename__ = "dataset_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_units.id"), nullable=False, index=True
    )
    source_import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(PrimaryKeyMixin, Base):
    """Append-only audit trail: import activation, investigations, task decisions, auth changes, exports."""

    __tablename__ = "audit_events"

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_users.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)  # success|denied|failed
    subject_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
