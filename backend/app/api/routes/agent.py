from fastapi import APIRouter

from app.agents.support_agent import SupportAgent
from app.schemas.agent import AgentRunRequest, AgentRunResponse

router = APIRouter(tags=["agent"])


@router.post("/agent/run", response_model=AgentRunResponse)
def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
    agent = SupportAgent()
    result = agent.run(payload.message, tenant_id=payload.tenant_id, user_id=payload.user_id)
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
