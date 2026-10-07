from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .semantic_assessor import (
    SemanticAssessment,
    SemanticAssessmentRequest,
    parse_semantic_assessment,
)


@dataclass(frozen=True)
class SemanticModelConfig:
    base_url: str
    api_key: str | None
    model: str
    timeout_seconds: float = 60.0
    max_tokens: int = 2048
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> "SemanticModelConfig":
        base_url = os.environ.get("UCG_MODEL_BASE_URL", "").strip()
        model = os.environ.get("UCG_SEMANTIC_MODEL", "").strip()
        if not base_url:
            raise RuntimeError("UCG_MODEL_BASE_URL is not configured")
        if not model:
            raise RuntimeError("UCG_SEMANTIC_MODEL is not configured")
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=os.environ.get("UCG_MODEL_API_KEY"),
            model=model,
            timeout_seconds=float(os.environ.get("UCG_MODEL_TIMEOUT", "60")),
            max_tokens=int(os.environ.get("UCG_MODEL_MAX_TOKENS", "2048")),
            temperature=float(os.environ.get("UCG_MODEL_TEMPERATURE", "0")),
        )


@dataclass(frozen=True)
class SemanticModelRun:
    status: str
    model: str
    provider: str
    raw_response: str | None
    latency_ms: float
    error: str | None = None


class OpenAICompatibleSemanticAssessor:
    """Real semantic assessor using an OpenAI-compatible chat endpoint."""

    name = "openai-compatible-semantic-v0.1"

    def __init__(self, config: SemanticModelConfig):
        self.config = config

    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def build_payload(self, request: SemanticAssessmentRequest) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
        }

    def assess(
        self,
        request: SemanticAssessmentRequest,
    ) -> tuple[tuple[SemanticAssessment, ...], SemanticModelRun]:
        started = time.perf_counter()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        body = json.dumps(self.build_payload(request)).encode("utf-8")
        http_request = Request(
            self._endpoint(),
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            run = SemanticModelRun(
                status="unavailable",
                model=self.config.model,
                provider="openai-compatible",
                raw_response=None,
                latency_ms=latency_ms,
                error=str(exc),
            )
            raise RuntimeError(f"semantic model unavailable: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("semantic model returned an invalid chat response") from exc

        assessments = parse_semantic_assessment(request, str(content))
        run = SemanticModelRun(
            status="complete",
            model=self.config.model,
            provider="openai-compatible",
            raw_response=raw,
            latency_ms=latency_ms,
        )
        return assessments, run
