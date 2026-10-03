"""Real OIDC token validation against Keycloak.

Validates issuer, audience, signature (via JWKS), and expiry. No bypass
path exists outside `DEMO_MODE`, and demo mode still validates real tokens
issued by the Keycloak container in docker-compose — it does not skip
verification, it only controls whether unauthenticated demo-login UI is
offered.
"""

from dataclasses import dataclass
from functools import lru_cache

import httpx
from jose import jwt
from jose.exceptions import JWTError

from revenueflowai.config import get_settings


class TokenValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    email: str
    email_verified: bool
    display_name: str
    realm_roles: tuple[str, ...]


@lru_cache
def _jwks_client() -> httpx.Client:
    return httpx.Client(timeout=5.0)


def _fetch_jwks() -> dict:
    settings = get_settings()
    response = _jwks_client().get(settings.oidc_jwks_url)
    response.raise_for_status()
    return response.json()


def validate_token(token: str) -> AuthenticatedPrincipal:
    settings = get_settings()
    try:
        jwks = _fetch_jwks()
        claims = jwt.decode(
            token,
            jwks,
            issuer=settings.oidc_issuer,
            options={
                "leeway": settings.jwt_leeway_seconds,
                "verify_aud": False,
                "verify_at_hash": False,  # ID tokens carry at_hash; the access token is not sent with them
            },
        )
        _check_audience(claims, settings.oidc_audience)
    except JWTError as exc:
        raise TokenValidationError("invalid_token", str(exc)) from exc
    except httpx.HTTPError as exc:
        raise TokenValidationError("jwks_unavailable", str(exc)) from exc

    realm_access = claims.get("realm_access", {})
    roles = tuple(realm_access.get("roles", ()))

    return AuthenticatedPrincipal(
        subject=claims["sub"],
        email=claims.get("email", ""),
        email_verified=bool(claims.get("email_verified", False)),
        display_name=claims.get("name", claims.get("preferred_username", claims["sub"])),
        realm_roles=roles,
    )


def _check_audience(claims: dict, expected: str) -> None:
    """Keycloak access tokens carry the audience in `aud`. Cognito access tokens
    carry the app client in `client_id` and no `aud`. Either must match exactly.
    """
    aud = claims.get("aud")
    audiences = aud if isinstance(aud, list) else [aud] if aud else []
    if expected in audiences or claims.get("client_id") == expected:
        return
    raise JWTError("token audience does not match this API")
