"""Supervisor: interprets a question via a QuestionPlanner (demo or live),
dispatches the resulting bounded plan to specialists, validates/merges
findings. Execution is identical regardless of which planner produced the
plan -- only the planning step differs between demo and live mode.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from revenueflowai.agents.contracts import (
    EvidenceReference,
    FinalInvestigation,
    Metric,
    ProposedAction,
    RemainingBudgets,
    SpecialistStatusSummary,
    TaskRequest,
    TrustedContext,
)
from revenueflowai.agents.providers.base import QuestionPlanner
from revenueflowai.agents.transport import InternalAgentTransport


@dataclass(frozen=True)
class InvestigationScope:
    organization_id: UUID
    business_unit_id: UUID
    dataset_version_id: UUID
    business_as_of_date: date
    source_snapshot_date: date
    actor_user_id: UUID
    provider_mode: str


def _build_context(scope: InvestigationScope, investigation_id: UUID) -> TrustedContext:
    return TrustedContext(
        investigation_id=investigation_id, conversation_id=investigation_id, turn_id=uuid4(),
        trace_id=uuid4(), task_id=uuid4(), actor_user_id=scope.actor_user_id,
        organization_id=scope.organization_id, allowed_business_unit_ids=(scope.business_unit_id,),
        dataset_version_id=scope.dataset_version_id, business_as_of_date=scope.business_as_of_date,
        source_snapshot_date=scope.source_snapshot_date, deadline_at=datetime.now(UTC),
        budgets=RemainingBudgets(
            tool_calls_remaining=24, model_requests_remaining=12, tokens_remaining=24_000
        ),
        provider_mode=scope.provider_mode,
    )


async def run_investigation(
    scope: InvestigationScope, question: str, transport: InternalAgentTransport,
    planner: QuestionPlanner, customer_id_hint: str | None = None,
    prior_entities: dict[str, str] | None = None,
) -> FinalInvestigation:
    plan = await planner.plan(question, customer_id_hint, prior_entities)
    as_of_str = scope.business_as_of_date.isoformat()

    if not plan.dispatches:
        reason = (
            "The live provider could not be reached; please try again or use demo mode."
            if plan.label == "live_provider_error"
            else "I couldn't determine which specialist to consult for this question. "
            "Try asking about a specific invoice, order, receipt, or shipment ID, "
            "or ask for a customer summary."
        )
        return FinalInvestigation(
            summary=reason, findings=(), specialist_status=(), evidence=(), recommended_actions=(),
            dispatches=(), entities=dict(plan.entities),
            missing_data=("unsupported_question_pattern",) if plan.label != "live_provider_error"
            else ("live_provider_unavailable",),
            dataset_version_id=scope.dataset_version_id, as_of_date=as_of_str,
        )

    investigation_id = uuid4()
    results = []
    for domain, intent in plan.dispatches:
        context = _build_context(scope, investigation_id)
        task = TaskRequest(
            task_id=context.task_id, domain=domain, intent=intent,
            resolved_entity_ids=plan.entities, context=context,
        )
        result = await transport.dispatch(task)
        results.append(result)

    seen_finding_keys: set[str] = set()
    all_findings = []
    all_evidence: list[EvidenceReference] = []
    seen_evidence: set[tuple[str, str]] = set()
    all_actions: list[ProposedAction] = []
    all_missing: list[str] = []
    all_metrics: list[Metric] = []

    for r in results:
        all_metrics.extend(r.metrics)
        for f in r.findings:
            if f.key not in seen_finding_keys:
                seen_finding_keys.add(f.key)
                all_findings.append(f)
                for ev in f.evidence:
                    ev_key = (ev.record_type, ev.record_id)
                    if ev_key not in seen_evidence:
                        seen_evidence.add(ev_key)
                        all_evidence.append(ev)
        all_actions.extend(r.proposed_actions)
        all_missing.extend(r.missing_data)
        all_missing.extend(f"ambiguous: {a}" for a in r.ambiguity)

    specialist_status = tuple(
        SpecialistStatusSummary(domain=r.domain, status=r.status, unavailable_reason=r.error_code)
        for r in results
    )

    if all_findings:
        summary = " ".join(f.statement for f in all_findings[:5])
    else:
        summary = "No findings were returned by the consulted specialist(s)."
    if all_missing:
        summary += f" ({len(all_missing)} item(s) noted as missing/ambiguous.)"

    return FinalInvestigation(
        summary=summary, findings=tuple(all_findings), metrics=tuple(all_metrics),
        dispatches=tuple(f"{d}:{i}" for d, i in plan.dispatches), entities=dict(plan.entities),
        specialist_status=specialist_status,
        evidence=tuple(all_evidence), recommended_actions=tuple(all_actions),
        missing_data=tuple(all_missing),
        dataset_version_id=scope.dataset_version_id, as_of_date=as_of_str,
    )
