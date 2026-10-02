"""Internal follow-up task endpoints. intent.md: approval records a
decision only — never implies an ERP write, payment, or email. Every
transition is written to the append-only audit_events table.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.db import get_session
from revenueflowai.models.ingestion import AuditEvent
from revenueflowai.models.tasks import TASK_STATES, FollowUpTask, TaskComment
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

VIEW_ROLES = ("admin", "analyst", "approver", "viewer")
WRITE_ROLES = ("admin", "analyst", "approver")
DECISION_ROLES = ("admin", "approver")

# Transitions a non-admin/approver decision role may apply directly.
ALLOWED_TRANSITIONS = {
    "proposed": {"approved", "rejected", "in_progress"},
    "in_progress": {"resolved", "rejected"},
    "approved": {"in_progress", "resolved"},
}


class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: str
    status: str
    assignee_user_id: UUID | None
    related_record_type: str | None
    related_record_id: str | None
    created_at: datetime
    resolved_at: datetime | None


def _to_response(task: FollowUpTask) -> TaskResponse:
    return TaskResponse(
        id=task.id, title=task.title, description=task.description, status=task.status,
        assignee_user_id=task.assignee_user_id, related_record_type=task.related_record_type,
        related_record_id=task.related_record_id, created_at=task.created_at, resolved_at=task.resolved_at,
    )


class CreateTaskRequest(BaseModel):
    business_unit_id: UUID
    title: str
    description: str = ""
    assignee_user_id: UUID | None = None
    related_record_type: str | None = None
    related_record_id: str | None = None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: CreateTaskRequest,
    app_user: AppUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    assert_business_unit_access(app_user, body.business_unit_id)

    task = FollowUpTask(
        organization_id=app_user.organization_id, business_unit_id=body.business_unit_id,
        created_by_user_id=app_user.id, assignee_user_id=body.assignee_user_id,
        title=body.title, description=body.description,
        related_record_type=body.related_record_type, related_record_id=body.related_record_id,
    )
    session.add(task)
    await session.flush()
    session.add(AuditEvent(
        actor_user_id=app_user.id, organization_id=app_user.organization_id,
        event_type="task.created", outcome="success",
        subject_type="follow_up_task", subject_id=str(task.id),
        detail={"title": body.title, "business_unit_id": str(body.business_unit_id)},
    ))
    await session.commit()
    return _to_response(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    business_unit_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[TaskResponse]:
    assert_business_unit_access(app_user, business_unit_id)

    tasks = (
        (await session.execute(
            select(FollowUpTask)
            .where(FollowUpTask.business_unit_id == business_unit_id)
            .order_by(FollowUpTask.created_at.desc())
        ))
        .scalars()
        .all()
    )
    return [_to_response(t) for t in tasks]


async def _get_task_or_404(session: AsyncSession, app_user: AppUser, task_id: UUID) -> FollowUpTask:
    task = (
        await session.execute(
            select(FollowUpTask).where(
                FollowUpTask.id == task_id, FollowUpTask.organization_id == app_user.organization_id
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "not_found"})
    assert_business_unit_access(app_user, task.business_unit_id)
    return task


class TransitionRequest(BaseModel):
    new_status: str


@router.post("/{task_id}/transition", response_model=TaskResponse)
async def transition_task(
    task_id: UUID,
    body: TransitionRequest,
    app_user: AppUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    if body.new_status not in TASK_STATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "invalid_status", "message": f"Unknown status '{body.new_status}'."},
        )

    task = await _get_task_or_404(session, app_user, task_id)

    is_decision = body.new_status in ("approved", "rejected")
    if is_decision and app_user.role not in DECISION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "role_not_permitted",
                "message": "Only an approver or admin may approve/reject a task.",
            },
        )

    allowed = ALLOWED_TRANSITIONS.get(task.status, set())
    if body.new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "invalid_transition",
                "message": f"Cannot move task from '{task.status}' to '{body.new_status}'.",
            },
        )

    old_status = task.status
    task.status = body.new_status
    if body.new_status == "resolved":
        task.resolved_at = datetime.now(UTC)

    session.add(AuditEvent(
        actor_user_id=app_user.id, organization_id=app_user.organization_id,
        event_type="task.transitioned", outcome="success",
        subject_type="follow_up_task", subject_id=str(task.id),
        detail={"from": old_status, "to": body.new_status},
    ))
    await session.commit()
    return _to_response(task)


class CreateCommentRequest(BaseModel):
    body: str


class CommentResponse(BaseModel):
    id: UUID
    author_user_id: UUID
    body: str
    created_at: datetime


@router.post("/{task_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def add_comment(
    task_id: UUID,
    body: CreateCommentRequest,
    app_user: AppUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> CommentResponse:
    task = await _get_task_or_404(session, app_user, task_id)

    comment = TaskComment(task_id=task.id, author_user_id=app_user.id, body=body.body)
    session.add(comment)
    await session.commit()
    return CommentResponse(
        id=comment.id, author_user_id=comment.author_user_id,
        body=comment.body, created_at=comment.created_at,
    )


@router.get("/{task_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    task_id: UUID,
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[CommentResponse]:
    await _get_task_or_404(session, app_user, task_id)

    comments = (
        (await session.execute(
            select(TaskComment).where(TaskComment.task_id == task_id).order_by(TaskComment.created_at)
        ))
        .scalars()
        .all()
    )
    return [
        CommentResponse(id=c.id, author_user_id=c.author_user_id, body=c.body, created_at=c.created_at)
        for c in comments
    ]
