"""Cash Application specialist: receipt balances, match proposals,
residuals, ambiguity. Tool allowlist: get_receipt_details,
find_receipt_matches, get_customer_summary. No autonomous application.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.agents.contracts import (
    EvidenceReference,
    Finding,
    Metric,
    ProposedAction,
    SpecialistResult,
    TaskRequest,
)
from revenueflowai.agents.tools import (
    ToolScope,
    find_receipt_matches_tool,
    get_customer_summary,
)
from revenueflowai.agents.transport import SpecialistHandler


def make_cash_handler(session: AsyncSession) -> SpecialistHandler:
    async def handler(task: TaskRequest) -> SpecialistResult:
        ctx = task.context
        scope = ToolScope(ctx.organization_id, ctx.allowed_business_unit_ids[0], ctx.business_as_of_date)
        findings: list[Finding] = []
        metrics: list[Metric] = []
        proposed_actions: list[ProposedAction] = []
        ambiguity: list[str] = []
        missing: list[str] = []
        tool_calls = 0

        if task.intent == "receipt_match":
            receipt_id = task.resolved_entity_ids.get("receipt_id")
            if not receipt_id:
                return SpecialistResult(
                    task_id=task.task_id, domain="cash", status="needs_clarification",
                    dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
                    ambiguity=("Which receipt ID?",),
                )
            match_data = await find_receipt_matches_tool(session, scope, receipt_id)
            tool_calls += 1
            if match_data["reason"] == "receipt_not_found":
                missing.append(f"Receipt {receipt_id} not found in the active dataset.")
            elif match_data["reason"] == "no_active_dataset":
                missing.append("No active dataset for this business unit.")
            elif not match_data["proposals"]:
                findings.append(Finding(
                    key=f"no_match:{receipt_id}",
                    statement=f"No invoice combination matches receipt {receipt_id}'s unapplied amount of "
                    f"{match_data['unapplied_amount']}.",
                    evidence=(),
                ))
            else:
                evidence = (
                    EvidenceReference(
                        source_type="database_record", record_type="receipt",
                        record_id=receipt_id, dataset_version_id=ctx.dataset_version_id,
                    ),
                )
                if match_data["is_ambiguous"]:
                    ambiguity.append(
                        f"Receipt {receipt_id} has {len(match_data['proposals'])} equally plausible "
                        "single-invoice matches; not silently selecting one."
                    )
                for p in match_data["proposals"]:
                    findings.append(Finding(
                        key=f"match:{receipt_id}:{','.join(p['invoice_ids'])}",
                        statement=(
                            f"Receipt {receipt_id} ({match_data['unapplied_amount']} unapplied) matches "
                            f"invoice(s) {', '.join(p['invoice_ids'])} for {p['total']} "
                            f"(evidence: {p['evidence']}, residual {p['residual']})."
                        ),
                        evidence=evidence,
                    ))
                    proposed_actions.append(ProposedAction(
                        description=(
                            f"Apply receipt {receipt_id} to invoice(s) {', '.join(p['invoice_ids'])}."
                        ),
                        evidence=evidence,
                    ))

        elif task.intent == "customer_summary":
            customer_id = task.resolved_entity_ids.get("customer_id")
            if not customer_id:
                return SpecialistResult(
                    task_id=task.task_id, domain="cash", status="needs_clarification",
                    dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
                    ambiguity=("Which customer ID?",),
                )
            data = await get_customer_summary(session, scope, customer_id)
            tool_calls += 1
            if not data["found"]:
                missing.append(f"Customer {customer_id} not found in the active dataset.")
            else:
                for currency, amount in data["unapplied_cash_by_currency"].items():
                    metrics.append(Metric(
                        name="unapplied_cash", value=amount, unit_or_currency=currency,
                        scope=f"customer:{customer_id}",
                        calculation_provenance="agents.tools.get_customer_summary",
                    ))
                if not data["unapplied_cash_by_currency"]:
                    findings.append(Finding(
                        key=f"no_unapplied_cash:{customer_id}",
                        statement=f"No unapplied cash for customer {customer_id}.", evidence=(),
                    ))

        else:
            missing.append(f"Cash Application specialist has no handling for intent '{task.intent}'.")

        return SpecialistResult(
            task_id=task.task_id, domain="cash",
            status="success" if (findings or metrics) else "partial",
            dataset_version_id=ctx.dataset_version_id, as_of_date=ctx.business_as_of_date.isoformat(),
            findings=tuple(findings), metrics=tuple(metrics), proposed_actions=tuple(proposed_actions),
            ambiguity=tuple(ambiguity), missing_data=tuple(missing), tool_calls_made=tool_calls,
        )

    return handler
