from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.customer import Customer
from app.models.order import Order
from app.models.support_ticket import SupportTicket


class ApprovalService:
    @staticmethod
    def create_ticket_request(
        session: Session,
        *,
        tenant_id: str,
        user_id: str,
        customer_id: str,
        order_id: str | None,
        description: str,
    ) -> ApprovalRequest:
        target_id = order_id or customer_id
        existing = (
            session.query(ApprovalRequest)
            .filter(
                ApprovalRequest.tenant_id == tenant_id,
                ApprovalRequest.action == "create_support_ticket",
                ApprovalRequest.target_id == target_id,
                ApprovalRequest.status == "pending",
            )
            .order_by(ApprovalRequest.created_at.desc())
            .first()
        )
        if existing is not None:
            return existing

        return ApprovalService.create_request(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="create_support_ticket",
            target_type="support_ticket",
            target_id=target_id,
            reason="Human review is required before creating a support ticket.",
            payload={
                "customer_id": customer_id,
                "order_id": order_id,
                "subject": "Customer support investigation",
                "description": description,
            },
        )

    @staticmethod
    def create_request(
        session: Session,
        *,
        tenant_id: str,
        user_id: str,
        action: str,
        target_type: str,
        target_id: str,
        reason: str,
        payload: dict,
    ) -> ApprovalRequest:
        approval_id = f"APR-{uuid4().hex[:8].upper()}"
        approval = ApprovalRequest(
            id=approval_id,
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            status="pending",
            reason=reason,
            payload=json.dumps(payload),
        )
        session.add(approval)
        session.commit()
        session.refresh(approval)
        return approval

    @staticmethod
    def resolve_request(
        session: Session,
        *,
        approval_id: str,
        decision: str,
        approver_id: str,
        comment: str | None = None,
    ) -> ApprovalRequest:
        approval = session.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if approval is None:
            raise ValueError("Approval request not found")
        if approval.status != "pending":
            raise ValueError("Approval request has already been resolved")

        if decision == "approved" and approval.action == "create_support_ticket":
            request_payload = json.loads(approval.payload or "{}")
            customer_id = request_payload.get("customer_id")
            if not customer_id:
                raise ValueError("Ticket approval is missing a customer ID")

            customer = (
                session.query(Customer)
                .filter(
                    Customer.id == customer_id,
                    Customer.tenant_id == approval.tenant_id,
                )
                .first()
            )
            if customer is None:
                raise ValueError("Ticket customer was not found in this tenant")

            order_id = request_payload.get("order_id")
            order = None
            if order_id:
                order = (
                    session.query(Order)
                    .filter(
                        Order.order_number == order_id,
                        Order.tenant_id == approval.tenant_id,
                        Order.customer_id == customer.id,
                    )
                    .first()
                )
                if order is None:
                    raise ValueError("Ticket order was not found for the approved customer")

            ticket_id = f"TKT-{uuid4().hex[:10].upper()}"
            session.add(
                SupportTicket(
                    id=ticket_id,
                    tenant_id=approval.tenant_id,
                    customer_id=customer.id,
                    order_id=order.id if order else None,
                    subject=request_payload.get("subject", "Customer support investigation"),
                    description=request_payload.get("description", ""),
                    status="open",
                )
            )
            request_payload["created_ticket_id"] = ticket_id
            approval.payload = json.dumps(request_payload)

        approval.status = "approved" if decision == "approved" else "rejected"
        approval.resolved_at = datetime.now(UTC)
        if comment:
            approval.reason = f"{approval.reason}\nApprover {approver_id}: {comment}"
        session.commit()
        session.refresh(approval)
        return approval
