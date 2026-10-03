"""Evidence drill-down: resolves a chat evidence reference (record_type +
record_id) to the stored row in the active dataset version, plus the rows
directly linked to it. Read-only; every lookup is scoped to the caller's
organization and the requested business unit's active dataset.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.db import get_session
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.models.documents import Document
from revenueflowai.models.entities import (
    CreditApplication,
    Customer,
    Dispute,
    Invoice,
    OrderHold,
    Receipt,
    ReceiptApplication,
    ShipmentLine,
)
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

VIEW_ROLES = ("admin", "analyst", "approver", "viewer")


class RelatedGroup(BaseModel):
    label: str
    rows: list[dict[str, Any]]


class EvidenceRecordResponse(BaseModel):
    record_type: str
    record_id: str
    fields: dict[str, Any]
    related: list[RelatedGroup]


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


_SYSTEM_COLUMNS = {
    "id", "organization_id", "business_unit_id", "dataset_version_id", "import_job_id",
    "source_filename", "source_row_number", "created_at", "updated_at",
}


def _row_fields(row: Any) -> dict[str, Any]:
    return {
        c.key: _plain(getattr(row, c.key))
        for c in row.__table__.columns
        if c.key not in _SYSTEM_COLUMNS
    }


async def _one(session: AsyncSession, model: Any, dv_id: UUID, **filters: Any) -> Any:
    clauses = [model.dataset_version_id == dv_id] + [getattr(model, k) == v for k, v in filters.items()]
    return (await session.execute(select(model).where(*clauses))).scalars().first()


async def _many(session: AsyncSession, model: Any, dv_id: UUID, **filters: Any) -> list[Any]:
    clauses = [model.dataset_version_id == dv_id] + [getattr(model, k).in_(v) for k, v in filters.items()]
    return list((await session.execute(select(model).where(*clauses))).scalars().all())


@router.get("/{record_type}/{record_id}", response_model=EvidenceRecordResponse)
async def get_evidence_record(
    record_type: str,
    record_id: str,
    business_unit_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> EvidenceRecordResponse:
    assert_business_unit_access(app_user, business_unit_id)
    if record_type == "document":
        return await _document_evidence(session, app_user, business_unit_id, record_id)
    dataset = await get_active_dataset_version(session, app_user.organization_id, business_unit_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "no_active_dataset", "message": "Upload and activate a CSV bundle first."},
        )
    dv = dataset.id

    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "evidence_not_found",
            "message": f"No {record_type} '{record_id}' in the active dataset.",
        },
    )

    if record_type == "invoice":
        inv = await _one(session, Invoice, dv, external_id=record_id)
        if inv is None:
            raise not_found
        receipt_apps = await _many(session, ReceiptApplication, dv, invoice_external_id=[record_id])
        credit_apps = await _many(session, CreditApplication, dv, invoice_external_id=[record_id])
        disputes = await _many(session, Dispute, dv, invoice_external_id=[record_id])
        related = [
            RelatedGroup(label="Receipt applications", rows=[_row_fields(r) for r in receipt_apps]),
            RelatedGroup(label="Credit applications", rows=[_row_fields(r) for r in credit_apps]),
            RelatedGroup(label="Disputes", rows=[_row_fields(r) for r in disputes]),
        ]
        return EvidenceRecordResponse(record_type=record_type, record_id=record_id,
                                      fields=_row_fields(inv), related=related)

    if record_type == "receipt":
        rcpt = await _one(session, Receipt, dv, external_id=record_id)
        if rcpt is None:
            raise not_found
        apps = await _many(session, ReceiptApplication, dv, receipt_external_id=[record_id])
        return EvidenceRecordResponse(
            record_type=record_type, record_id=record_id, fields=_row_fields(rcpt),
            related=[RelatedGroup(label="Applied to invoices", rows=[_row_fields(a) for a in apps])],
        )

    if record_type == "customer":
        cust = await _one(session, Customer, dv, external_id=record_id)
        if cust is None:
            raise not_found
        return EvidenceRecordResponse(record_type=record_type, record_id=record_id,
                                      fields=_row_fields(cust), related=[])

    if record_type == "order_hold":
        holds = await _many(session, OrderHold, dv, order_external_id=[record_id])
        if not holds:
            raise not_found
        return EvidenceRecordResponse(
            record_type=record_type, record_id=record_id, fields=_row_fields(holds[0]),
            related=[RelatedGroup(label="All holds on this order", rows=[_row_fields(h) for h in holds])],
        )

    if record_type == "shipment_line":
        line = await _one(session, ShipmentLine, dv, external_id=record_id)
        if line is None:
            raise not_found
        return EvidenceRecordResponse(record_type=record_type, record_id=record_id,
                                      fields=_row_fields(line), related=[])

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error_code": "unsupported_record_type",
            "message": f"Unsupported record type '{record_type}'.",
        },
    )


def record_id_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


async def _document_evidence(
    session: AsyncSession, app_user: AppUser, business_unit_id: UUID, record_id: str
) -> EvidenceRecordResponse:
    doc = (await session.execute(
        select(Document).where(
            Document.id == record_id_uuid(record_id),
            Document.organization_id == app_user.organization_id,
            Document.business_unit_id == business_unit_id,
        )
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "evidence_not_found", "message": f"No document '{record_id}'."},
        )
    fields = {
        "filename": doc.filename, "content_type": doc.content_type, "byte_size": doc.byte_size,
        "sha256": doc.sha256, "created_at": doc.created_at.isoformat(), "text": doc.extracted_text,
    }
    return EvidenceRecordResponse(record_type="document", record_id=record_id, fields=fields, related=[])
