from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatSource(BaseModel):
    filename: str | None = None
    type: Literal["policy", "order", "payment", "product", "user", "customer"]
    id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = None
    tenant_id: str = "tenant-demo"
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    response: str
    model: str
    request_id: str | None = None
    latency_ms: int | None = None
    usage: dict[str, int] | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    pending_approval: dict[str, str] | None = None
