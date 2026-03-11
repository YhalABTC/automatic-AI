#!/usr/bin/env python3
"""
🌌 Aoineco-Verified | Multi-Agent Collective (PRO)
S-DNA: AOI-2026-0302-SDNA-COUNCILPRO-01
License: Proprietary Beta (see LICENSE_PROPRIETARY_BETA.md)

AOI Council Run (Unified Runner for Lite/Pro) - v0.1.7
SSOT: context/AOI_COUNCIL_PRO_SPEC_V0_1.md

Usage:
  python3 scripts/aoi_council_run.py --mode decision --topic "Should we buy X?" --pro
"""

import argparse
import json
import os
import re
import sys
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import local adapter
try:
    import aoi_council_orchestrator_pro_adapter as pro_adapter
except ImportError:
    # If running from root, add scripts to path
    sys.path.append(os.path.join(os.path.dirname(__file__)))
    import aoi_council_orchestrator_pro_adapter as pro_adapter

# --- Constants ---
VERSION = "0.1.8"
PROOF_PACK_SCHEMA_VERSION = "0.1"
DEFAULT_MODEL = "gemini-flash"  # placeholder; actual agent routing lives in Orchestrator Pro

# Policy engine v0.2 (externalized config)
POLICY_ENGINE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "context" / "AOI_COUNCIL_POLICY_ENGINE_CONFIG_V0_1.json"

# Baseline defaults (kept for hardening + fallback)
DEFAULT_POLICY_RULES = {
    "exposure_tier_patterns": {
        "OPEN": ["open", "public", "release", "announce", "press", "blog", "moltbook", "botmadang"],
        "TEASER": ["teaser", "preview", "early", "pilot", "demo", "pre-release", "pre launch", "sample", "sampled", "draft", "beta"],
        "STEALTH": ["stealth", "internal", "사내", "confidential", "restricted", "비공개", "internal-only", "prerelease", "preview-only", "private"],
        "TOP SECRET": ["top secret", "tokenomics", "treasury", "distribution", "wallet private", "private key", "seed", "kyc", "kms", "signature", "signing"],
    },
    "l1_l2_l3_blocklist": [
        "wallet", "sign", "signing", "private key", "onchain", "tx", "transaction", "deploy", "deploying", "deployments", "commit", "publishing", "external posting", "external post", "immutable", "permanent"
    ],
    "evidence_secret_patterns": ["private key", "secret", "api key", "authorization", "bearer", "passwd", "password", "mnemonic", "seed phrase"],
}
POLICY_SCORE = {"PASS": 0, "WARN": 20, "FAIL": 60}
POLICY_RULE_WEIGHTS = {
    "exposure_tier": {"PASS": 0, "WARN": 10, "FAIL": 50},
    "l1_l2_l3_boundary": {"PASS": 0, "WARN": 35, "FAIL": 60},
    "evidence_integrity": {"PASS": 0, "WARN": 15, "FAIL": 50},
    "github_public_final_policy": {"PASS": 0, "WARN": 20, "FAIL": 50},
}
POLICY_THRESHOLD = {
    "warn_conditional": 20,
    "warn_hold": 55,
    "score_hold": 80,
    "score_conditional": 30,
}

# Cost governor defaults (v0.1)
DEFAULT_COST_GOVERNOR = {
    "version": "v0.1",
    "enabled": True,
    "window_seconds": 3600,
    "max_tasks_per_minute": 12,
    "max_tasks_per_hour": 180,
    "max_retries_per_task": 3,
    "max_retries_per_window": 50,
    "retry_backoff_ms": [1000, 3000, 8000],
    "budget_usd": {
        "soft": 5,
        "hard": 7,
        "currency": "USDC",
        "chain": "Base",
    },
    "auto_actions": {
        "on_warn": "notify_only",
        "on_critical": "pause_actor",
    },
    "burst_guard": {
        "task_spike_ratio": 4,
        "window_size_seconds": 300,
    },
}

# runtime-loaded mutable values
POLICY_RULES = DEFAULT_POLICY_RULES

# --- Roster Definitions ---
ROSTER_LITE = [
    {"id": "oracle", "label": "🧿 Oracle", "role": "Decision Frame & Veto Gate"},
    {"id": "analyzer", "label": "🧠 Analyzer", "role": "Scoring & Trade-offs"},
    {"id": "security", "label": "⚔️ Security", "role": "Security & Risk Compliance"},
    {"id": "builder", "label": "⚡ Builder", "role": "Feasibility & MVP Plan"},
    {"id": "comms", "label": "📢 Comms", "role": "Messaging & Community Reaction"},
]


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_orchestrator_mode(requested_pro: bool) -> str:
    """
    Determine if we run in PRO or LITE mode.
    - request_pro=False -> lite
    - request_pro=True -> adapter probe then pro/lite fallback
    """
    if not requested_pro:
        return "lite"

    if pro_adapter.is_pro_available():
        return "pro"

    print("⚠️  [System] Orchestrator Pro not detected/enabled. Falling back to Lite mode.")
    return "lite"


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] if s else "topic"


def _make_evidence_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ag-{ts}-{uuid.uuid4().hex[:8]}"



def _load_policy_config(config_path: Optional[str] = None) -> None:
    """Load policy rules and thresholds from JSON config file without changing behavior defaults."""
    global POLICY_RULES, POLICY_SCORE, POLICY_RULE_WEIGHTS, POLICY_THRESHOLD

    env_path = os.environ.get("AOI_COUNCIL_POLICY_CONFIG")
    config_path = config_path or env_path or str(POLICY_ENGINE_CONFIG_PATH)
    path = Path(config_path)
    if not path.exists():
        # keep defaults if file missing
        print(f"[policy-config] Missing {path}, fallback to embedded defaults")
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        POLICY_RULES = data.get("policy_rules", POLICY_RULES)
        POLICY_SCORE = data.get("policy_score", POLICY_SCORE)
        POLICY_RULE_WEIGHTS = data.get("policy_rule_weights", POLICY_RULE_WEIGHTS)
        POLICY_THRESHOLD = data.get("policy_threshold", POLICY_THRESHOLD)
    except Exception as exc:
        print(f"[policy-config] Failed to load {path}: {exc}; using defaults")



def _load_cost_governor_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load cost governor policy from JSON config, fallback to defaults on errors."""
    env_path = os.environ.get("AOI_COST_GOVERNOR_CONFIG")
    path_value = config_path or env_path
    if not path_value:
        return DEFAULT_COST_GOVERNOR.copy()

    path = Path(path_value)
    if not path.exists():
        print(f"[cost-governor] Missing {path}, fallback to embedded defaults")
        return DEFAULT_COST_GOVERNOR.copy()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root must be object")
        merged = DEFAULT_COST_GOVERNOR.copy()
        merged.update({k: v for k, v in data.items() if v is not None})
        # keep nested budgets if partial updates are given
        if "budget_usd" in data and isinstance(data["budget_usd"], dict):
            m = dict(merged["budget_usd"])
            m.update(data["budget_usd"])
            merged["budget_usd"] = m
        if "auto_actions" in data and isinstance(data["auto_actions"], dict):
            m = dict(merged["auto_actions"])
            m.update(data["auto_actions"])
            merged["auto_actions"] = m
        if "burst_guard" in data and isinstance(data["burst_guard"], dict):
            m = dict(merged["burst_guard"])
            m.update(data["burst_guard"])
            merged["burst_guard"] = m
        return merged
    except Exception as exc:
        print(f"[cost-governor] Failed to load {path}: {exc}; using defaults")
        return DEFAULT_COST_GOVERNOR.copy()



def _safe_lower(value: Optional[str]) -> str:
    return (value or "").lower()
def _load_cost_state(state_path: Optional[str], actor: str) -> Dict[str, Any]:
    if not state_path:
        return {"version": "v0.1", "actors": {}}
    path = Path(state_path)
    if not path.exists():
        return {"version": "v0.1", "actors": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "v0.1", "actors": {}}
    if not isinstance(data, dict):
        return {"version": "v0.1", "actors": {}}
    actors = data.get("actors")
    if not isinstance(actors, dict):
        actors = {}
    for k,v in list(actors.items()):
        if not isinstance(v, dict):
            actors[k]={}
    data["actors"] = actors
    if actor not in actors:
        actors[actor] = {}
    return data


def _save_cost_state(state_path: Optional[str], state: Dict[str, Any]) -> None:
    if not state_path:
        return
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _bucket_for(seconds: int) -> int:
    return int(time.time() // seconds) if seconds > 0 else 0


def _cost_governor_check(
    actor: str,
    estimated_cost_usd: float,
    retry_attempt: int,
    mode: str,
    state_path: Optional[str],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply AOI Cost Governor v0.1 policy and mutate state for usage accounting."""
    ts_now = int(time.time())
    cfg = config or DEFAULT_COST_GOVERNOR
    if not cfg.get("enabled", True):
        return {
            "version": "v0.1",
            "status": "ENABLED",
            "decision": "ALLOW",
            "reason": "Cost governor disabled",
            "checks": [],
            "metrics": {},
        }

    state = _load_cost_state(state_path, actor)
    actors = state.setdefault("actors", {})
    actor_state = actors.setdefault(actor, {})

    minute_bucket = _bucket_for(60)
    hour_bucket = _bucket_for(3600)
    burst_bucket = _bucket_for(max(1, int(cfg.get("burst_guard", {}).get("window_size_seconds", 300))))
    retry_bucket = _bucket_for(60)

    if actor_state.get("minute_bucket") != minute_bucket:
        actor_state["minute_bucket"] = minute_bucket
        actor_state["minute_count"] = 0
    if actor_state.get("hour_bucket") != hour_bucket:
        actor_state["hour_bucket"] = hour_bucket
        actor_state["hour_count"] = 0
    if actor_state.get("burst_bucket") != burst_bucket:
        actor_state["burst_bucket"] = burst_bucket
        actor_state["burst_count"] = 0
    if actor_state.get("retry_bucket") != retry_bucket:
        actor_state["retry_bucket"] = retry_bucket
        actor_state["retry_count"] = 0

    minute_count = int(actor_state.get("minute_count", 0))
    hour_count = int(actor_state.get("hour_count", 0))
    burst_count = int(actor_state.get("burst_count", 0))
    retry_window_count = int(actor_state.get("retry_count", 0))

    budget_soft = float((cfg.get("budget_usd") or {}).get("soft", 0.0) or 0.0)
    budget_hard = float((cfg.get("budget_usd") or {}).get("hard", 0.0) or 0.0)
    budget_spent = float(actor_state.get("budget_spent", 0.0) or 0.0)
    minute = max(0, minute_count)
    hour = max(0, hour_count)
    max_min = int(cfg.get("max_tasks_per_minute", 0) or 0)
    max_hour = int(cfg.get("max_tasks_per_hour", 0) or 0)
    max_retries_task = int(cfg.get("max_retries_per_task", 0) or 0)
    max_retries_window = int(cfg.get("max_retries_per_window", 0) or 0)

    # hard cap checks (fail-closed)
    checks = []
    decision = "ALLOW"
    reasons = []

    if budget_hard > 0 and (budget_spent + estimated_cost_usd) >= budget_hard:
        decision = "BLOCK"
        reasons.append(f"hard budget exceeded ({budget_spent + estimated_cost_usd:.2f}/{budget_hard:.2f})")
        checks.extend(["hard_budget"])

    if max_retries_task > 0 and retry_attempt > max_retries_task:
        decision = "BLOCK"
        reasons.append(f"retry_attempt {retry_attempt} exceeds max_retries_per_task {max_retries_task}")
        checks.append("retries_per_task")

    if max_retries_window > 0 and (retry_window_count + retry_attempt) > max_retries_window:
        decision = "BLOCK"
        reasons.append(f"retry window ({retry_window_count + retry_attempt}/{max_retries_window}) exceeded")
        checks.append("retries_per_window")

    if decision == "ALLOW" and max_min > 0 and (minute_count + 1) > max_min:
        decision = "REVIEW"
        reasons.append(f"minute burst ({minute_count + 1}/{max_min})")
        checks.append("max_tasks_per_minute")

    if decision == "ALLOW" and max_hour > 0 and (hour_count + 1) > max_hour:
        decision = "REVIEW"
        reasons.append(f"hourly cap ({hour_count + 1}/{max_hour})")
        checks.append("max_tasks_per_hour")

    # burst guard
    ratio = int(cfg.get("burst_guard", {}).get("task_spike_ratio", 0) or 0)
    if decision == "ALLOW" and ratio > 0 and max_min > 0 and minute > 0 and burst_count > (max_min * ratio):
        decision = "REVIEW"
        reasons.append(f"burst guard triggered ({burst_count}/{max_min * ratio})")
        checks.append("burst_guard")

    if decision == "ALLOW" and budget_soft > 0 and (budget_spent + estimated_cost_usd) > budget_soft:
        if decision != "BLOCK":
            decision = "REVIEW"
        reasons.append(f"soft budget pressure ({budget_spent + estimated_cost_usd:.2f}/{budget_soft:.2f})")
        checks.append("soft_budget")

    # mutate accounting regardless of decision outcome
    actor_state["minute_count"] = minute_count + 1
    actor_state["hour_count"] = hour_count + 1
    actor_state["burst_count"] = burst_count + 1
    actor_state["retry_count"] = retry_window_count + max(0, int(retry_attempt or 0))
    actor_state["budget_spent"] = budget_spent + max(0.0, float(estimated_cost_usd or 0.0))
    actor_state["last_ts"] = ts_now
    actor_state["last_mode"] = mode
    actor_state["last_decision"] = decision

    state["actors"] = actors

    _save_cost_state(state_path, state)

    if decision == "BLOCK":
        auto_action = cfg.get("auto_actions", {}).get("on_critical", "pause_actor")
    elif decision == "REVIEW":
        auto_action = cfg.get("auto_actions", {}).get("on_warn", "notify_only")
    else:
        auto_action = "proceed"

    return {
        "version": "v0.1",
        "status": "BLOCK" if decision == "BLOCK" else ("HOLD" if decision == "REVIEW" else "OK"),
        "decision": decision,
        "reason": "; ".join(reasons) if reasons else "within_threshold",
        "checks": checks,
        "auto_action": auto_action,
        "metrics": {
            "cost_estimate": float(estimated_cost_usd or 0.0),
            "attempts": {
                "minute": minute_count + 1,
                "hour": hour_count + 1,
                "retry_window": retry_window_count + max(0, int(retry_attempt or 0)),
            },
            "budget": {
                "soft": budget_soft,
                "hard": budget_hard,
                "spent": float(actor_state["budget_spent"]),
            },
            "state": {
                "minute_bucket": minute_bucket,
                "hour_bucket": hour_bucket,
                "burst_bucket": burst_bucket,
            },
        },
    }




def mock_agent_response(role: Dict[str, str], topic: str) -> str:
    """Stub for Lite role call."""
    return f"[{role['label']}] Opinion on '{topic}': This is a placeholder response generated by the runner stub."


def _invoke_agent(role: Dict[str, str], topic: str, mode: str, context: Optional[str]) -> str:
    if mode == "pro":
        agent_id = role.get("agent_id", "unknown")
        ctx = {"mode": mode, "context": context}
        return pro_adapter.invoke_pro_agent(agent_id, topic, ctx)
    return mock_agent_response(role, topic)


def _make_critique(target_label: str, context_blob: str) -> str:
    """Create deterministic critique text for cross-critique passes (stubbed)."""
    snippet = context_blob[:36] if context_blob else "current topic"
    return (
        f"[Cross-critique] {target_label} should tighten confidence with concrete assumptions. "
        f"Current claim references '{snippet}' but lacks fallback condition, "
        "so include a fail-safe and one measurable validation metric."
    )


def _select_smart_roster(full_roster: List[Dict[str, Any]], topic: str, context: Optional[str]) -> List[Dict[str, Any]]:
    """Smart roster selection for Pro: start core roles, add specialists conditionally."""
    core_ids = {"oracle", "strategy", "security", "builder", "comms"}
    always_ids = set(core_ids) | {"risk"}  # devil's advocate always on in Pro

    t = _safe_lower(topic)
    c = _safe_lower(context)
    blob = f"{t}\n{c}"

    want = set(always_ids)

    # Heuristic triggers
    if any(k in blob for k in ["benchmark", "compare", "winner", "research", "dorahacks", "market", "news"]):
        want.add("research")
    if any(k in blob for k in ["deploy", "ci", "launch", "cron", "agent", "reliability", "launchagent", "ops"]):
        want.add("ops")
    if any(k in blob for k in ["proof", "evidence", "ssot", "notion", "artifact", "manifest"]):
        want.add("record")
    if any(k in blob for k in ["ux", "ui", "demo", "landing", "copy", "positioning"]):
        want.add("product")
    if any(k in blob for k in ["test", "edge", "bug", "regression", "qa"]):
        want.add("quality")

    selected = [r for r in full_roster if r.get("id") in want]
    return selected[:11]


def _contains_block(patterns: List[str], text: str) -> List[str]:
    lowered = (text or "").lower()
    return [p for p in patterns if p in lowered]


def _infer_role_position(role_id: str, role_label: str, topic: str, context: Optional[str], output: str) -> Dict[str, Any]:
    text = (f"{topic or ''} {context or ''} {output or ''}").lower()
    high_risk_terms = ["wallet", "sign", "private key", "seed", "treasury", "secret", "onchain", "tx", "signature", "kms", "kyc", "deploy", "release", "publish"]
    has_high_risk = bool(_contains_block(high_risk_terms, text))

    recommendation = "Conditional"
    confidence = "Medium"
    risk = "Medium"

    if role_id in {"security", "risk"}:
        risk = "High"
        confidence = "Medium"
        if has_high_risk:
            recommendation = "Hold"
            confidence = "Low"
    elif role_id in {"ops", "quality"}:
        confidence = "Medium"
        if has_high_risk:
            recommendation = "Hold"
            confidence = "Low"
    elif role_id in {"oracle", "strategy", "research"}:
        if has_high_risk:
            recommendation = "Conditional"
            risk = "Medium"
    else:
        risk = "Low"
        confidence = "High"
        if has_high_risk:
            confidence = "Medium"

    if "placeholder" in output.lower() and len((output or "").strip()) < 120:
        confidence = "Medium" if confidence == "High" else confidence

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "risk": risk,
        "risk_signal": has_high_risk,
        "note": "high-risk terms detected" if has_high_risk else "policy risk within normal bounds",
    }


def _role_critique(source_label: str, source_position: Dict[str, Any], target_label: str, target_position: Dict[str, Any], topic: str) -> str:
    if source_position["recommendation"] != target_position["recommendation"]:
        return (
            f"[{source_label}] disagrees with {target_label}: recommendation differs. "
            "Request explicit rollback condition + measurable KPI before any narrow-scope execution is allowed."
        )
    # Same direction => tighten execution conditions
    return (
        f"[{source_label}] aligns with {target_label} on recommendation, "
        f"but requires clearer failure thresholds and ownership of follow-up checks. topic={topic[:20]}"
    )


def _role_weights() -> Dict[str, float]:
    return {
        "risk": 1.8,
        "security": 1.5,
        "ops": 1.2,
        "quality": 1.1,
        "oracle": 1.05,
        "strategy": 1.0,
        "builder": 0.95,
        "research": 0.9,
        "record": 0.8,
        "product": 0.8,
        "comms": 0.75,
    }


def _resolve_recommendation_from_votes(votes: List[str], roles: List[Dict[str, Any]]) -> str:
    score_map = {"Hold": 0.0, "Conditional": 1.0, "Approve": 1.4}
    weights = _role_weights()

    total_weight = 0.0
    weighted_score = 0.0
    for role, vote in zip(roles, votes):
        w = weights.get(role.get("id", ""), 1.0)
        weighted_score += score_map.get(vote, 1.0) * w
        total_weight += w

    if total_weight == 0:
        return "Conditional"

    ratio = weighted_score / total_weight
    if ratio < 0.55:
        return "Hold"
    if ratio < 1.05:
        return "Conditional"
    return "Conditional"


def _merge_role_position(base_output: str, position: Dict[str, Any], topic: str, context: Optional[str]) -> str:
    base = base_output.strip()
    if not base:
        base = "Placeholder opinion recorded."
    context_tag = (context or "").strip()[:50]
    if context_tag:
        return f"{base} | {position.get("note", "")} (context: {context_tag})."
    return f"{base} | {position.get("note", "")}"


def _synthesize_passes(roles: List[Dict[str, Any]], topic: str, context: Optional[str], mode: str) -> Dict[str, Any]:
    """Implements 3-pass Cross-Critique scaffold for Pro-ready workflow."""
    if mode != "pro":
        return {
            "critiques": [],
            "roles": roles,
            "pass_b_count": 0,
            "pass_c_count": 0,
            "synthesis": {
                "consensus": "Lite mode currently does not run cross-critique.",
                "conflict": "Lite mode is baseline single-pass.",
                "dissent": [],
                "assumptions": ["Inputs are sufficient for single-pass decision support."],
                "recommendation": "Conditional",
                "confidence": "Low",
                "risk": "Unknown",
            },
        }

    if not roles:
        return {
            "critiques": [],
            "roles": roles,
            "pass_b_count": 0,
            "pass_c_count": 0,
            "synthesis": {
                "consensus": "No roles selected for Pro run.",
                "conflict": "No opinions collected.",
                "dissent": [],
                "assumptions": ["No active roles means no substantive consensus yet."],
                "recommendation": "Hold",
                "confidence": "Low",
                "risk": "High",
            },
        }

    for role in roles:
        position = _infer_role_position(
            role.get("id", ""),
            role.get("label", ""),
            topic,
            context,
            role.get("pass_a_output", ""),
        )
        role["position"] = position

    critiques = []
    for idx, role in enumerate(roles):
        target = roles[(idx + 1) % len(roles)]
        critique = _role_critique(
            role.get("label", ""),
            role["position"],
            target.get("label", ""),
            target["position"],
            topic,
        )
        critiques.append({
            "critic_id": role["id"],
            "critic_label": role["label"],
            "target_id": target["id"],
            "target_label": target["label"],
            "critique": critique,
        })
        target.setdefault("critiques_received", []).append(critique)

    for role in roles:
        received = role.get("critiques_received", [])
        if received:
            role["pass_c_output"] = (
                f"Revised position: keep direction = {role['position']['recommendation']}, "
                f"add fallback condition and acceptance criteria from feedback: {received[0]}"
            )
        else:
            role["pass_c_output"] = (
                f"Revised position: keep direction = {role['position']['recommendation']}, "
                "no peer feedback received."
            )
        role["pass_a_output"] = _merge_role_position(role["pass_a_output"], role["position"], topic, context)

    votes = [r["position"]["recommendation"] for r in roles]
    recommendation = _resolve_recommendation_from_votes(votes, roles)
    consensus_count = {v: votes.count(v) for v in set(votes)}

    if len(consensus_count) <= 1 or (recommendation == "Conditional" and consensus_count.get("Conditional", 0) >= len(roles) - 1):
        conflict = "No major conflict; roles converge on Conditional path with explicit safety conditions."
    else:
        conflict = "Conflict: {} recommendations observed ({}).".format(len(consensus_count), "; ".join([f"{k}:{v}" for k, v in sorted(consensus_count.items())]))

    if recommendation == "Hold":
        confidence = "Medium" if consensus_count.get("Hold", 0) > len(roles) / 2 else "Low"
    else:
        confidence = "High" if len(consensus_count) == 1 else "Medium"

    risk = "High" if any(r["position"].get("risk") == "High" for r in roles) else "Medium"
    if risk != "High" and any(r["position"].get("risk_signal") for r in roles if isinstance(r.get("position"), dict)):
        risk = "Medium"

    dissent = [r["label"] for r in roles if r["position"]["recommendation"] != recommendation]

    assumptions = [
        "Final decision requires measurable pass/fail criteria before implementation.",
        "Policy scorecard and L1/L2/L3 constraints are treated as hard post-synthesis gates.",
        "Fallback plan should be prepared for Hold/Conditional boundary transitions.",
    ]
    if recommendation == "Hold":
        assumptions.append("At least one high-risk signal was detected; execution should be deferred until controls are added.")

    return {
        "critiques": critiques,
        "roles": roles,
        "pass_b_count": len(critiques),
        "pass_c_count": len(roles),
        "synthesis": {
            "consensus": "Most roles align on a conservative path." if len(consensus_count) == 1 else "Conservative consensus: conditions first, then proceed only with controls.",
            "conflict": conflict,
            "dissent": dissent[:5],
            "assumptions": assumptions,
            "recommendation": recommendation,
            "confidence": confidence,
            "risk": risk,
            "policy_adjustments": [],
            "policy_score": 0,
            "policy_risk_score_card": {
                "status": "PASS",
                "score": 0,
                "warn_count": 0,
                "fail_count": 0,
                "breakdown": [],
            },
            "pass_votes": {
                v: consensus_count[v] for v in sorted(consensus_count.keys())
            },
        },
    }


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return ""


def _contains_keyword_patterns(text: str, patterns: List[str]) -> List[str]:
    lowered = (text or "").lower()
    return [p for p in patterns if p in lowered]


def _classify_exposure_tier(text: str) -> Dict[str, Any]:
    """Simple deterministic classification from policy keyword matrices."""
    lowered = (text or "").lower()

    hits_open = _contains_keyword_patterns(lowered, POLICY_RULES["exposure_tier_patterns"]["OPEN"])
    hits_teaser = _contains_keyword_patterns(lowered, POLICY_RULES["exposure_tier_patterns"]["TEASER"])
    hits_stealth = _contains_keyword_patterns(lowered, POLICY_RULES["exposure_tier_patterns"]["STEALTH"])
    hits_top = _contains_keyword_patterns(lowered, POLICY_RULES["exposure_tier_patterns"]["TOP SECRET"])

    if hits_top:
        return {
            "status": "WARN",
            "tier": "TOP SECRET",
            "note": f"Top-secret keywords detected: {', '.join(hits_top)}",
        }

    if hits_stealth:
        return {
            "status": "PASS",
            "tier": "STEALTH",
            "note": f"Stealth/internal keywords detected: {', '.join(hits_stealth)}",
        }

    if hits_teaser:
        return {
            "status": "PASS",
            "tier": "TEASER",
            "note": f"Teaser/pilot keywords detected: {', '.join(hits_teaser)}",
        }

    if hits_open:
        return {
            "status": "PASS",
            "tier": "OPEN",
            "note": "Open/public-oriented terms detected.",
        }

    return {
        "status": "PASS",
        "tier": "OPEN",
        "note": "No restricted exposure keyword matched. default OPEN.",
    }


def _derive_action_decision(status: str, score: int, warn_count: int, fail_count: int, checks: List[Dict[str, Any]]) -> str:
    """Map policy results to explicit Action Guard decisions.

    ALLOW  : low risk, PASS band
    REVIEW : warn band, or soft risk with multiple weak signals
    BLOCK  : fail band, hard score, or explicit hard blockers
    """
    hard_block_keywords = {"wallet", "sign", "signature", "private key", "seed", "deploy", "tx", "transaction", "hard stop", "immutable"}

    if fail_count > 0 or score >= POLICY_THRESHOLD.get("score_hold", 80):
        return "BLOCK"

    if status == "WARN" or score >= POLICY_THRESHOLD.get("warn_hold", 55) or score >= POLICY_THRESHOLD.get("warn_conditional", 20):
        return "REVIEW"

    # explicit hard-block text scan for conservative enforcement
    notes = " ".join([str(c.get("note", "")).lower() for c in checks])
    if any(k in notes for k in hard_block_keywords):
        return "REVIEW"

    return "ALLOW"


def _score_policy_checks(checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    score = 0
    fail_count = 0
    warn_count = 0
    weighted_breakdown = []

    for c in checks:
        rule_id = c.get("id")
        status = c.get("status", "PASS")
        weight_map = POLICY_RULE_WEIGHTS.get(rule_id, POLICY_SCORE)
        weighted = weight_map.get(status, POLICY_SCORE.get(status, 0))
        score += weighted

        if status == "FAIL":
            fail_count += 1
        elif status == "WARN":
            warn_count += 1

        weighted_breakdown.append({
            "id": rule_id,
            "status": status,
            "weight": weighted,
        })

    if fail_count > 0:
        status = "FAIL"
    elif warn_count > 0:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "score": score,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "weighted_breakdown": weighted_breakdown,
    }


def _policy_check(inputs: Dict[str, Any], mode: str, evidence_paths: Optional[List[str]]) -> Dict[str, Any]:
    topic = _safe_lower(inputs.get("topic"))
    context = _safe_lower(inputs.get("context"))
    evidence_paths = evidence_paths or []
    blob = f"{topic} {context}"

    checks = []

    # 1) Exposure tier (deterministic keyword scoring)
    exposure = _classify_exposure_tier(blob)
    checks.append({
        "id": "exposure_tier",
        "status": exposure["status"],
        "tier": exposure["tier"],
        "note": exposure["note"],
    })

    # 2) L1/L2/L3 boundary checks
    l3_hits = _contains_keyword_patterns(blob, POLICY_RULES["l1_l2_l3_blocklist"])
    if l3_hits:
        l3_status = "WARN"
        l3_note = f"Potential L3 triggers in topic/context: {', '.join(l3_hits)}. Runner is report-only by default."
    else:
        l3_status = "PASS"
        l3_note = "No L3 trigger found in topic/context."
    checks.append({
        "id": "l1_l2_l3_boundary",
        "status": l3_status,
        "note": l3_note,
    })

    # 3) Evidence integrity: exists + readable + secret leak check
    evidence_notes: List[str] = []
    evidence_ok = True

    for p in evidence_paths:
        p_obj = Path(p)
        if not p_obj.exists():
            evidence_ok = False
            evidence_notes.append(f"Evidence path missing: {p}")
            continue
        if not p_obj.is_file():
            evidence_ok = False
            evidence_notes.append(f"Evidence path is not a file: {p}")
            continue

        contents = _read_file_text(p_obj).lower()
        secret_hits = _contains_keyword_patterns(contents, POLICY_RULES["evidence_secret_patterns"])
        if secret_hits:
            evidence_ok = False
            evidence_notes.append(f"Potential secret pattern in {p}: {', '.join(secret_hits)}")

    if not evidence_paths:
        evidence_notes.append("No evidence paths provided. This is allowed for local runs.")

    checks.append({
        "id": "evidence_integrity",
        "status": "PASS" if evidence_ok else "WARN",
        "note": " | ".join(evidence_notes),
    })

    # 4) Public-final policy guard
    public_markers = ["final", "frozen", "hackathon", "public final", "public-final"]
    public_guard = "PASS"
    public_note = "PASS: runner mode is report-only and does not mutate public repositories."
    if mode == "pro" and any(k in topic for k in public_markers):
        public_guard = "WARN"
        public_note = "Topic indicates a final/frozen/public artifact. Validate against GITHUB_PUBLIC_FINAL_POLICY_V0_1.md before any mutation."

    checks.append({
        "id": "github_public_final_policy",
        "status": public_guard,
        "note": public_note,
    })

    scoring = _score_policy_checks(checks)
    score = scoring["score"]

    if mode != "pro":
        # Keep Lite deterministic and simple
        status = scoring["status"]
    else:
        status = scoring["status"]

    action_decision = _derive_action_decision(status, score, scoring.get("warn_count", 0), scoring.get("fail_count", 0), checks)

    evidence_id = _make_evidence_id()

    return {
        "version": PROOF_PACK_SCHEMA_VERSION,
        "executed_at": get_timestamp(),
        "mode": mode,
        "mode_requested": mode,
        "evidence_id": evidence_id,
        "action_decision": action_decision,
        "action_gates": {
            "default_decision": "ALLOW" if action_decision == "ALLOW" else action_decision,
            "review_reasons": [c.get("id") for c in checks if c.get("status") in ["WARN", "FAIL"]],
            "evidence": {
                "id": evidence_id,
                "decision": action_decision,
                "score": score,
                "status": status,
            },
        },
        "summary": {
            "status": status,
            "score": score,
            "fail_count": scoring["fail_count"],
            "warn_count": scoring["warn_count"],
            "weighted_breakdown": scoring["weighted_breakdown"],
        },
        "checks": checks,
    }



def _parse_iso_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _permission_scope_check(
    actor: str,
    target: str,
    method: str,
    action: str,
    amount: float,
    value_usd: float,
    network: str,
    permission_path: Optional[str],
) -> Dict[str, Any]:
    """Validate requested action against permission scope registry.

    Returns a compact decision payload used by AOI Permission Scope v0.1.
    """
    ts_now = datetime.now(timezone.utc)
    if not permission_path:
        return {
            "version": "v0.1",
            "status": "NOT_FOUND",
            "decision": "ALLOW",
            "matched_permission_id": None,
            "reason": "No permission scope file provided",
            "notes": ["permission scope input is optional in current rollout"],
            "checks": ["permission_path"],
            "checked_at": ts_now.isoformat(),
        }

    path = Path(permission_path)
    if not path.exists():
        return {
            "version": "v0.1",
            "status": "NOT_FOUND",
            "decision": "REVIEW",
            "matched_permission_id": None,
            "reason": f"Permission file missing: {permission_path}",
            "notes": ["Load failure"],
            "checks": ["file_exists"],
            "checked_at": ts_now.isoformat(),
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "version": "v0.1",
            "status": "NOT_FOUND",
            "decision": "REVIEW",
            "matched_permission_id": None,
            "reason": f"Permission file parse error: {exc}",
            "notes": ["Invalid permission JSON"],
            "checks": ["parse_json"],
            "checked_at": ts_now.isoformat(),
        }

    registry = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(registry, list):
        return {
            "version": "v0.1",
            "status": "NOT_FOUND",
            "decision": "REVIEW",
            "matched_permission_id": None,
            "reason": "Permission file missing 'permissions' list",
            "notes": ["Invalid permission schema"],
            "checks": ["schema"],
            "checked_at": ts_now.isoformat(),
        }

    actor_l = (actor or "").lower()
    target_l = (target or "").lower()
    method_l = (method or "").lower()
    action_l = (action or "").lower()
    network_l = (network or "").lower()

    def match_entry(entry: Dict[str, Any]) -> bool:
        ent_subject = str(entry.get("subject") or "").lower()
        if ent_subject and actor_l and actor_l != ent_subject:
            return False
        ent_target = str(entry.get("target") or "").lower()
        if ent_target and ent_target != target_l:
            return False
        ent_audience = str(entry.get("audience") or "").lower()
        # Optional audience currently does not auto-match external callers.
        ent_method = str(entry.get("method") or "").lower()
        if ent_method and method_l and ent_method != method_l:
            return False
        ent_action = str(entry.get("action") or "").lower()
        if ent_action and action_l and ent_action != action_l:
            return False
        return True

    matched = None
    for entry in registry:
        if not isinstance(entry, dict):
            continue
        if match_entry(entry):
            matched = entry
            break

    if not matched:
        return {
            "version": "v0.1",
            "status": "NOT_FOUND",
            "decision": "REVIEW",
            "matched_permission_id": None,
            "reason": "No permission entry matched subject/target/action/method",
            "notes": ["scope-mismatch"],
            "checks": ["subject", "target", "action", "method"],
            "checked_at": ts_now.isoformat(),
        }

    pid = matched.get("permission_id") or "unknown"
    state = (matched.get("state") or "revoked").lower()

    # lifecycle checks
    now = ts_now
    not_before = _parse_iso_ts(matched.get("not_before"))
    expires_at = _parse_iso_ts(matched.get("expires_at"))
    if state == "revoked":
        return _permission_scope_result("REVOKED", "DENY", pid, f"Permission revoked ({pid})", ["state"], now)
    if expires_at and now > expires_at:
        return _permission_scope_result("EXPIRED", "DENY", pid, f"Permission expired at {expires_at.isoformat()}", ["expiry"], now)
    if not_before and now < not_before:
        return _permission_scope_result("NOT_ACTIVE", "REVIEW", pid, f"Permission not active before {not_before.isoformat()}", ["not_before"], now)

    constraints = matched.get("constraints") or {}
    if not isinstance(constraints, dict):
        constraints = {}

    # allowlist constraints
    allowed_contracts = [str(x).lower() for x in (constraints.get("allowed_contracts") or [])]
    allowed_methods = [str(x).lower() for x in (constraints.get("allowed_methods") or [])]
    allowed_networks = [str(x).lower() for x in (constraints.get("allowed_networks") or [])]

    if allowed_contracts and target_l and target_l not in allowed_contracts:
        return _permission_scope_result("OUT_OF_SCOPE", "DENY", pid, f"Target '{target}' not in allowed_contracts", ["allowed_contracts"], now)
    if allowed_methods and method_l and method_l not in allowed_methods:
        return _permission_scope_result("OUT_OF_SCOPE", "DENY", pid, f"Method '{method}' not allowed", ["allowed_methods"], now)
    if allowed_networks and network_l and network_l not in allowed_networks:
        return _permission_scope_result("OUT_OF_SCOPE", "DENY", pid, f"Network '{network}' not allowed", ["allowed_networks"], now)

    max_amount = _safe_float(constraints.get("max_amount"), 0.0)
    max_value_usd = _safe_float(constraints.get("max_value_usd"), 0.0)
    if max_amount > 0 and amount > max_amount:
        return _permission_scope_result("LIMIT_EXCEEDED", "DENY", pid, f"Amount {amount} exceeds max_amount {max_amount}", ["amount"], now)
    if max_value_usd > 0 and value_usd > max_value_usd:
        return _permission_scope_result("LIMIT_EXCEEDED", "DENY", pid, f"Value USD {value_usd} exceeds max_value_usd {max_value_usd}", ["value_usd"], now)

    single_use = bool(constraints.get("single_use", False))
    usage_count = int(matched.get("usage_count") or 0)
    if single_use and usage_count >= 1:
        return _permission_scope_result("CONSUMED", "DENY", pid, f"single_use permission already consumed ({usage_count})", ["single_use"], now)

    rate_limit = constraints.get("rate_per_minute")
    if rate_limit is not None:
        try:
            rate_limit_f = int(rate_limit)
            seen_min = int(matched.get("usage_last_minute") or 0)
            if seen_min > rate_limit_f:
                return _permission_scope_result("RATE_LIMIT", "HOLD", pid, f"usage_last_minute {seen_min} exceeds rate_per_minute {rate_limit_f}", ["rate_per_minute"], now)
        except Exception:
            pass

    return {
        "version": "v0.1",
        "status": "GRANTED",
        "decision": "ALLOW",
        "matched_permission_id": pid,
        "reason": "Permission checks passed",
        "notes": ["lifecycle_ok", "scope_ok", "constraints_ok"],
        "checks": ["state", "scope", "constraints"],
        "checked_at": now.isoformat(),
    }


def _permission_scope_result(status: str, decision: str, permission_id: str, reason: str, checks: List[str], checked_at_dt: datetime) -> Dict[str, Any]:
    return {
        "version": "v0.1",
        "status": status,
        "decision": decision,
        "matched_permission_id": permission_id,
        "reason": reason,
        "notes": list(checks),
        "checks": list(checks),
        "checked_at": checked_at_dt.isoformat(),
    }


def _apply_permission_to_synthesis(permission: Dict[str, Any], synthesis: Dict[str, Any], executor_mode: str) -> Dict[str, Any]:
    """Apply permission-scope constraints as hard/soft controls."""
    status = permission.get("status") or "NOT_FOUND"
    decision = permission.get("decision") or "REVIEW"
    reason = permission.get("reason") or "No permission scope reason provided"

    decision = str(decision).upper()
    recommendation = synthesis.get("recommendation", "Conditional")
    confidence = synthesis.get("confidence", "Medium")
    risk = synthesis.get("risk", "Medium")
    adjustments = synthesis.get("policy_adjustments", []) or []

    if isinstance(adjustments, list):
        adjustments.append(f"permission_scope: {status} ({reason})")

    if decision == "DENY":
        recommendation = "Hold"
        confidence = "Low"
        risk = "High"
        synthesis["action_decision"] = "BLOCK"
    elif decision == "HOLD":
        if recommendation == "Approve":
            recommendation = "Conditional"
        synthesis["action_decision"] = "REVIEW"
        risk = "Medium"
        if confidence not in ["Low"]:
            confidence = "Medium"
    elif decision == "ALLOW":
        if status != "GRANTED":
            # keep existing action decision
            pass
    else:
        if synthesis.get("action_decision") != "BLOCK":
            synthesis["action_decision"] = "REVIEW"

    synthesis["recommendation"] = recommendation
    synthesis["confidence"] = confidence
    synthesis["risk"] = risk
    synthesis["policy_adjustments"] = adjustments[:6]
    synthesis["permission_scope"] = {
        "status": status,
        "decision": decision,
        "reason": reason,
        "permission_id": permission.get("matched_permission_id"),
        "checks": permission.get("checks", []),
        "checked_at": permission.get("checked_at"),
    }

    # align with action gate
    if decision == "DENY":
        synthesis["policy_adjustments"].append("permission_scope: hard block")

    return synthesis


def _apply_cost_governor_to_synthesis(cost: Dict[str, Any], synthesis: Dict[str, Any], executor_mode: str) -> Dict[str, Any]:
    """Apply cost governor outputs to synthesis adjustments and risk posture."""
    status = str(cost.get("status") or "OK").upper()
    decision = str(cost.get("decision") or "ALLOW").upper()
    reason = cost.get("reason") or "No cost governor reason provided"

    recommendations = synthesis.get("recommendation", "Conditional")
    confidence = synthesis.get("confidence", "Medium")
    risk = synthesis.get("risk", "Medium")
    adjustments = synthesis.get("policy_adjustments", []) or []

    if isinstance(adjustments, list):
        adjustments.append(f"cost_governor: {status}/{decision} ({reason})")

    if status == "BLOCK" or decision == "DENY":
        synthesis["action_decision"] = "BLOCK"
        recommendations = "Hold"
        confidence = "Low"
        risk = "High"
        if "cost_governor: hard block" not in adjustments:
            adjustments.append("cost_governor: hard block")
    elif status == "HOLD" or decision == "REVIEW":
        if recommendations == "Approve":
            recommendations = "Conditional"
        synthesis["action_decision"] = "REVIEW"
        risk = "Medium"
        if confidence not in ["Low"]:
            confidence = "Medium"

    synthesis["recommendation"] = recommendations
    synthesis["confidence"] = confidence
    synthesis["risk"] = risk
    synthesis["policy_adjustments"] = adjustments[:10]
    synthesis["cost_governor"] = {
        "status": status,
        "decision": decision,
        "reason": reason,
        "auto_action": cost.get("auto_action"),
        "metrics": cost.get("metrics", {}),
    }

    return synthesis


def _merge_action_decisions(a: str, b: str) -> str:
    if not a:
        return b
    if "BLOCK" in (a, b):
        return "BLOCK"
    if "REVIEW" in (a, b):
        return "REVIEW"
    return a or b


def _apply_policy_to_synthesis(policy: Dict[str, Any], synthesis: Dict[str, Any], executor_mode: str) -> Dict[str, Any]:
    """Apply policy summary as hard constraints on the provisional verdict."""
    policy_summary = policy.get("summary", {})
    status = (policy_summary.get("status") or "PASS").upper()
    score = int(policy_summary.get("score", 0) or 0)
    warn_count = int(policy_summary.get("warn_count", 0) or 0)
    fail_count = int(policy_summary.get("fail_count", 0) or 0)
    checks = policy.get("checks", []) or []
    action_decision = _derive_action_decision(status, score, warn_count, fail_count, checks)
    adjustments = []

    recommendation = synthesis.get("recommendation", "Conditional")
    confidence = synthesis.get("confidence", "Low")
    risk = synthesis.get("risk", "Unknown")

    # deterministic score-based policy impact
    if score >= POLICY_THRESHOLD["score_hold"] or status == "FAIL":
        adjustments.append("policy_score: hard hold")
        recommendation = "Hold"
        confidence = "Low"
        risk = "High"
    elif score >= POLICY_THRESHOLD["warn_hold"] or (status == "WARN" and warn_count >= 2):
        adjustments.append("policy_score: hard hold")
        recommendation = "Hold"
        confidence = "Low" if confidence != "Low" else confidence
        risk = "High"
    elif score >= POLICY_THRESHOLD["score_conditional"]:
        adjustments.append("policy_score: conditional")
        if recommendation not in ["Hold", "Conditional"]:
            recommendation = "Conditional"
    elif status == "WARN":
        adjustments.append("policy_warn: enforce safe posture")
        if recommendation not in ["Hold", "Conditional"]:
            recommendation = "Conditional"
        if confidence in ["Medium", "High"]:
            confidence = "Medium"

    if action_decision == "BLOCK" or status == "FAIL" or score >= POLICY_THRESHOLD["score_hold"]:
        recommendation = "Hold"
        risk = "High"
        if "policy_score: hard hold" not in adjustments:
            adjustments.append("policy_score: hard hold")
    elif risk != "High" and status == "WARN":
        risk = "Medium"

    if action_decision == "REVIEW" and recommendation == "Approve":
        recommendation = "Conditional"

    synthesis.setdefault("assumptions", []).append("Policy constraints applied by runner governance layer.")
    synthesis["policy_adjustments"] = adjustments
    synthesis["action_decision"] = action_decision
    synthesis["policy_score"] = score
    synthesis["policy_risk_score_card"] = {
        "status": status,
        "score": score,
        "warn_count": warn_count,
        "fail_count": int(policy_summary.get("fail_count", 0) or 0),
        "breakdown": policy_summary.get("weighted_breakdown", []),
    }
    synthesis["recommendation"] = recommendation
    synthesis["confidence"] = confidence
    synthesis["risk"] = risk
    return synthesis


def _build_actions(manifest: Dict[str, Any], policy: Dict[str, Any], mode: str) -> str:
    checks = policy.get("checks", [])
    warning_lines = [f"- {c['id']}: {c['status']} — {c.get('note', '')}" for c in checks]

    synthesis = manifest.get("synthesis", {})
    recommendation = synthesis.get("recommendation", "Conditional")
    confidence = synthesis.get("confidence", "Low")
    risk = synthesis.get("risk", "Unknown")

    policy_summary = policy.get("summary", {})
    policy_score = policy_summary.get("score", 0)
    policy_warn = policy_summary.get("warn_count", 0)
    policy_fail = policy_summary.get("fail_count", 0)
    action = policy.get("action_decision", "REVIEW")
    evidence_id = policy.get("evidence_id", "-")

    base = [
        "# Next Actions (stub)",
        "",
        "1) Oracle 최종 확정: TL;DR + recommendation 정리",
        "2) Policy check에서 FAIL/WARN 항목이 있으면 수동 승인/보완 후 재실행",
        "3) Notion Decision Log mirror 또는 CURRENT_STATE 업로드",
        "",
        "## Policy check summary",
    ] + warning_lines

    cost_gate = manifest.get("cost_governor_check", {})
    base.extend(
        [
            "",
            "## Summary",
            f"- Recommendation: {recommendation}",
            f"- Action: {action}",
            f"- Confidence: {confidence}",
            f"- Risk: {risk}",
            f"- Evidence ID: {evidence_id}",
            f"- Cost governor: {cost_gate.get('status', '-')}/{cost_gate.get('decision', '-')}",
            f"- Cost reason: {cost_gate.get('reason', '-')}",
        ]
    )

    if mode == "pro":
        if policy_fail > 0:
            base.extend(
                [
                    "",
                    "## Policy scorecard",
                    f"- score={policy_score} (hard gate)",
                    f"- fail_count={policy_fail}",
                    f"- warn_count={policy_warn}",
                    "- FAIL가 존재하면 즉시 Hold 강제",
                ]
            )
        elif policy_score >= POLICY_THRESHOLD["warn_hold"]:
            base.extend(
                [
                    "",
                    "## Policy scorecard",
                    f"- score={policy_score} (conditional/high risk)",
                    "- WARN/리스크 누적이 높아 수동 보완 후 재실행 추천",
                ]
            )
        elif policy_score >= POLICY_THRESHOLD["warn_conditional"]:
            base.extend(
                [
                    "",
                    "## Policy scorecard",
                    f"- score={policy_score} (attention)",
                    "- 안전 조치 후 승인/재실행 고려",
                ]
            )

    if mode == "pro" and any(c.get("status") in ("WARN", "FAIL") for c in checks):
        base.extend(
            [
                "",
                "## Action required",
                "- Policy check 이슈가 있으므로 L3 경로/외부 공개/금융/서명 항목은 보류",
                "- 증빙 패키지(정정본) 재생성 추천",
            ]
        )

    return "\n".join(base)


def _build_summary_html(report_text: str, manifest: Dict[str, Any], policy: Dict[str, Any]) -> str:
    synthesis = manifest.get("synthesis", {})
    policy_summary = policy.get("summary", {})
    status = policy_summary.get("status", "PASS")
    status_class = "ok" if status == "PASS" else ("warn" if status == "WARN" else "bad")
    policy_badges = "".join([
        f"<span class='badge {'ok' if c.get('status') == 'PASS' else ('warn' if c.get('status') in ['WARN','WARN'] else 'bad')}'>{c['id']}: {c['status']}</span>"
        for c in policy.get('checks', [])
    ])

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>AOI Council Proof Pack</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1, h2 {{ color: #1f2937; }}
    .meta {{ background: #f7f7f9; padding: 12px; border-left: 4px solid #3b82f6; margin: 12px 0; }}
    .bad {{ color: #b91c1c; }} .warn {{ color: #92400e; }} .ok {{ color: #166534; }}
    .card {{ border: 1px solid #ddd; padding: 12px; margin: 12px 0; border-radius: 8px; }}
    .badge {{ display: inline-block; margin-right: 8px; padding: 3px 8px; border-radius: 999px; background: #eef2ff; font-size: 0.85rem; }}
    pre {{ background: #111827; color: #f9fafb; padding: 12px; overflow:auto; }}
    .status {{ font-weight: 700; }}
  </style>
</head>
<body>
  <h1>AOI Council Proof Pack</h1>
  <div class="meta">
    <b>Run:</b> {manifest['run_id']}<br />
    <b>Mode:</b> {manifest['executor']}<br />
    <b>Topic:</b> {manifest['inputs']['topic']}<br />
    <b>Time:</b> {manifest['timestamp']}<br />
    <b>Policy:</b> <span class="status {status_class}">{status}</span>
  </div>

  <h2>Verdict</h2>
  <div class="card">
    <div><b>Recommendation:</b> {synthesis.get('recommendation', 'Pending')}</div>
    <div><b>Action:</b> {synthesis.get('action_decision', 'REVIEW')}</div>
    <div><b>Confidence:</b> {synthesis.get('confidence', 'Low')}</div>
    <div><b>Risk:</b> {synthesis.get('risk', 'Unknown')}</div>
    <div><b>Policy score:</b> {policy_summary.get('score', 0)}</div>
    <div><b>Evidence ID:</b> {policy.get('evidence_id', '-')}</div>
    <div><b>Cost governor:</b> {manifest.get("cost_governor_check", {}).get("status", "-")}/{manifest.get("cost_governor_check", {}).get("decision", "-")}</div>
    <div><b>Cost reason:</b> {manifest.get("cost_governor_check", {}).get("reason", "-")}</div>
    <div><b>Permission scope:</b> {manifest.get("permission_scope_check", {}).get("status", "-")}/{manifest.get("permission_scope_check", {}).get("decision", "-")}</div>
    <div><b>Permission id:</b> {manifest.get("permission_scope_check", {}).get("matched_permission_id", "-")}</div>
    <div><b>Policy adjustments:</b> {'; '.join(synthesis.get('policy_adjustments', ['none']))}</div>
  </div>

  <h2>Policy Checks</h2>
  <div class="card">
    {policy_badges}
    {''.join([f"<div><b>{c['id']}:</b> <span class='{ 'bad' if c['status']=='FAIL' else 'warn' if c['status']=='WARN' else 'ok'}'>{c['status']}</span> — {c.get('note', '')}</div>" for c in policy.get('checks', [])])}
  </div>

  <h2>Consensus / Conflict</h2>
  <div class="card">
    <div><b>Consensus:</b> {synthesis.get('consensus', '-')}</div>
    <div><b>Conflict:</b> {synthesis.get('conflict', '-')}</div>
  </div>

  <h2>Policy & Assumptions</h2>
  <div class="card">
    <ul>
      {''.join([f"<li>{a}</li>" for a in synthesis.get('assumptions', [])])}
    </ul>
  </div>

  <h2>Report Snapshot</h2>
  <pre>{report_text[:4000]}</pre>
</body>
</html>
"""




def generate_report(manifest: Dict[str, Any]) -> str:
    """Render the human-readable Markdown report from the manifest."""
    m = manifest
    lines: List[str] = []
    lines.append(f"# Team Council ({m['executor'].capitalize()}) — {m['inputs']['mode']}")
    lines.append("")
    lines.append(f"**Date:** {m['timestamp']}")
    lines.append(f"**Topic:** {m['inputs']['topic']}")
    if m['inputs'].get('context'):
        lines.append(f"**Context:** {m['inputs']['context']}")
    lines.append("")

    synthesis = m.get("synthesis", {})

    lines.append("## TL;DR")
    lines.append(f"Recommendation={synthesis.get('recommendation', 'Pending')}, Confidence={synthesis.get('confidence', 'Low')}, Risk={synthesis.get('risk', 'Unknown')}")
    lines.append("")

    lines.append("## Cross-Critique (3-pass scaffold)")
    lines.append("")

    if m["executor"] == "pro":
        lines.append("### Pass A (Initial)")
        for r in m['roles']:
            lines.append(f"- **{r['label']}**: {r.get('pass_a_output', r.get('output', 'No output'))}")

        lines.append("")
        lines.append("### Pass B (Cross-Critique)")
        for c in m.get('critiques', []):
            lines.append(f"- **{c['critic_label']}** -> **{c['target_label']}**: {c['critique']}")

        lines.append("")
        lines.append("### Pass C (Revision)")
        for r in m['roles']:
            lines.append(f"- **{r['label']}**: {r.get('pass_c_output', 'No revision')}")
    else:
        for r in m['roles']:
            lines.append(f"- **{r['label']}**: {r.get('output', 'No output')}")

    lines.append("")
    lines.append("## Consensus / Conflict")
    lines.append(synthesis.get("consensus", "(pending)"))
    lines.append("")
    lines.append("## Dissent")
    dissent = synthesis.get("dissent", []) or ["(no formal dissent extracted)"]
    for d in dissent:
        lines.append(f"- {d}")
    lines.append("")
    lines.append("## Assumptions")
    for a in synthesis.get("assumptions", [])[:3]:
        lines.append(f"- {a}")
    lines.append("")

    lines.append("## Verdict")
    lines.append(f"- **Recommendation:** {synthesis.get('recommendation', 'Pending')}")
    lines.append(f"- **Action:** {synthesis.get('action_decision', 'REVIEW')}")
    lines.append(f"- **Confidence:** {synthesis.get('confidence', 'Low')}")
    lines.append(f"- **Risk:** {synthesis.get('risk', 'Unknown')}")
    evidence_id = manifest.get("policy_check", {}).get("evidence_id")
    if evidence_id:
        lines.append(f"- **Policy evidence_id:** {evidence_id}")
    cost_scope = manifest.get("cost_governor_check", {})
    if cost_scope:
        lines.append(f"- **Cost governor:** {cost_scope.get('status', '-')}/{cost_scope.get('decision', '-')}")
        lines.append(f"- **Cost reason:** {cost_scope.get('reason', '-')}")
        metrics = cost_scope.get("metrics", {})
        spent = metrics.get("budget", {}).get("spent") if isinstance(metrics.get("budget", {}), dict) else None
        if spent is not None:
            lines.append(f"- **Cost spent:** {spent}")

    permission_scope = manifest.get("permission_scope_check", {})
    if permission_scope:
        lines.append(f"- **Permission status:** {permission_scope.get('status', '-')}")
        lines.append(f"- **Permission decision:** {permission_scope.get('decision', '-')}")
        if permission_scope.get("matched_permission_id") is not None:
            lines.append(f"- **Permission id:** {permission_scope.get('matched_permission_id')}")
        if permission_scope.get("reason"):
            lines.append(f"- **Permission reason:** {permission_scope.get('reason')}")

    policy_adjustments = synthesis.get("policy_adjustments", [])
    if policy_adjustments:
        lines.append("- **Policy adjustments:**")
        for item in policy_adjustments:
            lines.append(f"  - {item}")

    lines.append("")
    lines.append("## Policy Check")
    policy_summary = manifest.get("policy_check", {}).get("summary", {})
    if policy_summary:
        lines.append(
            f"- **Policy status:** {policy_summary.get('status', 'PASS')} "
            f"(score={policy_summary.get('score', 0)}, warn={policy_summary.get('warn_count', 0)}, fail={policy_summary.get('fail_count', 0)})"
        )
    for c in manifest.get("policy_check", {}).get("checks", []):
        lines.append(f"- **{c['id']}**: {c['status']} — {c.get('note', '')}")

    lines.append("")
    lines.append("## Next Actions")
    lines.append("(stub: see actions.md)")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="AOI Council Runner (Lite/Pro)")
    parser.add_argument("--mode", required=True, choices=["decision", "planning", "evaluation"], help="Council mode")
    parser.add_argument("--topic", required=True, help="Topic for discussion")
    parser.add_argument("--context", help="Additional context")
    parser.add_argument("--pro", action="store_true", help="Request Pro mode (11 roles)")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for proofs. If omitted: Pro -> SSOT proof_samples; Lite -> /tmp",
    )
    parser.add_argument(
        "--evidence-path",
        action="append",
        default=None,
        help="Optional evidence file paths for policy checks (repeatable)",
    )
    parser.add_argument(
        "--permission-scope",
        default=os.environ.get("AOI_PERMISSION_SCOPE_PATH"),
        help="Optional permission scope JSON file path (v0.1)",
    )
    parser.add_argument(
        "--actor-id",
        default=os.environ.get("AOI_DEFAULT_ACTOR_ID", "manual"),
        help="Actor identifier used for permission scope matching",
    )
    parser.add_argument(
        "--target",
        default="web-or-cli",
        help="Permission scope target identifier",
    )
    parser.add_argument(
        "--method",
        default="cli",
        help="Permission scope method",
    )
    parser.add_argument(
        "--action",
        default="propose",
        help="Permission scope action",
    )
    parser.add_argument(
        "--amount",
        type=float,
        default=0.0,
        help="Optional amount for scope limit check",
    )
    parser.add_argument(
        "--value-usd",
        type=float,
        default=0.0,
        help="Optional value in USD for scope limit check",
    )
    parser.add_argument(
        "--network",
        default="",
        help="Optional network tag for scope network allowlist",
    )
    parser.add_argument(
        "--estimated-cost-usd",
        type=float,
        default=0.0,
        help="Estimated cost/cost proxy in USD for this council run",
    )
    parser.add_argument(
        "--retry-attempt",
        type=int,
        default=0,
        help="Observed retry attempt count for this run (used by cost governor)",
    )
    parser.add_argument(
        "--cost-governor-state",
        default=os.environ.get("AOI_COST_GOVERNOR_STATE_PATH", "/tmp/aoi_cost_governor_state_v0_1.json"),
        help="Path to cost governor state JSON",
    )
    parser.add_argument(
        "--cost-governor-config",
        default=None,
        help="Optional AOI cost governor JSON config path",
    )

    args = parser.parse_args()

    # load policy + cost governor config at startup
    _load_policy_config()
    cost_governor_policy = _load_cost_governor_config(args.cost_governor_config)

    # 1) Init manifest
    run_id = f"council_{int(time.time())}_{_slug(args.topic)}"
    executor_mode = detect_orchestrator_mode(args.pro)

    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "timestamp": get_timestamp(),
        "executor": executor_mode,
        "schema": {
            "council_runner_version": VERSION,
            "proof_pack_schema_version": PROOF_PACK_SCHEMA_VERSION,
        },
        "inputs": {
            "mode": args.mode,
            "topic": args.topic,
            "context": args.context,
            "evidence_paths": args.evidence_path,
            "permission_scope_path": args.permission_scope,
            "actor": args.actor_id,
            "target": args.target,
            "method": args.method,
            "action": args.action,
            "amount": args.amount,
            "value_usd": args.value_usd,
            "network": args.network,
            "estimated_cost_usd": args.estimated_cost_usd,
            "retry_attempt": args.retry_attempt,
            "cost_governor_state": args.cost_governor_state,
        },
        "roles": [],
        "verdict": {},
        "failures": [],
        "critiques": [],
        "synthesis": {},
    }

    # 2) Select roster
    if executor_mode == "pro":
        full_roster = pro_adapter.get_pro_roster()
        roster = _select_smart_roster(full_roster, args.topic, args.context)
        manifest["roster"] = {
            "selected": [r.get("id") for r in roster],
            "full_count": len(full_roster),
            "selected_count": len(roster),
            "policy": "smart_roster_v0.1",
        }
    else:
        roster = ROSTER_LITE

    print(f"🚀 Starting AOI Council Run [{run_id}] in [{executor_mode.upper()}] mode with {len(roster)} roles...")

    # 3) Execute initial pass
    for role_def in roster:
        print(f"  > Invoking {role_def['label']}...")
        base_output = _invoke_agent(role_def, args.topic, executor_mode, args.context)

        role_result = role_def.copy()
        role_result["pass_a_output"] = base_output
        role_result["output"] = base_output
        role_result["status"] = "success"
        role_result["pass_b_output"] = []
        role_result["pass_c_output"] = ""
        role_result["critiques_received"] = []
        manifest["roles"].append(role_result)

    # 4) Cross-critique + synthesis
    synthesis_out = _synthesize_passes(manifest["roles"], args.topic, args.context, executor_mode)
    manifest["roles"] = synthesis_out["roles"]
    manifest["critiques"] = synthesis_out["critiques"]
    manifest["synthesis"] = synthesis_out["synthesis"]

    # 5) Policy and permission checks for Pro/Lite proof pack + deterministic verdict override
    policy = _policy_check(manifest["inputs"], executor_mode, args.evidence_path)
    manifest["policy_check"] = policy

    # Apply policy constraints to provisional synthesis
    manifest["synthesis"] = _apply_policy_to_synthesis(policy, manifest["synthesis"], executor_mode)

    permission = _permission_scope_check(
        actor=args.actor_id,
        target=args.target,
        method=args.method,
        action=args.action,
        amount=args.amount,
        value_usd=args.value_usd,
        network=args.network,
        permission_path=args.permission_scope,
    )
    manifest["permission_scope_check"] = permission
    manifest["synthesis"] = _apply_permission_to_synthesis(permission, manifest["synthesis"], executor_mode)

    # final action gate = policy + permission + cost gates (fail-closed)
    permission_action = permission.get("decision", "REVIEW")
    if permission_action == "DENY":
        permission_action = "BLOCK"
    elif permission_action == "ALLOW":
        permission_action = "ALLOW"
    elif permission_action == "HOLD":
        permission_action = "REVIEW"

    cost_governor = _cost_governor_check(
        actor=args.actor_id,
        estimated_cost_usd=args.estimated_cost_usd,
        retry_attempt=args.retry_attempt,
        mode=executor_mode,
        state_path=args.cost_governor_state,
        config=cost_governor_policy,
    )

    cost_action = cost_governor.get("decision", "REVIEW")
    if cost_action == "DENY" or cost_governor.get("status") == "BLOCK":
        cost_action = "BLOCK"
    elif cost_action == "ALLOW":
        cost_action = "ALLOW"
    else:
        cost_action = "REVIEW"

    manifest["synthesis"] = _apply_cost_governor_to_synthesis(cost_governor, manifest["synthesis"], executor_mode)
    manifest["synthesis"]["action_decision"] = _merge_action_decisions(
        manifest["synthesis"].get("action_decision", "REVIEW"),
        permission_action,
    )
    manifest["synthesis"]["action_decision"] = _merge_action_decisions(
        manifest["synthesis"].get("action_decision", "REVIEW"),
        cost_action,
    )
    if permission.get("decision") == "DENY" or cost_governor.get("status") == "BLOCK":
        manifest["synthesis"]["recommendation"] = "Hold"

    manifest["cost_governor_check"] = cost_governor
    manifest["synthesis"]["cost_governor"] = {
        "status": cost_governor.get("status"),
        "decision": cost_governor.get("decision"),
        "auto_action": cost_governor.get("auto_action"),
        "reason": cost_governor.get("reason"),
        "metrics": cost_governor.get("metrics", {}),
    }

    manifest["verdict"] = {
        "recommendation": manifest["synthesis"].get("recommendation", "Pending"),
        "confidence": manifest["synthesis"].get("confidence", "Low"),
        "risk": manifest["synthesis"].get("risk", "Unknown"),
        "policy_adjustments": manifest["synthesis"].get("policy_adjustments", []),
        "action": manifest["synthesis"].get("action_decision", "REVIEW"),
        "evidence_id": manifest.get("policy_check", {}).get("evidence_id"),
        "permission": {
            "status": permission.get("status"),
            "decision": permission.get("decision"),
            "permission_id": permission.get("matched_permission_id"),
        },
        "cost_governor": {
            "status": cost_governor.get("status"),
            "decision": cost_governor.get("decision"),
            "auto_action": cost_governor.get("auto_action"),
            "reason": cost_governor.get("reason"),
        },
    }

    # escalate failures for deterministic visibility
    if policy.get("summary", {}).get("status") in ["WARN", "FAIL"]:
        manifest["failures"].append(f"policy_check_{policy['summary']['status']}")
    if permission.get("decision") == "DENY":
        manifest["failures"].append("permission_scope_denied")
    if cost_governor.get("status") == "BLOCK":
        manifest["failures"].append("cost_governor_block")

    # 6) Save proof pack artifacts
    if args.out_dir:
        base_out = Path(args.out_dir)
    else:
        if executor_mode == "pro":
            repo_root = Path(__file__).resolve().parents[1]
            base_out = repo_root / "context" / "proof_samples" / "council_runs"
        else:
            base_out = Path("/tmp")

    out_path = base_out / run_id
    out_path.mkdir(parents=True, exist_ok=True)

    report_content = generate_report(manifest)
    report_file = out_path / "report.md"
    report_file.write_text(report_content, encoding="utf-8")

    manifest["outputs"] = {
        "proof_pack_dir": str(out_path),
        "report_md": str(report_file),
        "manifest_json": str(out_path / "manifest.json"),
        "policy_check_json": str(out_path / "policy_check.json"),
        "policy_scorecard_json": str(out_path / "policy_scorecard.json"),
        "actions_md": str(out_path / "actions.md"),
        "summary_html": str(out_path / "summary.html"),
    }

    manifest_file = out_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    policy_file = out_path / "policy_check.json"
    policy_file.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")

    # Additional deterministic policy scorecard artifact for downstream governance pipeline
    scorecard_file = out_path / "policy_scorecard.json"
    scorecard_file.write_text(
        json.dumps(policy.get("summary", {}), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    actions_file = out_path / "actions.md"
    actions_file.write_text(_build_actions(manifest, policy, executor_mode), encoding="utf-8")

    summary_file = out_path / "summary.html"
    summary_file.write_text(_build_summary_html(report_content, manifest, policy), encoding="utf-8")

    print("✅ Run complete.")
    print(f"   📂 Proof Pack: {out_path}")
    print(f"   📄 Report: {report_file}")
    print(f"   💾 Manifest: {manifest_file}")
    print(f"   🛡️ Policy check: {policy_file}")
    print(f"   📈 Summary: {summary_file}")


if __name__ == "__main__":
    main()
