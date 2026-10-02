"""FastAPI dependencies: authentication, application-user resolution, and
role/scope authorization. Every data-touching endpoint must depend on
`require_role(...)` (or `get_current_app_user` at minimum) — authentication
alone is not authorization per intent.md.
"""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.oidc import TokenValidationError, validate_token
from revenueflowai.db import get_session
from revenueflowai.models.tenancy import AppUser

_bearer = HTTPBearer(auto_error=True)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    try:
        return validate_token(credentials.credentials)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc


async def get_current_app_user(
    principal=Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> AppUser:
    result = await session.execute(select(AppUser).where(AppUser.oidc_subject == principal.subject))
    app_user = result.scalar_one_or_none()
    if app_user is None or not app_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "no_application_grant",
                "message": "No active application grant for this identity.",
            },
        )
    return app_user


def require_role(*allowed_roles: str) -> Callable:
    async def dependency(app_user: AppUser = Depends(get_current_app_user)) -> AppUser:
        if app_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "role_not_permitted",
                    "message": f"Role '{app_user.role}' cannot perform this action.",
                },
            )
        return app_user

    return dependency


def assert_business_unit_access(app_user: AppUser, business_unit_id: UUID) -> None:
    """Raise 403 unless the user's org/grants cover this business unit.

    Admins are scoped to their whole organization; other roles need an
    explicit grant row. Call this on every tool/API/export/job/object path
    that resolves a business_unit_id, per agent_architecture.md's trusted
    context requirement.
    """
    if app_user.role == "admin":
        return
    granted_ids = {bu.id for bu in app_user.granted_business_units}
    if business_unit_id not in granted_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "business_unit_not_granted",
                "message": "Not authorized for this business unit.",
            },
        )
