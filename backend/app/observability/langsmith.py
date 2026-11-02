from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings


def configure_langsmith() -> None:
    if not settings.langsmith_tracing:
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        os.environ.pop("LANGSMITH_API_KEY", None)
        os.environ.pop("LANGSMITH_PROJECT", None)
        return

    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project


@contextmanager
def trace_ai_operation(
    operation_name: str,
    *,
    inputs: dict[str, Any] | None = None,
    **metadata: Any,
) -> Iterator[Any | None]:
    configure_langsmith()
    if not settings.langsmith_tracing:
        yield None
        return

    try:
        from langsmith import trace
    except ImportError:
        yield None
        return

    with trace(operation_name, inputs=inputs, metadata=metadata) as run_tree:
        yield run_tree
