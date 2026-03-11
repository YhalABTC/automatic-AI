#!/usr/bin/env python3
"""Mirror local SSOT decisions to Notion Decision Log DB.

- Reads Notion token from `the-alpha-oracle/vault/notion.env` or `the-alpha-oracle/vault/notion_token.txt`.
- Uses target DB from `context/NOTION_DECISION_LOG_TARGET_SSOT_V0_1.md`.
- Ensures a Date property for write timestamp exists (default name: 작성시간).

Safety:
- Never uploads raw longform documents.
- Only uploads summaries + local evidence paths.

Create behavior (upgraded):
- Creates a page body in the existing Decision Log style:
  Topic / Context / Constraints / TL;DR / Evidence / Next actions
- Attempts to set common DB properties if they exist, but never requires schema changes.

Usage:
  python3 scripts/notion_decision_log_mirror.py ensure-schema
  python3 scripts/notion_decision_log_mirror.py create --title "..." --summary "..." --paths "a,b,c" [--exposure OPEN]
  python3 scripts/notion_decision_log_mirror.py create --title "..." --topic "..." --context "..." --constraints "..." --tldr "..." --next-actions "a;b;c" --paths "a,b,c"
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

NOTION_VERSION = "2022-06-28"

TOKEN_ENV_PATH = Path("the-alpha-oracle/vault/notion.env")
TOKEN_TXT_PATH = Path("the-alpha-oracle/vault/notion_token.txt")
TARGET_SSOT_PATH = Path("context/NOTION_DECISION_LOG_TARGET_SSOT_V0_1.md")

DEFAULT_TITLE_PROP = "Name"  # common default in Notion DB
DEFAULT_TIME_PROP = "작성시간"  # requested

# Common Decision Log columns (optional; only set if they exist)
PROP_EXPOSURE = "Exposure"
PROP_STATUS = "Status"
PROP_RECOMMENDATION = "Recommendation"
PROP_MODE = "Mode"
PROP_RISK = "Risk"
PROP_CONFIDENCE = "Confidence"
PROP_TAGS = "Tags"
PROP_PROJECT = "Project"
PROP_SOURCE_URL = "Source URL"

# Policy-score fields (optional)
PROP_POLICY_STATUS = "Policy Status"
PROP_POLICY_SCORE = "Policy Score"
PROP_POLICY_WARN_COUNT = "Policy Warn Count"
PROP_POLICY_FAIL_COUNT = "Policy Fail Count"
PROP_POLICY_SCORECARD = "Policy Scorecard"

# Legacy optional text properties
DEFAULT_SUMMARY_PROP = "Summary"  # optional
DEFAULT_PATHS_PROP = "EvidencePaths"  # optional


def now_kst_iso() -> str:
    """Return current time in KST ISO string with +09:00 offset."""
    from datetime import timedelta

    utc = datetime.now(timezone.utc)
    kst_dt = utc + timedelta(hours=9)
    return kst_dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")


def load_token() -> str:
    if TOKEN_ENV_PATH.exists():
        txt = TOKEN_ENV_PATH.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"NOTION_TOKEN\s*=\s*(\S+)", txt)
        if m:
            return m.group(1).strip()
    if TOKEN_TXT_PATH.exists():
        return TOKEN_TXT_PATH.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0]
    raise FileNotFoundError("Notion token not found in vault.")


def load_db_id() -> str:
    txt = TARGET_SSOT_PATH.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"Database ID:\s*([0-9a-f]{32})", txt)
    if not m:
        raise ValueError("Database ID not found in target SSOT.")
    return m.group(1)


def notion_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_db(token: str, db_id: str) -> dict[str, Any]:
    url = f"https://api.notion.com/v1/databases/{db_id}"
    r = requests.get(url, headers=notion_headers(token), timeout=30)
    r.raise_for_status()
    return r.json()


def patch_db_add_date_property(token: str, db_id: str, prop_name: str) -> None:
    url = f"https://api.notion.com/v1/databases/{db_id}"
    payload = {"properties": {prop_name: {"date": {}}}}
    r = requests.patch(url, headers=notion_headers(token), json=payload, timeout=30)
    r.raise_for_status()


def ensure_schema(token: str, db_id: str) -> None:
    db = get_db(token, db_id)
    props = db.get("properties", {})

    if DEFAULT_TIME_PROP not in props:
        patch_db_add_date_property(token, db_id, DEFAULT_TIME_PROP)
        print(f"added_property:{DEFAULT_TIME_PROP}")
    else:
        print(f"property_exists:{DEFAULT_TIME_PROP}")


def find_title_prop(db_props: dict[str, Any]) -> str:
    # locate the title property (type == title)
    for k, v in db_props.items():
        if v.get("type") == "title":
            return k
    return DEFAULT_TITLE_PROP


def _set_prop_value(db_props: dict[str, Any], prop_name: str, value: Any) -> dict[str, Any] | None:
    """Return a Notion property payload for the given prop if present, else None.

    Supports: select, multi_select, rich_text, url.
    """
    if prop_name not in db_props or value is None:
        return None

    t = db_props[prop_name].get("type")

    if t == "select":
        return {"select": {"name": str(value)}}

    if t == "multi_select":
        if isinstance(value, str):
            items = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, list):
            items = [str(v).strip() for v in value if str(v).strip()]
        else:
            items = [str(value).strip()]
        return {"multi_select": [{"name": n} for n in items]}

    if t == "url":
        return {"url": str(value)}

    # rich_text fallback
    return {"rich_text": [{"text": {"content": str(value)[:1900]}}]}


def _heading(text: str, level: int = 2) -> dict[str, Any]:
    typ = f"heading_{level}"
    return {
        "object": "block",
        "type": typ,
        typ: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _bullets(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        out.append(
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": ln[:2000]}}]
                },
            }
        )
    return out


def patch_page_properties(token: str, page_id: str, props: dict[str, Any]) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(url, headers=notion_headers(token), json={"properties": props}, timeout=30)
    r.raise_for_status()


def create_page(
    token: str,
    db_id: str,
    title: str,
    summary: str,
    paths: list[str],
    exposure: str | None,
    *,
    topic: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    tldr: str | None = None,
    next_actions: list[str] | None = None,
    status: str | None = None,
    recommendation: str | None = None,
    mode: str | None = None,
    risk: str | None = None,
    confidence: str | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
    policy_status: str | None = None,
    policy_score: int | None = None,
    policy_warn_count: int | None = None,
    policy_fail_count: int | None = None,
    policy_scorecard: str | None = None,
) -> dict[str, Any]:
    db = get_db(token, db_id)
    props = db.get("properties", {})
    title_prop = find_title_prop(props)

    page_props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": title}}]},
        DEFAULT_TIME_PROP: {"date": {"start": now_kst_iso()}},
    }

    # Optional properties (only if exist in DB)
    if DEFAULT_SUMMARY_PROP in props:
        page_props[DEFAULT_SUMMARY_PROP] = {"rich_text": [{"text": {"content": (tldr or summary)[:1900]}}]}

    if DEFAULT_PATHS_PROP in props:
        page_props[DEFAULT_PATHS_PROP] = {"rich_text": [{"text": {"content": "\n".join(paths)[:1900]}}]}

    if PROP_POLICY_SCORECARD in props and policy_scorecard:
        page_props[PROP_POLICY_SCORECARD] = {"rich_text": [{"text": {"content": policy_scorecard[:1900]}}]}

    for k, v in [
        (PROP_EXPOSURE, exposure),
        (PROP_STATUS, status),
        (PROP_RECOMMENDATION, recommendation),
        (PROP_MODE, mode),
        (PROP_RISK, risk),
        (PROP_CONFIDENCE, confidence),
        (PROP_PROJECT, project),
        (PROP_TAGS, tags),
        (PROP_POLICY_STATUS, policy_status),
        (PROP_POLICY_SCORE, policy_score),
        (PROP_POLICY_WARN_COUNT, policy_warn_count),
        (PROP_POLICY_FAIL_COUNT, policy_fail_count),
    ]:
        pv = _set_prop_value(props, k, v)
        if pv is not None:
            page_props[k] = pv

    # Build body in the established style.
    topic_text = topic or title
    context_text = context or "(TBD)"
    constraints_text = constraints or "(TBD)"
    tldr_text = tldr or summary or "(TBD)"

    evidence_lines = paths[:] if paths else []
    if not evidence_lines and summary:
        evidence_lines = ["(no local evidence paths provided)"]

    na = next_actions or []
    if not na:
        na = ["(TBD)"]

    children: list[dict[str, Any]] = []
    children += [_heading("Topic"), _paragraph(topic_text)]
    children += [_heading("Context"), _paragraph(context_text)]
    children += [_heading("Constraints"), _paragraph(constraints_text)]
    children += [_heading("TL;DR"), _paragraph(tldr_text)]
    if policy_status is not None or policy_score is not None:
        children += [_heading("Policy scorecard")]
        policy_lines = []
        if policy_status is not None:
            policy_lines.append(f"Status: {policy_status}")
        if policy_score is not None:
            policy_lines.append(f"Score: {policy_score}")
        if policy_warn_count is not None:
            policy_lines.append(f"Warn: {policy_warn_count}")
        if policy_fail_count is not None:
            policy_lines.append(f"Fail: {policy_fail_count}")
        children += _bullets(policy_lines)
        if policy_scorecard:
            children += _bullets(["score breakdown:", policy_scorecard[:800]])
    children += [_heading("Evidence")]
    children += _bullets(evidence_lines)
    children += [_heading("Next actions")]
    children += _bullets(na)

    payload = {"parent": {"database_id": db_id}, "properties": page_props, "children": children}

    url = "https://api.notion.com/v1/pages"
    r = requests.post(url, headers=notion_headers(token), json=payload, timeout=30)
    r.raise_for_status()
    page = r.json()

    # If DB has Source URL and it's empty, backfill it with the created page URL.
    if PROP_SOURCE_URL in props:
        page_url = page.get("url")
        if page_url:
            try:
                patch_page_properties(token, page["id"], {PROP_SOURCE_URL: {"url": page_url}})
            except Exception:
                # best-effort; never fail create due to a backfill
                pass

    return page


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ensure-schema")

    cp = sub.add_parser("create")
    cp.add_argument("--title", required=True)

    # Backward-compatible minimum inputs
    cp.add_argument("--summary", required=True, help="Used as TL;DR unless --tldr is provided")
    cp.add_argument("--paths", required=True, help="comma-separated local evidence paths")
    cp.add_argument("--exposure", default=None)

    # Body sections (Decision Log style)
    cp.add_argument("--topic", default=None)
    cp.add_argument("--context", default=None)
    cp.add_argument("--constraints", default=None)
    cp.add_argument("--tldr", default=None)
    cp.add_argument("--next-actions", default=None, help="semicolon-separated (e.g., 'a;b;c')")

    # Optional DB columns (only applied if they exist)
    cp.add_argument("--status", default=None)
    cp.add_argument("--recommendation", default=None)
    cp.add_argument("--mode", default=None)
    cp.add_argument("--risk", default=None)
    cp.add_argument("--confidence", default=None)
    cp.add_argument("--project", default=None)
    cp.add_argument("--tags", default=None, help="comma-separated")
    cp.add_argument("--policy-status", default=None)
    cp.add_argument("--policy-score", type=int, default=None)
    cp.add_argument("--policy-warn-count", type=int, default=None)
    cp.add_argument("--policy-fail-count", type=int, default=None)
    cp.add_argument("--policy-scorecard", default=None, help="compact json string for policy scorecard")

    fp = sub.add_parser("fill-missing")
    fp.add_argument("--limit", type=int, default=0, help="0 means all")

    args = ap.parse_args()

    token = load_token()
    db_id = load_db_id()

    if args.cmd == "ensure-schema":
        ensure_schema(token, db_id)
        return

    if args.cmd == "create":
        paths = [p.strip() for p in args.paths.split(",") if p.strip()]
        next_actions = None
        if getattr(args, "next_actions", None):
            next_actions = [x.strip() for x in args.next_actions.split(";") if x.strip()]

        tags = None
        if getattr(args, "tags", None):
            tags = [x.strip() for x in args.tags.split(",") if x.strip()]

        # Safe defaults (only used if the caller didn't supply values)
        res = create_page(
            token,
            db_id,
            args.title,
            args.summary,
            paths,
            args.exposure,
            topic=args.topic,
            context=args.context,
            constraints=args.constraints,
            tldr=args.tldr,
            next_actions=next_actions,
            status=args.status,
            recommendation=args.recommendation,
            mode=args.mode,
            risk=args.risk,
            confidence=args.confidence,
            tags=tags,
            project=args.project,
            policy_status=args.policy_status,
            policy_score=args.policy_score,
            policy_warn_count=args.policy_warn_count,
            policy_fail_count=args.policy_fail_count,
            policy_scorecard=args.policy_scorecard,
        )
        print("created:", res.get("url", "(no url)"))
        return


if __name__ == "__main__":
    main()
