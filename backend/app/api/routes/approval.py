import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.approval import ApprovalRequest
from app.schemas.approval import ApprovalCreate, ApprovalDecision, ApprovalRead
from app.services.approval_service import ApprovalService

router = APIRouter(tags=["approval"])


@router.post("/approvals", response_model=ApprovalRead)
def create_approval(
    payload: ApprovalCreate, db: Annotated[Session, Depends(get_db)]
) -> ApprovalRead:
    approval = ApprovalService.create_request(
        db,
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        action=payload.action,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        payload=payload.payload,
    )
    return ApprovalRead(
        id=approval.id,
        tenant_id=approval.tenant_id,
        user_id=approval.user_id,
        action=approval.action,
        target_type=approval.target_type,
        target_id=approval.target_id,
        status=approval.status,
        reason=approval.reason,
        payload=json.loads(approval.payload or "{}"),
        created_at=approval.created_at.isoformat(),
        resolved_at=approval.resolved_at.isoformat() if approval.resolved_at else None,
    )


@router.patch("/approvals/{approval_id}", response_model=ApprovalRead)
def resolve_approval(
    approval_id: str,
    payload: ApprovalDecision,
    db: Annotated[Session, Depends(get_db)],
) -> ApprovalRead:
    try:
        approval = ApprovalService.resolve_request(
            db,
            approval_id=approval_id,
            decision=payload.decision,
            approver_id=payload.approver_id,
            comment=payload.comment,
        )
    except ValueError as exc:
        error_status = 404 if str(exc) in {"Approval request not found"} else 409
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc

    return ApprovalRead(
        id=approval.id,
        tenant_id=approval.tenant_id,
        user_id=approval.user_id,
        action=approval.action,
        target_type=approval.target_type,
        target_id=approval.target_id,
        status=approval.status,
        reason=approval.reason,
        payload=json.loads(approval.payload or "{}"),
        created_at=approval.created_at.isoformat(),
        resolved_at=approval.resolved_at.isoformat() if approval.resolved_at else None,
    )


@router.get("/approvals", response_model=list[ApprovalRead])
def list_approvals(db: Annotated[Session, Depends(get_db)]) -> list[ApprovalRead]:
    rows = db.query(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).all()
    return [
        ApprovalRead(
            id=row.id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            status=row.status,
            reason=row.reason,
            payload=json.loads(row.payload or "{}"),
            created_at=row.created_at.isoformat(),
            resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
        )
        for row in rows
    ]
