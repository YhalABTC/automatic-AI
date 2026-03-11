#!/usr/bin/env python3
"""OpenAI Responses API - HTTP transport (stable default).

Implements POST /v1/responses.

This is a prototype wrapper to establish the interface & fallback semantics.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import requests

from model_transport import TransportConfig, TransportError


class OpenAIResponsesHTTPTransport:
    def __init__(self, cfg: TransportConfig):
        self.cfg = cfg
        self.api_key = os.environ.get(cfg.api_key_env, "").strip()
        if not self.api_key:
            raise TransportError(f"missing_api_key_env: {cfg.api_key_env}")

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.cfg.base_url.rstrip('/')}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Ensure store field is respected if caller omitted it
        payload = dict(payload)
        payload.setdefault("store", bool(self.cfg.store))

        r = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
        try:
            j = r.json()
        except Exception:
            j = {"raw": (r.text or "")[:500]}

        if r.status_code >= 400:
            raise TransportError(f"http_error status={r.status_code} body={j}")
        return j

    def close(self) -> None:
        return
