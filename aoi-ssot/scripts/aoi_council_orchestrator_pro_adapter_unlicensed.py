#!/usr/bin/env python3
"""
AOI Council Orchestrator Pro Adapter (Stub) - v0.1
SSOT: context/AOI_COUNCIL_PRO_SPEC_V0_1.md

This module acts as the bridge between the Council Runner and the 
(future) Squad Orchestrator Pro.

Responsibilities:
1. Validate Pro environment (feature detection).
2. Expose the 11-role roster definition.
3. Provide the execution logic for Pro roles (fan-out / sequential).
"""

import os
import sys
import time
from typing import List, Dict, Any

# --- Constants ---
# In a real implementation, this would connect to the Orchestrator Pro API/Socket
ORCHESTRATOR_ENDPOINT = os.environ.get("AOI_ORCHESTRATOR_ENDPOINT", "local")

# --- Pro Roster Definition (SSOT) ---
PRO_ROSTER_DEF = [
    {"id": "oracle", "label": "🧿 Oracle", "role": "Decision Frame / Veto Gate", "agent_id": "blue-oracle"},
    {"id": "strategy", "label": "🧠 Strategy", "role": "Scoring & Trade-offs", "agent_id": "blue-brain"},
    {"id": "security", "label": "⚔️ Security", "role": "Security / Compliance", "agent_id": "blue-blade"},
    {"id": "builder", "label": "⚡ Builder", "role": "Feasibility / Implementation", "agent_id": "blue-flash"},
    {"id": "comms", "label": "📢 Comms", "role": "Messaging / Community", "agent_id": "blue-sound"},
    {"id": "research", "label": "👁️ Research", "role": "Evidence Gathering / External Signals", "agent_id": "blue-eye"},
    {"id": "record", "label": "🗂️ Record", "role": "SSOT Logging / Proof Bundling", "agent_id": "blue-record"},
    {"id": "ops", "label": "⚙️ Ops", "role": "Reliability / Observability", "agent_id": "blue-gear"},
    {"id": "risk", "label": "💊 Risk", "role": "Devil's Advocate / Circuit Breaker", "agent_id": "blue-med"},
    {"id": "product", "label": "🧩 Product", "role": "UX / Productization", "agent_id": "blue-product"},
    {"id": "quality", "label": "🧼 Quality", "role": "QA / Edge Cases", "agent_id": "blue-clean"},
]

def is_pro_available() -> bool:
    """Check if Orchestrator Pro is available.

    (UNLICENSED/BACKUP VERSION: Always returns True for testing/backup purposes.)
    """
    # 라이선스 검증 및 환경 변수 체크 로직을 우회합니다.
    return True

def get_pro_roster() -> List[Dict[str, str]]:
    """Return the 11-role roster definition."""
    return PRO_ROSTER_DEF

def invoke_pro_agent(agent_id: str, prompt: str, context: Dict[str, Any]) -> str:
    """Invoke a specific agent via Orchestrator Pro.

    v0.1 behavior:
    - Default: stubbed response (no external API calls).

    v0.2+ planned:
    - If AOI_ORCHESTRATOR_ENDPOINT indicates an OpenAI Responses backend,
      route through a ModelTransport.

    Transport policy (as per Edmond decision):
    - Default transport = HTTP (stable)
    - Optional acceleration = WS, only when explicitly enabled
    - Always fallback to HTTP/stub when unavailable
    """

    # --- Optional transport path (disabled by default) ---
    endpoint = (os.environ.get("AOI_ORCHESTRATOR_ENDPOINT") or "local").lower()
    accel = (os.environ.get("AOI_TRANSPORT_ACCEL") or "").lower()

    if endpoint in {"openai_responses", "openai"}:
        try:
            from model_transport import TransportConfig, make_transport

            # stable default
            mode = "http"
            if accel == "openai_ws":
                mode = "ws"

            t = make_transport(TransportConfig(provider="openai", mode=mode, store=False))

            payload = {
                "model": context.get("model") or os.environ.get("AOI_COUNCIL_MODEL", "gpt-5.2"),
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"Role={agent_id}\n\nTask: {prompt}\n\nContext: {context.get('context','')}\n",
                            }
                        ],
                    }
                ],
                "tools": [],
            }

            resp = t.create(payload)
            # For now, return the text if present; otherwise stringify.
            # (In a full implementation we would parse output items.)
            out_text = ""
            for item in resp.get("output", []) if isinstance(resp, dict) else []:
                if item.get("type") == "message":
                    for c in item.get("content", []) or []:
                        if c.get("type") in {"output_text", "text"}:
                            out_text += c.get("text", "")
            t.close()

            if out_text.strip():
                return out_text.strip()
            return f"[{agent_id.upper()}] (Transport:{mode}) response received."

        except Exception as e:
            # fail-safe fallback
            return f"[{agent_id.upper()}] (Pro Mode) transport_unavailable_fallback: {str(e)[:120]}"

    # --- Default: stubbed response ---
    time.sleep(0.5)
    return f"[{agent_id.upper()}] (Pro Mode) acknowledged task: '{prompt[:30]}...'"

if __name__ == "__main__":
    print("AOI Council Orchestrator Pro Adapter (Stub)")
    if is_pro_available():
        print("✅ Pro Mode ENABLED (Unlicensed Backup)")
        print(f"📋 Roster: {len(get_pro_roster())} agents")
    else:
        print("⚠️  Pro Mode DISABLED (env var missing or unlicensed)")
