#!/usr/bin/env python3
"""OpenAI Responses API - WebSocket transport (optional accelerator).

Endpoint: wss://api.openai.com/v1/responses

Notes:
- OpenAI runs responses sequentially on a single socket (no multiplexing).
- Connection limit ~60 minutes.
- With store=false/ZDR: cache miss -> previous_response_not_found.

This module is written to be *optional*:
- It requires `websocket-client` (pip install websocket-client).
- If dependency missing, callers must fallback to HTTP.

We keep the API surface minimal: send one response.create and read events until response.completed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from model_transport import TransportConfig, TransportError


class OpenAIResponsesWSTransport:
    def __init__(self, cfg: TransportConfig):
        self.cfg = cfg
        self.api_key = os.environ.get(cfg.api_key_env, "").strip()
        if not self.api_key:
            raise TransportError(f"missing_api_key_env: {cfg.api_key_env}")

        try:
            from websocket import create_connection  # type: ignore
        except Exception as e:
            raise TransportError(f"missing_dependency websocket-client: {e}")

        self._create_connection = create_connection
        self.ws = self._create_connection(
            cfg.ws_url,
            header=[f"Authorization: Bearer {self.api_key}"],
        )

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # WebSocket mode uses `type=response.create` envelopes.
        body = dict(payload)
        body.setdefault("store", bool(self.cfg.store))
        event = {"type": "response.create", **body}
        self.ws.send(json.dumps(event))

        # Collect events until we see a completed response.
        response: Dict[str, Any] = {}
        events: List[Dict[str, Any]] = []
        while True:
            raw = self.ws.recv()
            msg = json.loads(raw)
            events.append(msg)

            t = msg.get("type")
            if t == "response.completed":
                response = msg.get("response") or {}
                break
            if t == "error":
                raise TransportError(f"ws_error: {msg}")

        # attach events for debugging (caller may drop for storage)
        response["_ws_events"] = events[-50:]
        return response

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass
