"""SQL-backed domain services, verified against live Postgres by inserting
rows directly (not via the CSV pipeline — that's already covered in
test_ingestion_activation.py) and checking the service layer's output
matches the S03/S05/S07 scenarios from synthetic_data_requirements.md.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from revenueflowai.domain.holds_service import compute_order_holds
from revenueflowai.domain.matching_service import compute_receipt_matches
from revenueflowai.domain.shipment_service import compute_unbilled_shipments
from revenueflowai.models.entities import (
    Invoice,
    InvoiceLine,
    Order,
    OrderHold,
    OrderLine,
    Receipt,
    Shipment,
    ShipmentLine,
)
from revenueflowai.models.ingestion import DatasetVersion, ImportJob

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)

COMMON_LINEAGE = {"source_filename": "test.csv", "source_row_number": 1}


async def _active_dataset_version(db_session, org, bu, user):
    job = ImportJob(
        organization_id=org.id, business_unit_id=bu.id, created_by_user_id=user.id,
        idempotency_key="sql-service-test", bundle_hash="deadbeef", snapshot_date=AS_OF, status="activated",
    )
    db_session.add(job)
    await db_session.flush()

    dv = DatasetVersion(
        organization_id=org.id, business_unit_id=bu.id,
        source_import_job_id=job.id, snapshot_date=AS_OF, is_active=True,
    )
    db_session.add(dv)
    await db_session.flush()
    return dv, job.id


def _scope(org, bu, dv, job_id) -> dict:
    return {
        "organization_id": org.id, "business_unit_id": bu.id,
        "dataset_version_id": dv.id, "import_job_id": job_id,
    }


async def test_s05_unbilled_shipments_via_sql(db_session, tenant):
    org, bu, user = tenant
    dv, job_id = await _active_dataset_version(db_session, org, bu, user)
    scope = _scope(org, bu, dv, job_id)

    db_session.add(Order(
        external_id="ORD-S05", customer_external_id="CUST-S05", order_date=AS_OF - timedelta(days=30),
        currency="USD", status="open", **scope, **COMMON_LINEAGE,
    ))
    db_session.add(OrderLine(
        external_id="OL-S05", order_external_id="ORD-S05", item_code="WIDGET",
        ordered_quantity=Decimal("10"), cancelled_quantity=Decimal("0"), unit_price=Decimal("100"),
        line_amount=Decimal("1000"), **scope, **COMMON_LINEAGE,
    ))
    db_session.add(Shipment(
        external_id="SHP-S05", order_external_id="ORD-S05", shipment_date=AS_OF - timedelta(days=7),
        status="shipped", **scope, **COMMON_LINEAGE,
    ))
    db_session.add(ShipmentLine(
        external_id="SL-S05", shipment_external_id="SHP-S05", order_line_external_id="OL-S05",
        shipped_quantity=Decimal("8"), **scope, **COMMON_LINEAGE,
    ))
    db_session.add(Invoice(
        external_id="INV-S05", customer_external_id="CUST-S05", order_external_id="ORD-S05",
        invoice_date=AS_OF - timedelta(days=5), due_date=AS_OF + timedelta(days=25),
        currency="USD", invoice_amount=Decimal("500"), status="posted", **scope, **COMMON_LINEAGE,
    ))
    db_session.add(InvoiceLine(
        external_id="IL-S05", invoice_external_id="INV-S05", shipment_line_external_id="SL-S05",
        billed_quantity=Decimal("5"), line_amount=Decimal("500"), **scope, **COMMON_LINEAGE,
    ))
    await db_session.flush()

    rows = await compute_unbilled_shipments(db_session, org.id, bu.id, AS_OF, age_threshold_days=5)

    assert len(rows) == 1
    row = rows[0]
    assert row.unbilled_quantity == Decimal("3")  # 8 shipped - 5 billed
    assert row.estimated_value == Decimal("300")  # 3 unbilled units * 100 unit price
    assert row.sufficient_evidence is True


async def test_s07_recorded_hold_via_sql(db_session, tenant):
    org, bu, user = tenant
    dv, job_id = await _active_dataset_version(db_session, org, bu, user)
    scope = _scope(org, bu, dv, job_id)

    db_session.add(OrderHold(
        external_id="HOLD-S07", order_external_id="ORD-S07", hold_reason="MISSING_SHIP_TO",
        status="active", applied_date=AS_OF - timedelta(days=10),
        **scope, **COMMON_LINEAGE,
    ))
    await db_session.flush()

    rows = await compute_order_holds(db_session, org.id, bu.id, AS_OF)

    assert len(rows) == 1
    assert rows[0].order_external_id == "ORD-S07"
    assert rows[0].hold_reason == "MISSING_SHIP_TO"
    assert rows[0].is_active is True
    assert rows[0].age_days == 10
    assert rows[0].linked_invoice_id is None  # never asserted without a source record


async def test_s03_exact_receipt_match_via_sql(db_session, tenant):
    org, bu, user = tenant
    dv, job_id = await _active_dataset_version(db_session, org, bu, user)
    scope = _scope(org, bu, dv, job_id)

    db_session.add(Invoice(
        external_id="INV-S03", customer_external_id="CUST-S03", invoice_date=AS_OF - timedelta(days=40),
        due_date=AS_OF - timedelta(days=10), currency="USD", invoice_amount=Decimal("600"), status="posted",
        **scope, **COMMON_LINEAGE,
    ))
    db_session.add(Receipt(
        external_id="RCP-S03", customer_external_id="CUST-S03", receipt_date=AS_OF,
        currency="USD", receipt_amount=Decimal("600"), status="posted",
        remittance_reference="INV-S03", **scope, **COMMON_LINEAGE,
    ))
    await db_session.flush()

    result = await compute_receipt_matches(db_session, org.id, bu.id, "RCP-S03")

    assert result.unapplied_amount == Decimal("600")
    assert not result.is_ambiguous
    assert len(result.proposals) == 1
    assert result.proposals[0].invoice_ids == ("INV-S03",)
    assert result.proposals[0].evidence == "remittance_reference"
