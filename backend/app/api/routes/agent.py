from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.support_agent import SupportAgent
from app.api.deps import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.schemas.agent import AgentRunRequest, AgentRunResponse
from app.services.approval_service import ApprovalService

router = APIRouter(tags=["agent"])


@router.post("/agent/run", response_model=AgentRunResponse)
def run_agent(
    payload: AgentRunRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AgentRunResponse:
    agent = SupportAgent()
    result = agent.run(payload.message, tenant_id=payload.tenant_id, user_id=payload.user_id)
    pending_approval = result.get("pending_approval")
    if pending_approval:
        parameters = pending_approval["parameters"]
        customer_ref = parameters.get("customer_id")
        order_number = parameters.get("order_id")
        order = None
        if order_number:
            order = (
                db.query(Order)
                .filter(
                    Order.order_number == order_number,
                    Order.tenant_id == payload.tenant_id,
                )
                .first()
            )
        customer = None
        if order is not None:
            customer = (
                db.query(Customer)
                .filter(
                    Customer.id == order.customer_id,
                    Customer.tenant_id == payload.tenant_id,
                )
                .first()
            )
        elif customer_ref:
            customer = (
                db.query(Customer)
                .filter(
                    Customer.tenant_id == payload.tenant_id,
                    (Customer.id == customer_ref)
                    | (Customer.customer_code == customer_ref),
                )
                .first()
            )

        if (
            customer is None
            or (order_number and order is None)
            or (customer_ref and customer.customer_code != customer_ref and customer.id != customer_ref)
            or (order is not None and customer.id != order.customer_id)
        ):
            result["pending_approval"] = None
            result["final_answer"] = (
                "I could not verify the customer or order. Please provide a valid identifier; "
                "no approval request or ticket was created."
            )
            for event in result["tool_events"]:
                if event.get("tool") == "create_support_ticket":
                    event["status"] = "clarification_required"
        else:
            approval = ApprovalService.create_ticket_request(
                db,
                tenant_id=payload.tenant_id,
                user_id=payload.user_id,
                customer_id=customer.id,
                order_id=order.order_number if order is not None else None,
                description=str(parameters["description"]),
            )
            result["pending_approval"] = {
                "id": approval.id,
                "status": approval.status,
                "target_id": approval.target_id,
                "action": approval.action,
            }
            result["final_answer"] += (
                f"\nApproval request {approval.id} is pending. No ticket was created."
            )

    return AgentRunResponse(
        conversation_id=result["conversation_id"],
        tenant_id=result["tenant_id"],
        user_id=result["user_id"],
        final_answer=result["final_answer"],
        pending_approval=result.get("pending_approval"),
        tool_results=result.get("tool_results", []),
        tool_events=result.get("tool_events", []),
        latency_ms=result["latency_ms"],
    )
