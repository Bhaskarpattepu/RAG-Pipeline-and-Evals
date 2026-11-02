from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.db.session import engine


def _server_path() -> Path:
    return Path(__file__).resolve().parents[3] / "mcp-server" / "server.py"


def _server_environment() -> dict[str, str]:
    environment = dict(os.environ)
    database_url = engine.url
    if database_url.get_backend_name() == "sqlite" and database_url.database not in (None, ":memory:"):
        database_path = Path(database_url.database).resolve()
        environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        environment["USE_SQLITE_FALLBACK"] = "0"
    else:
        environment["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    return environment


async def call_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    server_path = _server_path()
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env=_server_environment(),
        cwd=str(server_path.parents[1] / "backend"),
    )

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        response = await session.call_tool(tool_name, arguments or {})
        payload: dict[str, Any] = {"tool": tool_name}
        if hasattr(response, "model_dump"):
            payload["result"] = response.model_dump()
        elif hasattr(response, "content"):
            payload["result"] = response.content
        else:
            payload["result"] = response
        return payload
