from app.agents.support_agent import SupportAgent


def test_agent_requires_approval_for_ticket_creation() -> None:
    agent = SupportAgent()
    result = agent.run("Customer CUST-1001 reports a failed order and wants a support ticket created.")
    assert "conversation_id" in result
    assert result["pending_approval"] is not None
    assert "support ticket" in result["final_answer"].lower()


def test_agent_uses_policy_context() -> None:
    agent = SupportAgent()
    result = agent.run("Check the refund policy for order ORD-2005.")
    assert result["final_answer"]
    assert "refund" in result["final_answer"].lower()


def test_agent_checks_multiple_tools_but_never_creates_ticket_before_approval(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run(
        "Order ORD-2005 payment failed. Check the order and payment and create a support ticket."
    )

    assert calls == ["get_order_status", "get_payment_status"]
    assert result["pending_approval"]["action"] == "create_support_ticket"
    assert not any(
        event["tool"] == "create_support_ticket" and event["executed"]
        for event in result["tool_events"]
    )
    assert any(
        event["tool"] == "create_support_ticket"
        and event["status"] == "approval_required"
        and event["executed"] is False
        for event in result["tool_events"]
    )


def test_agent_routes_payment_status_without_order_lookup(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Check the payment status for order ORD-2005.")

    assert calls == ["get_payment_status"]
    assert [event["tool"] for event in result["tool_events"] if event["executed"]] == [
        "get_payment_status"
    ]


def test_agent_does_not_lookup_order_for_payment_failure_policy_question(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    SupportAgent().run(
        "Check payment for order ORD-2005 and explain what policy says after a failed retry."
    )

    assert calls == ["get_payment_status"]


def test_agent_routes_product_and_user_lookups_to_mcp(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append((tool_name, arguments or {}))
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    agent = SupportAgent()
    product_result = agent.run("Check product stock and price for SKU-1001.")
    user_result = agent.run("Look up user USER-1001 details and role.")

    assert calls == [
        ("get_product_details", {"product_id": "SKU-1001", "tenant_id": "tenant-demo"}),
        ("get_user_details", {"user_id": "USER-1001", "tenant_id": "tenant-demo"}),
    ]
    assert product_result["tool_events"][0]["status"] == "completed"
    assert user_result["tool_events"][0]["status"] == "completed"
