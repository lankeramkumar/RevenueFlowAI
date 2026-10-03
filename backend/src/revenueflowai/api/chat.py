"""Investigation chat endpoint. Runs the Supervisor synchronously (no SSE
yet -- tracked as a gap) and persists the conversation. intent.md: the UI
must accurately label demo vs. live mode; never claim a live model
answered when the demo provider actually did.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.agents.ar import make_ar_handler
from revenueflowai.agents.cash import make_cash_handler
from revenueflowai.agents.contracts import Domain
from revenueflowai.agents.order import make_order_handler
from revenueflowai.agents.providers.base import QuestionPlanner
from revenueflowai.agents.providers.demo import DemoQuestionPlanner
from revenueflowai.agents.supervisor import InvestigationScope, run_investigation
from revenueflowai.agents.transport import InternalAgentTransport, SpecialistHandler
from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.config import get_settings
from revenueflowai.db import get_session
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.models.chat import ChatMessage, Conversation
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

VIEW_ROLES = ("admin", "analyst", "approver", "viewer")

# Evidence record types whose IDs can be carried into a follow-up question.
_RECORD_TYPE_TO_ENTITY = {"invoice": "invoice_id", "receipt": "receipt_id", "customer": "customer_id"}


def _get_planner(requested_mode: str) -> tuple[QuestionPlanner, str]:
    """Falls back to demo when live is requested but no key is configured --
    labeled honestly either way, never silently pretending demo is live.
    """
    settings = get_settings()
    if requested_mode == "live" and settings.anthropic_api_key:
        from revenueflowai.agents.providers.live import AnthropicQuestionPlanner

        return AnthropicQuestionPlanner(settings.anthropic_api_key), "live"
    return DemoQuestionPlanner(), "demo"


def _prior_entities(evidence: dict | None) -> dict[str, str]:
    entities: dict[str, str] = {}
    for item in (evidence or {}).get("items", []):
        key = _RECORD_TYPE_TO_ENTITY.get(item.get("record_type", ""))
        if key and key not in entities:
            entities[key] = item["record_id"]
    return entities


class InvestigateRequest(BaseModel):
    business_unit_id: UUID
    question: str
    conversation_id: UUID | None = None
    customer_id_hint: str | None = None
    mode: str = "demo"  # "demo" | "live"


class EvidenceOut(BaseModel):
    source_type: str
    record_type: str
    record_id: str


class FindingOut(BaseModel):
    statement: str
    evidence: list[EvidenceOut]


class MetricOut(BaseModel):
    name: str
    value: str
    unit_or_currency: str
    calculation_provenance: str


class SpecialistStatusOut(BaseModel):
    domain: str
    status: str
    unavailable_reason: str | None


class InvestigateResponse(BaseModel):
    conversation_id: UUID
    summary: str
    provider_mode: str
    findings: list[FindingOut]
    metrics: list[MetricOut]
    specialist_status: list[SpecialistStatusOut]
    evidence: list[EvidenceOut]
    missing_data: list[str]
    dataset_version_id: UUID | None
    as_of_date: str


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate(
    body: InvestigateRequest,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> InvestigateResponse:
    assert_business_unit_access(app_user, body.business_unit_id)

    dataset_version = await get_active_dataset_version(
        session, app_user.organization_id, body.business_unit_id
    )
    if dataset_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "no_active_dataset", "message": "Upload and activate a CSV bundle first."},
        )

    prior_entities: dict[str, str] | None = None
    if body.conversation_id:
        conversation = (
            await session.execute(
                select(Conversation).where(
                    Conversation.id == body.conversation_id,
                    Conversation.organization_id == app_user.organization_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "not_found"})
        last_assistant = (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation.id, ChatMessage.role == "assistant")
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        prior_entities = _prior_entities(last_assistant.evidence if last_assistant else None)
    else:
        conversation = Conversation(
            organization_id=app_user.organization_id, business_unit_id=body.business_unit_id,
            created_by_user_id=app_user.id, dataset_version_id=dataset_version.id,
            title=body.question[:256],
        )
        session.add(conversation)
        await session.flush()

    session.add(ChatMessage(conversation_id=conversation.id, role="user", content=body.question))

    planner, resolved_mode = _get_planner(body.mode)
    handlers: dict[Domain, SpecialistHandler] = {
        "order": make_order_handler(session),
        "ar": make_ar_handler(session),
        "cash": make_cash_handler(session),
    }
    transport = InternalAgentTransport(handlers=handlers)

    scope = InvestigationScope(
        organization_id=app_user.organization_id, business_unit_id=body.business_unit_id,
        dataset_version_id=dataset_version.id, business_as_of_date=dataset_version.snapshot_date,
        source_snapshot_date=dataset_version.snapshot_date, actor_user_id=app_user.id,
        provider_mode=resolved_mode,
    )

    result = await run_investigation(
        scope, body.question, transport, planner, body.customer_id_hint, prior_entities
    )

    findings = [
        FindingOut(
            statement=f.statement,
            evidence=[EvidenceOut(source_type=e.source_type, record_type=e.record_type, record_id=e.record_id)
                      for e in f.evidence],
        )
        for f in result.findings
    ]
    metrics = [
        MetricOut(name=m.name, value=m.value, unit_or_currency=m.unit_or_currency,
                  calculation_provenance=m.calculation_provenance)
        for m in result.metrics
    ]
    evidence = [EvidenceOut(source_type=e.source_type, record_type=e.record_type, record_id=e.record_id)
                for e in result.evidence]
    specialist_status = [
        SpecialistStatusOut(domain=s.domain, status=s.status, unavailable_reason=s.unavailable_reason)
        for s in result.specialist_status
    ]

    session.add(ChatMessage(
        conversation_id=conversation.id, role="assistant", content=result.summary,
        provider_mode=resolved_mode,
        specialist_status={"items": [s.model_dump() for s in specialist_status]},
        evidence={
            "items": [e.model_dump() for e in evidence],
            "findings": [f.model_dump() for f in findings],
            "metrics": [m.model_dump() for m in metrics],
        },
        missing_data={"items": list(result.missing_data)},
    ))
    await session.commit()

    return InvestigateResponse(
        conversation_id=conversation.id, summary=result.summary, provider_mode=resolved_mode,
        findings=findings, metrics=metrics, specialist_status=specialist_status, evidence=evidence,
        missing_data=list(result.missing_data),
        dataset_version_id=result.dataset_version_id, as_of_date=result.as_of_date,
    )


class MessageOut(BaseModel):
    role: str
    content: str
    provider_mode: str | None
    findings: list[FindingOut] = []
    metrics: list[MetricOut] = []
    specialist_status: list[SpecialistStatusOut] = []
    evidence: list[EvidenceOut] = []
    missing_data: list[str] = []


def _to_message_out(m: ChatMessage) -> MessageOut:
    payload = m.evidence or {}
    return MessageOut(
        role=m.role, content=m.content, provider_mode=m.provider_mode,
        findings=[FindingOut(**f) for f in payload.get("findings", [])],
        metrics=[MetricOut(**x) for x in payload.get("metrics", [])],
        specialist_status=[SpecialistStatusOut(**s) for s in (m.specialist_status or {}).get("items", [])],
        evidence=[EvidenceOut(**e) for e in payload.get("items", [])],
        missing_data=(m.missing_data or {}).get("items", []),
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[MessageOut]:
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.organization_id == app_user.organization_id
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "not_found"})
    assert_business_unit_access(app_user, conversation.business_unit_id)

    messages = (
        (await session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        ))
        .scalars()
        .all()
    )
    return [_to_message_out(m) for m in messages]
