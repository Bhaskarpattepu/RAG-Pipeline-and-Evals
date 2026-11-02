from typing import Literal

from pydantic import BaseModel, Field


class TicketBase(BaseModel):
    customer_id: str
    order_id: str | None = None
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)


class TicketCreate(TicketBase):
    pass


class TicketRead(TicketBase):
    id: str
    tenant_id: str
    status: str = "open"


class TicketUpdate(BaseModel):
    status: Literal["open", "pending", "closed"] = "open"
