"""Dashboard read endpoints — real queries over the active dataset version,
never LLM-computed. Any authenticated role with business-unit access may
view (intent.md: Viewer can "read authorized dashboards").
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.db import get_session
from revenueflowai.domain.services import compute_aging_summary
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class AgingSummaryResponse(BaseModel):
    dataset_version_id: UUID | None
    snapshot_date: date | None
    as_of_date: date
    # {currency: {bucket: decimal-string}} -- money as strings over the wire, per intent.md
    totals_by_currency_bucket: dict[str, dict[str, str]]


@router.get("/aging-summary", response_model=AgingSummaryResponse)
async def get_aging_summary(
    business_unit_id: UUID,
    as_of: date = Query(default_factory=date.today),
    app_user: AppUser = Depends(require_role("admin", "analyst", "approver", "viewer")),
    session: AsyncSession = Depends(get_session),
) -> AgingSummaryResponse:
    assert_business_unit_access(app_user, business_unit_id)

    summary = await compute_aging_summary(session, app_user.organization_id, business_unit_id, as_of)

    return AgingSummaryResponse(
        dataset_version_id=summary.dataset_version_id,
        snapshot_date=summary.snapshot_date,
        as_of_date=summary.as_of_date,
        totals_by_currency_bucket={
            currency: {bucket: str(total) for bucket, total in buckets.items()}
            for currency, buckets in summary.totals_by_currency_bucket.items()
        },
    )
