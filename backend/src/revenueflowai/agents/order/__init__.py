"""Order specialist: shipment/billing reconciliation, holds. Per
agent_architecture.md, this module owns a separate role, typed interface,
and tool allowlist (list_unbilled_shipments, get_order_trace, scoped
order/document evidence) -- it cannot call AR or Cash, and cannot
recursively delegate back through the supervisor.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.agents.contracts import EvidenceReference, Finding, SpecialistResult, TaskRequest
from revenueflowai.agents.format import money as _money
from revenueflowai.agents.format import qty as _qty
from revenueflowai.agents.tools import ToolScope, get_order_trace, list_unbilled_shipments
from revenueflowai.agents.transport import SpecialistHandler


def make_order_handler(session: AsyncSession) -> SpecialistHandler:
    async def handler(task: TaskRequest) -> SpecialistResult:
        ctx = task.context
        scope = ToolScope(ctx.organization_id, ctx.allowed_business_unit_ids[0], ctx.business_as_of_date)
        findings: list[Finding] = []
        missing: list[str] = []
        tool_calls = 0

        if task.intent == "unbilled_shipments":
            threshold = int(task.filters.get("age_threshold_days", "5"))
            data = await list_unbilled_shipments(session, scope, threshold)
            tool_calls += 1
            rows = data["unbilled_shipments"]
            if not rows:
                findings.append(Finding(
                    key="no_unbilled_shipments",
                    statement=f"No shipments are unbilled beyond {threshold} days as of {scope.as_of}.",
                    evidence=(),
                ))
            for r in rows:
                findings.append(Finding(
                    key=f"unbilled:{r['shipment_line_id']}",
                    statement=(
                        f"Shipment {r['shipment_id']} line {r['shipment_line_id']}: "
                        f"{_qty(r['unbilled_quantity'])} of {_qty(r['shipped_quantity'])} units unbilled "
                        f"(estimated value {_money(r['estimated_value'])}, shipped {r['shipment_date']})."
                        if r["sufficient_evidence"]
                        else f"Shipment {r['shipment_id']} line {r['shipment_line_id']} lacks sufficient "
                        "billing-link evidence; cannot confirm unbilled status."
                    ),
                    evidence=(
                        EvidenceReference(
                            source_type="database_record", record_type="shipment_line",
                            record_id=r["shipment_line_id"], dataset_version_id=ctx.dataset_version_id,
                        ),
                    ),
                ))

        elif task.intent == "order_hold":
            order_id = task.resolved_entity_ids.get("order_id")
            if not order_id:
                return SpecialistResult(
                    task_id=task.task_id, domain="order", status="needs_clarification",
                    dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
                    ambiguity=("Which order ID?",),
                )
            data = await get_order_trace(session, scope, order_id)
            tool_calls += 1
            if not data["found"]:
                missing.append(f"Order {order_id} not found in the active dataset.")
            else:
                active_holds = [h for h in data["holds"] if h["is_active"]]
                if not active_holds:
                    findings.append(Finding(
                        key=f"no_active_hold:{order_id}",
                        statement=f"Order {order_id} has no active hold.", evidence=(),
                    ))
                for h in active_holds:
                    statement = f"Order {order_id} is on hold: recorded reason '{h['hold_reason']}'"
                    if h["linked_invoice_id"]:
                        statement += f", linked to invoice {h['linked_invoice_id']} by a source record."
                    else:
                        statement += ". No source record links this hold to any invoice."
                    findings.append(Finding(
                        key=f"hold:{order_id}", statement=statement,
                        evidence=(
                            EvidenceReference(
                                source_type="database_record", record_type="order_hold",
                                record_id=order_id, dataset_version_id=ctx.dataset_version_id,
                            ),
                        ),
                    ))

        else:
            missing.append(f"Order specialist has no handling for intent '{task.intent}'.")

        return SpecialistResult(
            task_id=task.task_id, domain="order",
            status="success" if findings else ("partial" if missing else "success"),
            dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
            findings=tuple(findings), missing_data=tuple(missing), tool_calls_made=tool_calls,
        )

    return handler
