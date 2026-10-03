"""Administration endpoints: business units and application users within
the admin's own organization. Automates what was previously a manual SQL
step after first boot (seeding an app_users row so a logged-in Keycloak
identity gets application-level authorization) -- admin-only, scoped to
the caller's own organization_id, every write audited.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from revenueflowai.auth.deps import require_role
from revenueflowai.db import get_session
from revenueflowai.models.ingestion import AuditEvent
from revenueflowai.models.tenancy import ROLES, AppUser, BusinessUnit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

ADMIN_ONLY = ("admin",)


class BusinessUnitResponse(BaseModel):
    id: UUID
    code: str
    name: str


@router.get("/business-units", response_model=list[BusinessUnitResponse])
async def list_business_units(
    app_user: AppUser = Depends(require_role(*ADMIN_ONLY)),
    session: AsyncSession = Depends(get_session),
) -> list[BusinessUnitResponse]:
    rows = (
        (await session.execute(
            select(BusinessUnit).where(BusinessUnit.organization_id == app_user.organization_id)
        ))
        .scalars()
        .all()
    )
    return [BusinessUnitResponse(id=bu.id, code=bu.code, name=bu.name) for bu in rows]


class AppUserResponse(BaseModel):
    id: UUID
    oidc_subject: str
    email: str
    display_name: str
    role: str
    is_active: bool
    granted_business_unit_ids: list[UUID]


def _to_user_response(user: AppUser) -> AppUserResponse:
    return AppUserResponse(
        id=user.id, oidc_subject=user.oidc_subject, email=user.email, display_name=user.display_name,
        role=user.role, is_active=user.is_active,
        granted_business_unit_ids=[bu.id for bu in user.granted_business_units],
    )


@router.get("/users", response_model=list[AppUserResponse])
async def list_users(
    app_user: AppUser = Depends(require_role(*ADMIN_ONLY)),
    session: AsyncSession = Depends(get_session),
) -> list[AppUserResponse]:
    rows = (
        (await session.execute(
            select(AppUser)
            .options(selectinload(AppUser.granted_business_units))
            .where(AppUser.organization_id == app_user.organization_id)
        ))
        .scalars()
        .unique()
        .all()
    )
    return [_to_user_response(u) for u in rows]


class CreateUserRequest(BaseModel):
    oidc_subject: str
    email: str
    display_name: str
    role: str
    business_unit_ids: list[UUID] = []


async def _resolve_granted_business_units(
    session: AsyncSession, organization_id: UUID, business_unit_ids: list[UUID]
) -> list[BusinessUnit]:
    if not business_unit_ids:
        return []
    rows = (
        (await session.execute(
            select(BusinessUnit).where(
                BusinessUnit.organization_id == organization_id,
                BusinessUnit.id.in_(business_unit_ids),
            )
        ))
        .scalars()
        .all()
    )
    found_ids = {bu.id for bu in rows}
    missing = set(business_unit_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "unknown_business_unit",
                "message": f"Unknown business_unit_id(s) for this organization: "
                           f"{sorted(str(m) for m in missing)}",
            },
        )
    return list(rows)


@router.post("/users", response_model=AppUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    app_user: AppUser = Depends(require_role(*ADMIN_ONLY)),
    session: AsyncSession = Depends(get_session),
) -> AppUserResponse:
    if body.role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "invalid_role", "message": f"role must be one of {ROLES}"},
        )

    existing = (
        await session.execute(select(AppUser).where(AppUser.oidc_subject == body.oidc_subject))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "oidc_subject_conflict",
                "message": "A user with this oidc_subject already exists.",
            },
        )

    granted = await _resolve_granted_business_units(session, app_user.organization_id, body.business_unit_ids)

    new_user = AppUser(
        oidc_subject=body.oidc_subject, email=body.email, display_name=body.display_name,
        role=body.role, organization_id=app_user.organization_id, granted_business_units=granted,
    )
    session.add(new_user)
    await session.flush()
    session.add(AuditEvent(
        actor_user_id=app_user.id, organization_id=app_user.organization_id,
        event_type="app_user.created", outcome="success",
        subject_type="app_user", subject_id=str(new_user.id),
        detail={"email": body.email, "role": body.role},
    ))
    await session.commit()
    await session.refresh(new_user, attribute_names=["granted_business_units"])
    return _to_user_response(new_user)


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    business_unit_ids: list[UUID] | None = None


@router.patch("/users/{user_id}", response_model=AppUserResponse)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    app_user: AppUser = Depends(require_role(*ADMIN_ONLY)),
    session: AsyncSession = Depends(get_session),
) -> AppUserResponse:
    target = (
        await session.execute(
            select(AppUser)
            .options(selectinload(AppUser.granted_business_units))
            .where(AppUser.id == user_id, AppUser.organization_id == app_user.organization_id)
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "user_not_found", "message": "User not found"},
        )

    changes: dict[str, object] = {}
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "invalid_role", "message": f"role must be one of {ROLES}"},
            )
        target.role = body.role
        changes["role"] = body.role
    if body.is_active is not None:
        target.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.business_unit_ids is not None:
        target.granted_business_units = await _resolve_granted_business_units(
            session, app_user.organization_id, body.business_unit_ids
        )
        changes["business_unit_ids"] = [str(i) for i in body.business_unit_ids]

    await session.flush()
    session.add(AuditEvent(
        actor_user_id=app_user.id, organization_id=app_user.organization_id,
        event_type="app_user.updated", outcome="success",
        subject_type="app_user", subject_id=str(target.id), detail=changes,
    ))
    await session.commit()
    await session.refresh(target, attribute_names=["granted_business_units"])
    return _to_user_response(target)


class ProviderStatusResponse(BaseModel):
    default_mode: str
    live_configured: bool
    live_model: str
    modes: list[str]


@router.get("/provider-status", response_model=ProviderStatusResponse)
async def provider_status(
    app_user: AppUser = Depends(require_role(*ADMIN_ONLY)),
) -> ProviderStatusResponse:
    from revenueflowai.agents.providers.live import PLANNER_MODEL
    from revenueflowai.config import get_settings

    return ProviderStatusResponse(
        default_mode="demo",
        live_configured=bool(get_settings().anthropic_api_key),
        live_model=PLANNER_MODEL,
        modes=["demo", "live"],
    )
