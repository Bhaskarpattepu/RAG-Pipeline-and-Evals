from __future__ import annotations

from time import perf_counter
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.observability.langsmith import trace_ai_operation


class LLMService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def available(self) -> bool:
        return self.client is not None

    def chat(self, message: str, trace_metadata: dict[str, Any] | None = None) -> dict:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        start = perf_counter()
        metadata = {
            "model": settings.openai_model,
            "input_length": len(message),
            **(trace_metadata or {}),
        }
        with trace_ai_operation(
            "openai_chat",
            inputs={"input_length": len(message)},
            **metadata,
        ) as trace_run:
            response = self.client.responses.create(
                model=settings.openai_model,
                input=message,
            )
            latency_ms = int((perf_counter() - start) * 1000)
            usage = getattr(response, "usage", None)
            usage_payload = None
            if usage is not None:
                usage_payload = {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    "total_tokens": getattr(usage, "total_tokens", 0),
                }
            if trace_run is not None:
                trace_run.outputs = {
                    "model": settings.openai_model,
                    "latency_ms": latency_ms,
                    "usage": usage_payload,
                }

        return {
            "response": response.output_text,
            "model": settings.openai_model,
            "request_id": getattr(response, "id", None),
            "latency_ms": latency_ms,
            "usage": usage_payload,
        }
