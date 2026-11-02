from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    tenant_id: str = "tenant-demo"
    user_id: str = "support-agent"


class AgentRunResponse(BaseModel):
    conversation_id: str
    tenant_id: str
    user_id: str
    final_answer: str
    pending_approval: dict[str, object] | None = None
    tool_results: list[dict[str, object]] = Field(default_factory=list)
    tool_events: list[dict[str, object]] = Field(default_factory=list)
    latency_ms: int = 0
