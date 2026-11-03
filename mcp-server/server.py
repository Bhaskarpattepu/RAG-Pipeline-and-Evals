from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer

BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

import app.models  # noqa: F401 - register SQLAlchemy table models
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import SessionLocal, engine
from app.models.approval import ApprovalRequest
from app.models.customer import Customer
from app.models.support_ticket import SupportTicket
from app.services.commerce_service import CommerceService

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_demo_data(db)

server = MCPServer("enterprise-ai-support")


@server.tool()
def get_customer_details(customer_id: str, tenant_id: str = "tenant-demo") -> dict[str, object]:
    with SessionLocal() as db:
        customer = CommerceService.get_customer(db, customer_id, tenant_id)
    return customer or {"error": "Customer not found", "customer_id": customer_id}


@server.tool()
def get_order_status(order_id: str, tenant_id: str = "tenant-demo") -> dict[str, object]:
    with SessionLocal() as db:
        order = CommerceService.get_order(db, order_id, tenant_id)
    return order or {"error": "Order not found", "order_id": order_id}


@server.tool()
def get_payment_status(order_id: str, tenant_id: str = "tenant-demo") -> dict[str, object]:
    with SessionLocal() as db:
        payment = CommerceService.get_payment(db, order_id, tenant_id)
    return payment or {"error": "Order not found", "order_id": order_id}


@server.tool()
def get_product_details(product_id: str, tenant_id: str = "tenant-demo") -> dict[str, object]:
    with SessionLocal() as db:
        product = CommerceService.get_product(db, product_id, tenant_id)
    return product or {"error": "Product not found", "product_id": product_id}


@server.tool()
def search_products(query: str, tenant_id: str = "tenant-demo") -> list[dict[str, object]]:
    with SessionLocal() as db:
        return CommerceService.search_products(db, query, tenant_id)


@server.tool()
def get_user_details(user_id: str, tenant_id: str = "tenant-demo") -> dict[str, object]:
    with SessionLocal() as db:
        user = CommerceService.get_user(db, user_id, tenant_id)
    return user or {"error": "User not found", "user_id": user_id}


@server.tool()
def get_refund_status(
    refund_id: str, tenant_id: str = "tenant-demo"
) -> dict[str, object]:
    with SessionLocal() as db:
        refund = CommerceService.get_refund(db, refund_id, tenant_id)
    return refund or {"error": "Refund not found.", "refund_id": refund_id}


@server.tool()
def search_support_tickets(
    customer_id: str, tenant_id: str = "tenant-demo"
) -> list[dict[str, str]]:
    with SessionLocal() as db:
        rows = (
            db.query(SupportTicket, Customer)
            .join(Customer, Customer.id == SupportTicket.customer_id)
            .filter(
                SupportTicket.tenant_id == tenant_id,
                Customer.tenant_id == tenant_id,
                Customer.customer_code == customer_id,
            )
            .order_by(SupportTicket.id)
            .limit(100)
            .all()
        )
    return [
        {
            "id": ticket.id,
            "customer_id": customer.customer_code,
            "order_id": ticket.order_id or "",
            "subject": ticket.subject,
            "status": ticket.status,
        }
        for ticket, customer in rows
    ]


@server.tool()
def create_support_ticket(approval_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        approval = (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.action == "create_support_ticket",
                ApprovalRequest.status == "approved",
            )
            .first()
        )
        if approval is None:
            return {"error": "A matching approved ticket request is required"}

        approved_payload = json.loads(approval.payload or "{}")
        ticket_id = approved_payload.get("created_ticket_id")
        if not ticket_id:
            return {"error": "The approved request does not contain a created ticket"}
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        if ticket is None:
            return {"error": "Ticket record for the approved request was not found"}
        return {
            "ticket_id": ticket.id,
            "customer_id": ticket.customer_id,
            "order_id": ticket.order_id or "",
            "status": ticket.status,
        }


@server.tool()
def update_ticket_status(
    ticket_id: str,
    status: Literal["open", "pending", "closed"],
    tenant_id: str = "tenant-demo",
) -> dict[str, str]:
    if status not in {"open", "pending", "closed"}:
        return {"error": "Unsupported ticket status.", "ticket_id": ticket_id}

    with SessionLocal() as db:
        ticket = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.id == ticket_id,
                SupportTicket.tenant_id == tenant_id,
            )
            .first()
        )
        if ticket is None:
            return {"error": "Ticket not found.", "ticket_id": ticket_id}

        ticket.status = status
        db.commit()
        return {"ticket_id": ticket.id, "status": ticket.status}


if __name__ == "__main__":
    server.run(transport="stdio")
