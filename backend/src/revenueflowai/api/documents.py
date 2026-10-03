"""Source-document endpoints: upload a TXT or PDF, list and read documents, and
download the original bytes. Every lookup is scoped to the caller's
organization and business unit; uploads are written to the audit log.
"""

import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.config import get_settings
from revenueflowai.db import get_session
from revenueflowai.documents import DocumentRejected, extract
from revenueflowai.models.documents import Document
from revenueflowai.models.ingestion import AuditEvent
from revenueflowai.models.tenancy import AppUser
from revenueflowai.storage.s3_store import S3CompatibleObjectStore

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

VIEW_ROLES = ("admin", "analyst", "approver", "viewer")
UPLOAD_ROLES = ("admin", "analyst")


class DocumentSummary(BaseModel):
    id: UUID
    business_unit_id: UUID
    filename: str
    content_type: str
    byte_size: int
    sha256: str
    created_at: datetime


class DocumentDetail(DocumentSummary):
    text: str


def _summary(doc: Document) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id, business_unit_id=doc.business_unit_id, filename=doc.filename,
        content_type=doc.content_type, byte_size=doc.byte_size, sha256=doc.sha256, created_at=doc.created_at,
    )


async def _scoped(session: AsyncSession, app_user: AppUser, document_id: UUID) -> Document:
    doc = (await session.execute(
        select(Document).where(
            Document.id == document_id, Document.organization_id == app_user.organization_id
        )
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "not_found"})
    assert_business_unit_access(app_user, doc.business_unit_id)
    return doc


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(
    business_unit_id: UUID = Form(...),
    file: UploadFile = File(...),
    app_user: AppUser = Depends(require_role(*UPLOAD_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> DocumentSummary:
    assert_business_unit_access(app_user, business_unit_id)
    data = await file.read()
    filename = (file.filename or "document").split("/")[-1].split("\\")[-1][:256] or "document"
    try:
        extracted = extract(filename, file.content_type or "", data)
    except DocumentRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc

    doc_id = uuid.uuid4()
    settings = get_settings()
    storage_key = f"{app_user.organization_id}/{doc_id}/{filename}"
    await S3CompatibleObjectStore().put_object(
        settings.s3_bucket_documents, storage_key, data, content_type=extracted.content_type,
    )
    doc = Document(
        id=doc_id, organization_id=app_user.organization_id, business_unit_id=business_unit_id,
        uploaded_by_user_id=app_user.id, filename=filename, content_type=extracted.content_type,
        byte_size=extracted.byte_size, sha256=extracted.sha256, storage_key=storage_key,
        extracted_text=extracted.text,
    )
    session.add(doc)
    session.add(AuditEvent(
        actor_user_id=app_user.id, organization_id=app_user.organization_id,
        event_type="document.uploaded", outcome="success", subject_type="document",
        subject_id=str(doc_id), detail={"filename": filename, "sha256": extracted.sha256},
    ))
    await session.commit()
    await session.refresh(doc)
    return _summary(doc)


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    business_unit_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentSummary]:
    assert_business_unit_access(app_user, business_unit_id)
    rows = (await session.execute(
        select(Document)
        .where(
            Document.organization_id == app_user.organization_id,
            Document.business_unit_id == business_unit_id,
        )
        .order_by(Document.created_at.desc())
    )).scalars().all()
    return [_summary(d) for d in rows]


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> DocumentDetail:
    doc = await _scoped(session, app_user, document_id)
    return DocumentDetail(**_summary(doc).model_dump(), text=doc.extracted_text)


@router.get("/{document_id}/content")
async def download_document(
    document_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    doc = await _scoped(session, app_user, document_id)
    data = await S3CompatibleObjectStore().get_object(get_settings().s3_bucket_documents, doc.storage_key)
    return Response(
        content=data, media_type=doc.content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )
