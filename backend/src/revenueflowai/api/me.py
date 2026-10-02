"""Current-user endpoint: role, organization, and accessible business units.
The frontend needs this to know which business_unit_id to query — it never
infers scope from client state.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.db import get_session
from revenueflowai.models.tenancy import AppUser, BusinessUnit

router = APIRouter(prefix="/api/v1/me", tags=["me"])


class BusinessUnitSummary(BaseModel):
    id: UUID
    code: str
    name: str


class MeResponse(BaseModel):
    email: str
    display_name: str
    role: str
    organization_id: UUID
    business_units: list[BusinessUnitSummary]


@router.get("", response_model=MeResponse)
async def get_me(
    app_user: AppUser = Depends(get_current_app_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    if app_user.role == "admin":
        # Admins are scoped to their whole organization (see assert_business_unit_access).
        business_units = (
            (await session.execute(
                select(BusinessUnit).where(BusinessUnit.organization_id == app_user.organization_id)
            ))
            .scalars()
            .all()
        )
    else:
        business_units = app_user.granted_business_units

    return MeResponse(
        email=app_user.email, display_name=app_user.display_name, role=app_user.role,
        organization_id=app_user.organization_id,
        business_units=[BusinessUnitSummary(id=bu.id, code=bu.code, name=bu.name) for bu in business_units],
    )
