"""AR specialist: invoice balances, aging, disputes, customer receivable
summary. Tool allowlist: get_invoice_details, get_aging_summary,
get_disputes, get_customer_summary.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.agents.contracts import EvidenceReference, Finding, Metric, SpecialistResult, TaskRequest
from revenueflowai.agents.format import money
from revenueflowai.agents.tools import (
    ToolScope,
    get_aging_summary,
    get_customer_summary,
    get_disputes,
    get_invoice_details,
)
from revenueflowai.agents.transport import SpecialistHandler


def make_ar_handler(session: AsyncSession) -> SpecialistHandler:
    async def handler(task: TaskRequest) -> SpecialistResult:
        ctx = task.context
        scope = ToolScope(ctx.organization_id, ctx.allowed_business_unit_ids[0], ctx.business_as_of_date)
        findings: list[Finding] = []
        metrics: list[Metric] = []
        missing: list[str] = []
        tool_calls = 0

        if task.intent == "invoice_overdue_dispute":
            invoice_id = task.resolved_entity_ids.get("invoice_id")
            if not invoice_id:
                return SpecialistResult(
                    task_id=task.task_id, domain="ar", status="needs_clarification",
                    dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
                    ambiguity=("Which invoice ID?",),
                )
            detail = await get_invoice_details(session, scope, invoice_id)
            tool_calls += 1
            if not detail["found"]:
                missing.append(f"Invoice {invoice_id} not found in the active dataset.")
            else:
                evidence = (
                    EvidenceReference(
                        source_type="database_record", record_type="invoice",
                        record_id=invoice_id, dataset_version_id=ctx.dataset_version_id,
                    ),
                )
                if detail["open_balance"] is None:
                    findings.append(Finding(
                        key=f"invoice_status:{invoice_id}",
                        statement=f"Invoice {invoice_id} is '{detail['status']}' and has no open balance.",
                        evidence=evidence,
                    ))
                else:
                    findings.append(Finding(
                        key=f"overdue:{invoice_id}",
                        statement=(
                            f"Invoice {invoice_id} has an open balance of {money(detail['open_balance'])} "
                            f"{detail['currency']}, {detail['days_overdue']} days overdue "
                            f"(bucket {detail['aging_bucket']})."
                        ),
                        evidence=evidence,
                    ))
                    metrics.append(Metric(
                        name="open_balance", value=detail["open_balance"],
                        unit_or_currency=detail["currency"], scope=f"invoice:{invoice_id}",
                        calculation_provenance="domain.balances.compute_invoice_open_balance",
                    ))
                if detail["open_dispute_amount"] != "0":
                    findings.append(Finding(
                        key=f"dispute:{invoice_id}",
                        statement=(
                            f"Invoice {invoice_id} has an open dispute of "
                            f"{money(detail['open_dispute_amount'])} "
                            f"{detail['currency']}. A dispute annotates the balance; it does not reduce it."
                        ),
                        evidence=evidence,
                    ))
                else:
                    findings.append(Finding(
                        key=f"no_dispute:{invoice_id}",
                        statement=f"No open dispute recorded for invoice {invoice_id}.", evidence=evidence,
                    ))

        elif task.intent == "aging_summary":
            data = await get_aging_summary(session, scope)
            tool_calls += 1
            for currency, buckets in data["totals_by_currency_bucket"].items():
                for bucket, total in buckets.items():
                    if total != "0":
                        metrics.append(Metric(
                            name="aging_total", value=total, unit_or_currency=currency,
                            scope=f"bucket:{bucket}",
                            calculation_provenance="domain.services.compute_aging_summary",
                        ))
                        findings.append(Finding(
                            key=f"aging:{currency}:{bucket}",
                            statement=f"{money(total)} {currency} is in the '{bucket}' aging bucket.",
                            evidence=(),
                        ))
            if not metrics:
                findings.append(Finding(
                    key="no_open_balances", statement="No open invoice balances.", evidence=(),
                ))

        elif task.intent == "customer_summary":
            customer_id = task.resolved_entity_ids.get("customer_id")
            if not customer_id:
                return SpecialistResult(
                    task_id=task.task_id, domain="ar", status="needs_clarification",
                    dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
                    ambiguity=("Which customer ID?",),
                )
            data = await get_customer_summary(session, scope, customer_id)
            tool_calls += 1
            if not data["found"]:
                missing.append(f"Customer {customer_id} not found in the active dataset.")
            else:
                evidence = (
                    EvidenceReference(
                        source_type="database_record", record_type="customer",
                        record_id=customer_id, dataset_version_id=ctx.dataset_version_id,
                    ),
                )
                for currency, amount in data["outstanding_balance_by_currency"].items():
                    metrics.append(Metric(
                        name="outstanding_balance", value=amount, unit_or_currency=currency,
                        scope=f"customer:{customer_id}",
                        calculation_provenance="agents.tools.get_customer_summary",
                    ))
                    findings.append(Finding(
                        key=f"outstanding:{customer_id}:{currency}",
                        statement=f"Customer {customer_id} has {money(amount)} {currency} outstanding.",
                        evidence=evidence,
                    ))
                findings.append(Finding(
                    key=f"disputes:{customer_id}",
                    statement=(
                        f"{data['open_dispute_count']} open dispute(s) totaling "
                        f"{money(data['open_dispute_amount_total'])}."
                    ),
                    evidence=evidence,
                ))

            disputes_data = await get_disputes(session, scope)
            tool_calls += 1
            _ = disputes_data  # available for future drill-down; customer_summary already includes the count

        else:
            missing.append(f"AR specialist has no handling for intent '{task.intent}'.")

        return SpecialistResult(
            task_id=task.task_id, domain="ar",
            status="success" if (findings or metrics) else "partial",
            dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
            findings=tuple(findings), metrics=tuple(metrics), missing_data=tuple(missing),
            tool_calls_made=tool_calls,
        )

    return handler
