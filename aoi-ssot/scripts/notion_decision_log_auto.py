#!/usr/bin/env python3
"""Notion Decision Log Auto-Writer (v0.1)

Purpose:
- Generate a consistent `notion_decision_log_mirror.py create ...` command from a set of changed paths.
- Dry-run by default to avoid accidental external writes.

Usage examples:
  python3 scripts/notion_decision_log_auto.py \
    --title "SSOT READY promotion" \
    --summary "Promoted X,Y,Z to READY" \
    --paths context/A.md,context/B.md \
    --tags ssot,ready \
    --next-actions "Use claims registry;Run proof tests"

  # Execute (actually writes to Notion):
  python3 scripts/notion_decision_log_auto.py ... --execute

Notes:
- This tool is L1/L2 only. Do not use for L3 actions.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys


def build_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "scripts/notion_decision_log_mirror.py",
        "create",
        "--title",
        args.title,
        "--summary",
        args.summary,
        "--paths",
        args.paths,
        "--tags",
        args.tags,
    ]

    if args.exposure:
        cmd += ["--exposure", args.exposure]
    if args.topic:
        cmd += ["--topic", args.topic]
    if args.constraints:
        cmd += ["--constraints", args.constraints]
    if args.tldr:
        cmd += ["--tldr", args.tldr]
    if args.next_actions:
        # notion_decision_log_mirror expects semicolon-separated
        cmd += ["--next-actions", args.next_actions]

    # policy scorecard fields
    if args.policy_status is not None:
        cmd += ["--policy-status", args.policy_status]
    if args.policy_score is not None:
        cmd += ["--policy-score", str(args.policy_score)]
    if args.policy_warn_count is not None:
        cmd += ["--policy-warn-count", str(args.policy_warn_count)]
    if args.policy_fail_count is not None:
        cmd += ["--policy-fail-count", str(args.policy_fail_count)]
    if args.policy_scorecard is not None:
        cmd += ["--policy-scorecard", args.policy_scorecard]

    return cmd


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--title", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--paths", required=True, help="comma-separated local evidence paths")
    p.add_argument("--tags", required=True, help="comma-separated")

    p.add_argument("--exposure", default="OPEN/TEASER")
    p.add_argument("--topic", default="AOI Core SSOT governance")
    p.add_argument(
        "--constraints",
        default=(
            "L1/L2 only. No money/wallet/on-chain signing/external posting. "
            "Stealth $AOI remains TOP SECRET. Public GitHub hackathon repos are FINAL unless explicitly requested."
        ),
    )
    p.add_argument("--tldr", default=None)
    p.add_argument(
        "--next-actions",
        default="Use READY claims registry for external copy;Run deterministic proof tests before sharing evidence",
        help="semicolon-separated",
    )

    p.add_argument("--policy-status", default=None)
    p.add_argument("--policy-score", type=int, default=None)
    p.add_argument("--policy-warn-count", type=int, default=None)
    p.add_argument("--policy-fail-count", type=int, default=None)
    p.add_argument("--policy-scorecard", default=None)

    p.add_argument("--execute", action="store_true", help="actually call notion_decision_log_mirror.py")

    args = p.parse_args()
    cmd = build_cmd(args)

    printable = " ".join(shlex.quote(x) for x in cmd)
    print("[notion-decision-auto] command:")
    print(printable)

    if not args.execute:
        print("[notion-decision-auto] dry-run (add --execute to create the Notion page)")
        return 0

    print("[notion-decision-auto] executing…")
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
