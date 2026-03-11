#!/usr/bin/env python3
"""Model transport abstraction for AOI Council.

Goal:
- Keep AOI Council orchestration provider-agnostic.
- Default to stable HTTP transport.
- Optionally accelerate with OpenAI Responses WebSocket mode.

This module is intentionally lightweight and safe:
- No secrets are logged.
- If OpenAI transport is unavailable (missing key / missing deps), callers should fallback.

SSOT: context/AOI_WEBSOCKET_MODE_ADOPTION_SPEC_V0_1.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Protocol


class TransportError(RuntimeError):
    pass


class ModelTransport(Protocol):
    """A minimal transport surface for 1-in-flight response chains."""

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def close(self) -> None:
        ...


@dataclass
class TransportConfig:
    provider: str = "openai"  # or "anthropic", "gemini", "openrouter", ...
    mode: str = "http"  # http|ws
    store: bool = False
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    ws_url: str = "wss://api.openai.com/v1/responses"
    timeout_s: int = 60


def make_transport(cfg: TransportConfig) -> ModelTransport:
    """Factory with safe fallback behavior.

    NOTE: This factory only returns OpenAI transports today.
    If provider != openai, raise; the caller should fallback to existing runner behavior.
    """

    if cfg.provider != "openai":
        raise TransportError(f"provider_not_supported: {cfg.provider}")

    if cfg.mode == "ws":
        try:
            from openai_responses_ws_transport import OpenAIResponsesWSTransport

            return OpenAIResponsesWSTransport(cfg)
        except Exception as e:
            raise TransportError(f"ws_transport_unavailable: {e}")

    # default
    from openai_responses_http_transport import OpenAIResponsesHTTPTransport

    return OpenAIResponsesHTTPTransport(cfg)
