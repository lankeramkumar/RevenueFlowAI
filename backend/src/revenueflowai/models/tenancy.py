"""Organizations, business units, users, and role grants."""

import uuid

from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from revenueflowai.db import Base
from revenueflowai.models.base import PrimaryKeyMixin, TimestampMixin


class Organization(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    business_units: Mapped[list["BusinessUnit"]] = relationship(back_populates="organization")


class BusinessUnit(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_units"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_business_unit_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="business_units")


user_business_unit_grants = Table(
    "user_business_unit_grants",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), primary_key=True),
    Column("business_unit_id", UUID(as_uuid=True), ForeignKey("business_units.id"), primary_key=True),
)


class AppUser(PrimaryKeyMixin, TimestampMixin, Base):
    """Local record of a Keycloak-authenticated user: role + scope grants.

    Authentication (identity, password, MFA) is Keycloak's job. This table
    only tracks application-level authorization: which organization and
    business units a subject is allowed to see, and their role.
    """

    __tablename__ = "app_users"

    oidc_subject: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # admin|analyst|approver|viewer
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    granted_business_units: Mapped[list[BusinessUnit]] = relationship(
        secondary=user_business_unit_grants
    )


ROLES = ("admin", "analyst", "approver", "viewer")
