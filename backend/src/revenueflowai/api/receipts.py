"""Receipt match-proposal endpoint. No autonomous application of receipts —
intent.md: these are proposals for a human to review, never executed."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.db import get_session
from revenueflowai.domain.matching_service import compute_receipt_matches
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/receipts", tags=["receipts"])


class MatchProposalResponse(BaseModel):
    invoice_ids: list[str]
    total: str
    residual: str
    is_exact: bool
    evidence: str


class ReceiptMatchResponse(BaseModel):
    receipt_external_id: str
    unapplied_amount: str | None
    proposals: list[MatchProposalResponse]
    is_ambiguous: bool
    reason: str | None


@router.get("/{receipt_external_id}/matches", response_model=ReceiptMatchResponse)
async def get_receipt_matches(
    receipt_external_id: str,
    business_unit_id: UUID,
    app_user: AppUser = Depends(require_role("admin", "analyst", "approver", "viewer")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptMatchResponse:
    assert_business_unit_access(app_user, business_unit_id)

    result = await compute_receipt_matches(
        session, app_user.organization_id, business_unit_id, receipt_external_id
    )

    return ReceiptMatchResponse(
        receipt_external_id=result.receipt_external_id,
        unapplied_amount=str(result.unapplied_amount) if result.unapplied_amount is not None else None,
        proposals=[
            MatchProposalResponse(
                invoice_ids=list(p.invoice_ids), total=str(p.total), residual=str(p.residual),
                is_exact=p.is_exact, evidence=p.evidence,
            )
            for p in result.proposals
        ],
        is_ambiguous=result.is_ambiguous,
        reason=result.reason,
    )
