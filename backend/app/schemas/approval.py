from typing import Literal

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    tenant_id: str = "tenant-demo"
    user_id: str = "support-agent"
    action: str = "create_support_ticket"
    target_type: str = "support_ticket"
    target_id: str = "TKT-1002"
    reason: str = "Manual review required before creating the support ticket."
    payload: dict[str, object] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    approver_id: str = "supervisor-user"
    comment: str | None = None


class ApprovalRead(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    action: str
    target_type: str
    target_id: str
    status: str
    reason: str
    payload: dict[str, object]
    created_at: str
    resolved_at: str | None = None
