from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket


class SupportService:
    @staticmethod
    def create_ticket(
        session: Session,
        *,
        tenant_id: str,
        customer_id: str,
        subject: str,
        description: str,
        order_id: str | None = None,
    ) -> SupportTicket:
        ticket_id = f"TKT-{len(session.query(SupportTicket).all()) + 1:05d}"
        ticket = SupportTicket(
            id=ticket_id,
            tenant_id=tenant_id,
            customer_id=customer_id,
            order_id=order_id,
            subject=subject,
            description=description,
            status="open",
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return ticket
