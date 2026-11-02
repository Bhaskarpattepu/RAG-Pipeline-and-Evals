from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.support_ticket import SupportTicket
from app.schemas.support import TicketCreate, TicketRead, TicketUpdate
from app.services.support_service import SupportService

router = APIRouter(tags=["support"])


@router.get("/tickets", response_model=list[TicketRead])
def list_tickets(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
) -> list[TicketRead]:
    rows = db.query(SupportTicket).limit(limit).all()
    return [
        TicketRead(
            id=row.id,
            tenant_id=row.tenant_id,
            customer_id=row.customer_id,
            order_id=row.order_id,
            subject=row.subject,
            description=row.description,
            status=row.status,
        )
        for row in rows
    ]


@router.post("/tickets", response_model=TicketRead)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)) -> TicketRead:
    ticket = SupportService.create_ticket(
        db,
        tenant_id="tenant-demo",
        customer_id=payload.customer_id,
        subject=payload.subject,
        description=payload.description,
        order_id=payload.order_id,
    )
    return TicketRead(
        id=ticket.id,
        tenant_id=ticket.tenant_id,
        customer_id=ticket.customer_id,
        order_id=ticket.order_id,
        subject=ticket.subject,
        description=ticket.description,
        status=ticket.status,
    )


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(ticket_id: str, payload: TicketUpdate, db: Session = Depends(get_db)) -> TicketRead:
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = payload.status
    db.commit()
    db.refresh(ticket)

    return TicketRead(
        id=ticket.id,
        tenant_id=ticket.tenant_id,
        customer_id=ticket.customer_id,
        order_id=ticket.order_id,
        subject=ticket.subject,
        description=ticket.description,
        status=ticket.status,
    )
