from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.customer import Customer
from app.models.support_ticket import SupportTicket


def _load_mcp_server():
    server_path = Path(__file__).resolve().parents[2] / "mcp-server" / "server.py"
    spec = importlib.util.spec_from_file_location("support_mcp_server_tests", server_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the MCP server module for tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mcp_ticket_tools_use_database_and_refund_lookup_is_explicitly_unavailable() -> None:
    mcp_server = _load_mcp_server()
    customer_id = f"CUST-{uuid4().hex[:12].upper()}"
    ticket_id = f"TKT-{uuid4().hex[:12].upper()}"

    with SessionLocal() as db:
        db.add(
            Customer(
                id=customer_id,
                tenant_id="tenant-demo",
                customer_code=customer_id,
                email=f"{customer_id.lower()}@example.test",
                full_name="MCP Tool Test",
            )
        )
        db.flush()
        db.add(
            SupportTicket(
                id=ticket_id,
                tenant_id="tenant-demo",
                customer_id=customer_id,
                subject="MCP database lookup test",
                description="Temporary row for tool integration tests.",
                status="open",
            )
        )
        db.commit()

    try:
        tickets = mcp_server.search_support_tickets(customer_id)
        assert tickets == [
            {
                "id": ticket_id,
                "customer_id": customer_id,
                "order_id": "",
                "subject": "MCP database lookup test",
                "status": "open",
            }
        ]
        assert mcp_server.search_support_tickets("CUST-NOT-FOUND") == []
        assert mcp_server.search_support_tickets(customer_id, "tenant-not-found") == []
        assert mcp_server.get_refund_status("REF-1005", "tenant-not-found") == {
            "error": "Refund not found.",
            "refund_id": "REF-1005",
        }
        assert mcp_server.update_ticket_status(
            ticket_id, "closed", "tenant-not-found"
        ) == {"error": "Ticket not found.", "ticket_id": ticket_id}

        assert mcp_server.update_ticket_status(ticket_id, "pending") == {
            "ticket_id": ticket_id,
            "status": "pending",
        }
        assert mcp_server.update_ticket_status(ticket_id, "unknown") == {
            "error": "Unsupported ticket status.",
            "ticket_id": ticket_id,
        }
        with SessionLocal() as db:
            ticket = db.scalar(
                select(SupportTicket).where(SupportTicket.id == ticket_id)
            )
            assert ticket is not None
            assert ticket.status == "pending"

        refund_result = mcp_server.get_refund_status("REF-1005")
        assert refund_result == {
            "refund_id": "REF-1005",
            "order_id": "ORD-2005",
            "status": "pending_review",
            "amount": 249.99,
        }
        assert mcp_server.get_refund_status("REF-NOT-FOUND") == {
            "error": "Refund not found.",
            "refund_id": "REF-NOT-FOUND",
        }
    finally:
        with SessionLocal() as db:
            ticket = db.scalar(
                select(SupportTicket).where(SupportTicket.id == ticket_id)
            )
            if ticket is not None:
                db.delete(ticket)
            customer = db.scalar(select(Customer).where(Customer.id == customer_id))
            if customer is not None:
                db.delete(customer)
            db.commit()
