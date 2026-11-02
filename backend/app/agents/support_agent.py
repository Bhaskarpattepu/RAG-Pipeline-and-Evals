from __future__ import annotations

import asyncio
import re
from time import perf_counter
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph
from mcp.shared.exceptions import MCPError

from app.observability.langsmith import trace_ai_operation
from app.services.mcp_client import call_mcp_tool
from app.services.rag_service import RAGService


class AgentState(TypedDict):
    messages: list[str]
    user_message: str
    conversation_id: str
    tenant_id: str
    user_id: str
    retrieved_documents: list[dict[str, Any]]
    selected_tools: list[str]
    tool_results: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    pending_approval: dict[str, Any] | None
    step_count: int
    errors: list[str]
    final_answer: str | None


class SupportAgent:
    def __init__(self) -> None:
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("understand_request", self.understand_request)
        workflow.add_node("retrieve_context", self.retrieve_context)
        workflow.add_node("decide_tool", self.decide_tool)
        workflow.add_node("execute_tool", self.execute_tool)
        workflow.add_node("finalize_response", self.finalize_response)
        workflow.set_entry_point("understand_request")
        workflow.add_edge("understand_request", "retrieve_context")
        workflow.add_edge("retrieve_context", "decide_tool")
        workflow.add_edge("decide_tool", "execute_tool")
        workflow.add_edge("execute_tool", "finalize_response")
        workflow.add_edge("finalize_response", END)
        return workflow.compile()

    def _seed_demo_documents(self, tenant_id: str) -> None:
        service = RAGService(use_qdrant=False)
        db = service._memory_index.setdefault(tenant_id, [])
        if db:
            return
        sample_docs = [
            {
                "chunk_id": f"{tenant_id}:refund-policy",
                "document_id": f"{tenant_id}:doc-1",
                "tenant_id": tenant_id,
                "filename": "refund-policy.md",
                "content": (
                    "Refunds for eligible subscriptions are processed within 7 business days. "
                    "Manual review is required for duplicate payments or chargebacks. Customers "
                    "may request a refund within 30 days of the original purchase date."
                ),
                "content_hash": "refund-policy",
                "metadata": {"tenant_id": tenant_id, "filename": "refund-policy.md", "chunk_index": 0},
            },
            {
                "chunk_id": f"{tenant_id}:payment-failures",
                "document_id": f"{tenant_id}:doc-2",
                "tenant_id": tenant_id,
                "filename": "payment-failures.md",
                "content": (
                    "Payment failures caused by expired cards or insufficient funds must be "
                    "retried manually. A human review is required before creating a refund or "
                    "support ticket."
                ),
                "content_hash": "payment-failures",
                "metadata": {"tenant_id": tenant_id, "filename": "payment-failures.md", "chunk_index": 0},
            },
        ]
        db.extend(sample_docs)

    def understand_request(self, state: AgentState) -> AgentState:
        state["step_count"] += 1
        state["messages"].append(f"Intent recognized for: {state['user_message'][:120]}")
        return state

    def retrieve_context(self, state: AgentState) -> AgentState:
        self._seed_demo_documents(state["tenant_id"])
        query = state["user_message"]
        start = perf_counter()
        with trace_ai_operation(
            "support_policy_retrieval",
            inputs={"query_length": len(query)},
            conversation_id=state["conversation_id"],
            tenant_id=state["tenant_id"],
        ) as trace_run:
            state["retrieved_documents"] = RAGService(use_qdrant=False).search_policy_context(
                query,
                tenant_id=state["tenant_id"],
                top_k=3,
            )
            latency_ms = int((perf_counter() - start) * 1000)
            if trace_run is not None:
                trace_run.outputs = {
                    "document_count": len(state["retrieved_documents"]),
                    "latency_ms": latency_ms,
                }
        if self._policy_requested(query):
            state["tool_events"].append(
                {
                    "tool": "retrieve_policy",
                    "status": "completed" if state["retrieved_documents"] else "no_results",
                    "executed": True,
                    "latency_ms": latency_ms,
                    "result_count": len(state["retrieved_documents"]),
                }
            )
        return state

    @staticmethod
    def _policy_requested(message: str) -> bool:
        return bool(
            re.search(r"\b(policy|eligible|chargeback|retry|retries)\b", message, re.IGNORECASE)
            or (
                re.search(r"\brefund\b", message, re.IGNORECASE)
                and not re.search(r"\bREF-[A-Z0-9-]+\b", message, re.IGNORECASE)
            )
        )

    @staticmethod
    def _customer_id(message: str) -> str | None:
        match = re.search(r"\bCUST-[A-Z0-9-]+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _order_id(message: str) -> str | None:
        match = re.search(r"\bORD-[A-Z0-9-]+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _refund_id(message: str) -> str | None:
        match = re.search(r"\bREF-[A-Z0-9-]+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _product_id(message: str) -> str | None:
        match = re.search(r"\b(?:PROD|SKU)-[A-Z0-9-]+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _user_id(message: str) -> str | None:
        match = re.search(r"\bUSER-[A-Z0-9-]+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    def decide_tool(self, state: AgentState) -> AgentState:
        request = state["user_message"]
        lowered = request.lower()
        tools: list[str] = []

        order_lookup_requested = bool(
            re.search(
                r"\b(order status|check (?:the )?order|look up (?:the )?order|investigate (?:the )?order)\b",
                lowered,
            )
            or (
                self._order_id(request)
                and (
                    re.search(r"\bwhere is\b", lowered)
                    or re.search(
                        r"\bORD-[A-Z0-9-]+\s+(?:has\s+)?(?:failed|failure)\b",
                        request,
                        re.IGNORECASE,
                    )
                )
            )
        )
        if order_lookup_requested and self._order_id(request):
            tools.append("get_order_status")
        if re.search(r"\b(payment|charge|charged|failed|transaction)\b", lowered) and self._order_id(request):
            tools.append("get_payment_status")
        if self._refund_id(request):
            tools.append("get_refund_status")
        if self._customer_id(request) and (
            re.search(r"\b(account|details|profile|lookup)\b", lowered)
            or (re.search(r"\blook up\b", lowered) and re.search(r"\bcustomer\b", lowered))
        ):
            tools.append("get_customer_details")
        if self._user_id(request) and re.search(r"\b(user|account|details|profile|lookup)\b", lowered):
            tools.append("get_user_details")
        product_id = self._product_id(request)
        if product_id and re.search(r"\b(product|price|stock|inventory|availability|sku)\b", lowered):
            tools.append("get_product_details")
        elif re.search(r"\b(products|catalog|inventory)\b", lowered):
            tools.append("search_products")
        if re.search(r"\b(search|find|existing)\b", lowered) and re.search(r"\btickets?\b", lowered):
            tools.append("search_support_tickets")
        if self._policy_requested(request):
            tools.append("retrieve_policy")

        ticket_requested = bool(
            re.search(
                r"\b(create|created|creating|open|opened|prepare|prepared|preparing|submit|submitted|raise|raised)\b",
                lowered,
            )
            and re.search(r"\btickets?\b", lowered)
        )
        state["selected_tools"] = list(dict.fromkeys(tools))
        state["pending_approval"] = None
        if ticket_requested:
            state["pending_approval"] = {
                "action": "create_support_ticket",
                "status": "awaiting_approval",
                "reason": "A human approval is required before creating a support ticket.",
                "parameters": {
                    "customer_id": self._customer_id(request),
                    "summary": "Support investigation",
                    "description": request,
                },
            }
        state["messages"].append(f"Selected tools: {', '.join(state['selected_tools']) or 'none'}")
        return state

    def execute_tool(self, state: AgentState) -> AgentState:
        message = state["user_message"]
        for selected_tool in state["selected_tools"]:
            if selected_tool == "retrieve_policy":
                continue

            arguments: dict[str, Any]
            if selected_tool in {"get_order_status", "get_payment_status"}:
                arguments = {"order_id": self._order_id(message), "tenant_id": state["tenant_id"]}
            elif selected_tool == "get_refund_status":
                arguments = {"refund_id": self._refund_id(message)}
            elif selected_tool in {"get_customer_details", "search_support_tickets"}:
                arguments = {
                    "customer_id": self._customer_id(message),
                    "tenant_id": state["tenant_id"],
                }
            elif selected_tool == "get_user_details":
                arguments = {"user_id": self._user_id(message), "tenant_id": state["tenant_id"]}
            elif selected_tool == "get_product_details":
                arguments = {"product_id": self._product_id(message), "tenant_id": state["tenant_id"]}
            elif selected_tool == "search_products":
                arguments = {"query": message, "tenant_id": state["tenant_id"]}
            else:
                continue

            started_at = perf_counter()
            event: dict[str, Any] = {"tool": selected_tool, "executed": True}
            with trace_ai_operation(
                "support_tool_execution",
                inputs={"tool": selected_tool, "argument_names": sorted(arguments)},
                conversation_id=state["conversation_id"],
                tenant_id=state["tenant_id"],
            ) as trace_run:
                try:
                    result = asyncio.run(call_mcp_tool(selected_tool, arguments))
                    latency_ms = int((perf_counter() - started_at) * 1000)
                    tool_payload = result.get("result", {})
                    tool_error = bool(
                        tool_payload.get("is_error")
                        or (
                            isinstance(tool_payload.get("structured_content"), dict)
                            and tool_payload["structured_content"].get("error")
                        )
                    )
                    event.update(
                        {
                            "status": "failed" if tool_error else "completed",
                            "latency_ms": latency_ms,
                        }
                    )
                    if tool_error:
                        state["errors"].append(f"{selected_tool}: tool reported an error")
                    state["tool_results"].append(
                        {"tool": selected_tool, "result": result.get("result"), "latency_ms": latency_ms}
                    )
                    if trace_run is not None:
                        trace_run.outputs = {
                            "status": event["status"],
                            "latency_ms": latency_ms,
                        }
                except (
                    MCPError,
                    OSError,
                    RuntimeError,
                    ValueError,
                    TimeoutError,
                    asyncio.SubprocessError,
                    ExceptionGroup,
                ) as exc:
                    latency_ms = int((perf_counter() - started_at) * 1000)
                    event.update({"status": "failed", "latency_ms": latency_ms, "error": str(exc)})
                    state["errors"].append(f"{selected_tool}: {exc}")
                    state["tool_results"].append(
                        {
                            "tool": selected_tool,
                            "result": {"error": str(exc)},
                            "latency_ms": latency_ms,
                        }
                    )
                    if trace_run is not None:
                        trace_run.outputs = {"status": "failed", "latency_ms": latency_ms}
            state["tool_events"].append(event)

        if state["pending_approval"]:
            state["tool_events"].append(
                {
                    "tool": "create_support_ticket",
                    "status": "approval_required",
                    "executed": False,
                }
            )
        return state

    def finalize_response(self, state: AgentState) -> AgentState:
        policy_text = "\n".join(doc.get("content", "") for doc in state["retrieved_documents"])
        tool_summary = "\n".join(
            f"- {item.get('tool', 'unknown')}: {item.get('result', {})}"
            for item in state["tool_results"]
        )
        if state["pending_approval"]:
            summary = (
                "Approval required before creating a support ticket. No ticket was created. "
                f"Policy context: {policy_text[:300]}\n{tool_summary}"
            )
        else:
            summary = (
                "I reviewed the requested business context. "
                f"Policy context: {policy_text[:300]}\n{tool_summary}"
            )
        if state["errors"]:
            summary += "\nTool errors: " + "; ".join(state["errors"])
        state["final_answer"] = summary.strip()
        return state

    def run(self, message: str, tenant_id: str = "tenant-demo", user_id: str = "support-agent") -> dict[str, Any]:
        conversation_id = f"conv-{uuid4()}"
        started_at = perf_counter()
        state: AgentState = {
            "messages": [message],
            "user_message": message,
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "retrieved_documents": [],
            "selected_tools": [],
            "tool_results": [],
            "tool_events": [],
            "pending_approval": None,
            "step_count": 0,
            "errors": [],
            "final_answer": None,
        }
        with trace_ai_operation(
            "support_agent_run",
            inputs={"message_length": len(message)},
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
        ) as trace_run:
            result = self.graph.invoke(state)
            latency_ms = int((perf_counter() - started_at) * 1000)
            if trace_run is not None:
                trace_run.outputs = {
                    "latency_ms": latency_ms,
                    "tool_events": result["tool_events"],
                    "approval_required": result["pending_approval"] is not None,
                    "error_count": len(result["errors"]),
                }
        return {
            "conversation_id": result["conversation_id"],
            "tenant_id": result["tenant_id"],
            "user_id": result["user_id"],
            "final_answer": result["final_answer"],
            "pending_approval": result.get("pending_approval"),
            "tool_results": result.get("tool_results", []),
            "tool_events": result["tool_events"],
            "latency_ms": latency_ms,
        }
