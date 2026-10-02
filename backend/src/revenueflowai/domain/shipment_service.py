"""SQL-backed wrapper around domain/shipments.py's pure unbilled-shipment logic."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.domain.shipments import compute_unbilled_shipment
from revenueflowai.models.entities import InvoiceLine, OrderLine, Shipment, ShipmentLine

DEFAULT_AGE_THRESHOLD_DAYS = 5


@dataclass(frozen=True)
class UnbilledShipmentRow:
    shipment_external_id: str
    shipment_line_external_id: str
    order_line_external_id: str | None
    shipped_quantity: Decimal
    billed_quantity: Decimal
    unbilled_quantity: Decimal
    estimated_value: Decimal
    sufficient_evidence: bool
    shipment_date: date


async def compute_unbilled_shipments(
    session: AsyncSession,
    organization_id: UUID,
    business_unit_id: UUID,
    as_of: date,
    age_threshold_days: int = DEFAULT_AGE_THRESHOLD_DAYS,
) -> list[UnbilledShipmentRow]:
    dataset_version = await get_active_dataset_version(session, organization_id, business_unit_id)
    if dataset_version is None:
        return []

    shipments = (
        (await session.execute(select(Shipment).where(Shipment.dataset_version_id == dataset_version.id)))
        .scalars()
        .all()
    )
    shipment_lines = (
        (await session.execute(
            select(ShipmentLine).where(ShipmentLine.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )
    order_lines = (
        (await session.execute(select(OrderLine).where(OrderLine.dataset_version_id == dataset_version.id)))
        .scalars()
        .all()
    )
    invoice_lines = (
        (await session.execute(
            select(InvoiceLine).where(InvoiceLine.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )

    shipment_by_external_id = {s.external_id: s for s in shipments}
    order_line_by_external_id = {ol.external_id: ol for ol in order_lines}

    billed_by_shipment_line: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for il in invoice_lines:
        if il.shipment_line_external_id and il.billed_quantity is not None:
            billed_by_shipment_line[il.shipment_line_external_id] += il.billed_quantity

    rows: list[UnbilledShipmentRow] = []
    for sl in shipment_lines:
        shipment = shipment_by_external_id.get(sl.shipment_external_id)
        if shipment is None:
            continue

        order_line = (
            order_line_by_external_id.get(sl.order_line_external_id)
            if sl.order_line_external_id
            else None
        )
        has_sufficient_links = sl.order_line_external_id is not None and order_line is not None
        unit_price = order_line.unit_price if order_line else Decimal("0")
        billed_quantity = billed_by_shipment_line.get(sl.external_id, Decimal("0"))

        result = compute_unbilled_shipment(
            shipped_quantity=sl.shipped_quantity,
            billed_quantity=billed_quantity if has_sufficient_links else None,
            unit_price=unit_price,
            shipment_date=shipment.shipment_date,
            as_of=as_of,
            age_threshold_days=age_threshold_days,
            has_sufficient_links=has_sufficient_links,
        )
        if result is None:
            continue  # below the age threshold: not an exception yet

        rows.append(UnbilledShipmentRow(
            shipment_external_id=shipment.external_id,
            shipment_line_external_id=sl.external_id,
            order_line_external_id=sl.order_line_external_id,
            shipped_quantity=sl.shipped_quantity,
            billed_quantity=billed_quantity,
            unbilled_quantity=result.unbilled_quantity,
            estimated_value=result.estimated_value,
            sufficient_evidence=result.sufficient_evidence,
            shipment_date=shipment.shipment_date,
        ))

    return rows
