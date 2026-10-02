"""Shared mixins for domain models.

Every business record carries both a surrogate UUID primary key (`id`) and the
original CSV business identifier (`external_id`), scoped by organization,
business unit, and dataset version — per intent.md's scoping and lineage
requirements. IDs are strings so leading zeros are preserved.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class PrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScopedRecordMixin(PrimaryKeyMixin, TimestampMixin):
    """Mixin for records ingested from a CSV bundle: scoped, versioned, lineage-tracked."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_units.id"), nullable=False, index=True
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Lineage: which import job / raw file / row produced this record.
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id"), nullable=False
    )
    source_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
