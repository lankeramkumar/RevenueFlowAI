"""SQL-backed wrapper around domain/holds.py's pure hold-presentation logic."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.domain.holds import present_hold
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.models.entities import OrderHold


@dataclass(frozen=True)
class OrderHoldRow:
    order_external_id: str
    hold_reason: str
    is_active: bool
    age_days: int | None
    linked_invoice_id: str | None


async def compute_order_holds(
    session: AsyncSession, organization_id: UUID, business_unit_id: UUID, as_of: date,
    active_only: bool = True,
) -> list[OrderHoldRow]:
    dataset_version = await get_active_dataset_version(session, organization_id, business_unit_id)
    if dataset_version is None:
        return []

    holds = (
        (await session.execute(select(OrderHold).where(OrderHold.dataset_version_id == dataset_version.id)))
        .scalars()
        .all()
    )

    rows = []
    for hold in holds:
        presentation = present_hold(
            status=hold.status, hold_reason=hold.hold_reason,
            applied_date=hold.applied_date, released_date=hold.released_date,
            linked_invoice_id=hold.linked_invoice_external_id, as_of=as_of,
        )
        if active_only and not presentation.is_active:
            continue
        rows.append(OrderHoldRow(
            order_external_id=hold.order_external_id,
            hold_reason=presentation.hold_reason,
            is_active=presentation.is_active,
            age_days=presentation.age_days,
            linked_invoice_id=presentation.linked_invoice_id,
        ))

    return rows
