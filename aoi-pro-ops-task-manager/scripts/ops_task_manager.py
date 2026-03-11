#!/usr/bin/env python3
"""AOI PRO — ops task manager (skill wrapper)

This is a self-contained copy of the workspace hygiene tool.

Edits are limited to ops/items metadata + status hygiene.
"""

import argparse
import datetime as dt
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
ROOT = SKILL_DIR.parents[1]  # workspace root
ITEMS_DIR = ROOT / "ops" / "items"

FM_RE = re.compile(r"^(---\n)(.*?)(\n---\n)(.*)$", re.S)


def load_policy(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def parse_frontmatter(text: str):
    m = FM_RE.match(text)
    if not m:
        return None
    fm = m.group(2)
    body = m.group(4)
    lines = fm.splitlines()
    return lines, body


def write_frontmatter(lines, body):
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def get_kv(lines, key):
    for l in lines:
        if l.startswith(key + ":"):
            return l.split(":", 1)[1].strip()
    return ""


def set_kv(lines, key, value):
    for i, l in enumerate(lines):
        if l.startswith(key + ":"):
            lines[i] = f"{key}: {value}"
            return
    # insert after id if exists
    idx = 0
    for i, l in enumerate(lines):
        if l.startswith("id:"):
            idx = i + 1
            break
    lines.insert(idx, f"{key}: {value}")


def ensure_tag(lines, tag="ralph-loop"):
    for key in ("tags", "labels"):
        for i, l in enumerate(lines):
            if l.startswith(key + ":"):
                if tag in l:
                    return False
                m = re.match(rf"{key}:\s*\[(.*)\]\s*$", l.strip())
                if m:
                    items = [x.strip() for x in m.group(1).split(",") if x.strip()]
                    items = [x for x in items if x != tag]
                    items = [tag] + items
                    lines[i] = f"{key}: [" + ",".join(items) + "]"
                    return True
    lines.append(f"tags: [{tag}]")
    return True


def detect_ralphish(project: str, title: str, body: str):
    t = (project + " " + title + " " + body[:500]).lower()
    if "acp dispatch" in project.lower():
        return True
    if "ralph loop" in t:
        return True
    if "loop-" in t:
        return True
    return False


def canonicalize_oracle_family(files, family_key: str, dry_run: bool):
    def date_from_name(p: Path):
        m = re.match(r"TASK-(\d{8})-ORACLE-\d{2}\.md", p.name)
        return m.group(1) if m else "00000000"

    files_sorted = sorted(files, key=lambda p: date_from_name(p))
    if not files_sorted:
        return []
    canonical = files_sorted[-1]
    changed = []
    for p in files_sorted[:-1]:
        text = p.read_text("utf-8", errors="ignore")
        parsed = parse_frontmatter(text)
        if not parsed:
            continue
        lines, body = parsed
        set_kv(lines, "status", "done")
        set_kv(lines, "priority", "low")
        note = f"\n## Status update\n- Marked as **DONE (duplicate/superseded)**. Canonical task: `{canonical}`.\n"
        if note.strip() not in body:
            body = body + ("\n" if body.endswith("\n") else "\n\n") + note
        new_text = write_frontmatter(lines, body)
        if new_text != text:
            changed.append(str(p))
            if not dry_run:
                p.write_text(new_text, "utf-8")
    return [(family_key, str(canonical), changed)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default=str(SKILL_DIR / "state" / "policy.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    policy = load_policy(Path(args.policy))
    dry_run = args.dry_run or (not args.apply)

    paths = sorted(ITEMS_DIR.glob("*.md"))

    oracle_map = {
        "ORACLE-01": re.compile(r"TASK-\d{8}-ORACLE-01\.md$"),
        "ORACLE-02": re.compile(r"TASK-\d{8}-ORACLE-02\.md$"),
        "ORACLE-03": re.compile(r"TASK-\d{8}-ORACLE-03\.md$"),
    }

    oracle_results = []
    for fam, pat in oracle_map.items():
        fam_files = [p for p in paths if pat.match(p.name)]
        oracle_results += canonicalize_oracle_family(fam_files, fam, dry_run)

    edits = []
    for p in paths:
        text = p.read_text("utf-8", errors="ignore")
        parsed = parse_frontmatter(text)
        if not parsed:
            continue
        lines, body = parsed
        project = get_kv(lines, "project")
        title = get_kv(lines, "title") or p.name

        changed = False
        if policy["rules"]["labeling"]["ensureRalphLoopTag"]["enabled"]:
            if detect_ralphish(project, title, body):
                changed = ensure_tag(lines, "ralph-loop") or changed

        proj_assignee = policy["rules"]["routing"]["projectAssignee"]
        if project in proj_assignee:
            if get_kv(lines, "assignee") == "" and get_kv(lines, "owner") == "":
                set_kv(lines, "assignee", proj_assignee[project])
                changed = True

        if changed:
            new_text = write_frontmatter(lines, body)
            edits.append(str(p))
            if not dry_run and new_text != text:
                p.write_text(new_text, "utf-8")

    out_dir = ROOT / policy["reporting"]["reportDir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    report = out_dir / f"REPORT_{stamp}.md"

    rep = []
    rep.append(f"# AOI PRO ops task manager report ({stamp} KST)")
    rep.append("")
    rep.append(f"- dry_run: **{dry_run}**")
    rep.append(f"- items scanned: **{len(paths)}**")
    rep.append(f"- files edited (label/routing): **{len(edits)}**")
    rep.append("")

    rep.append("## Oracle canonicalization")
    for fam, canonical, changed_files in oracle_results:
        rep.append(f"- {fam}: canonical={canonical} ; older_marked_done={len(changed_files)}")
    rep.append("")

    rep.append("## Edited files")
    for e in edits[:200]:
        rep.append(f"- {e}")
    if len(edits) > 200:
        rep.append(f"- ... ({len(edits)-200} more)")

    report.write_text("\n".join(rep), "utf-8")
    print(str(report))


if __name__ == "__main__":
    main()
