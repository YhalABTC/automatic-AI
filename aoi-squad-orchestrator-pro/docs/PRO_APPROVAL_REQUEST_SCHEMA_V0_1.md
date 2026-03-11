# Pro Approval Request Schema v0.1 (AOI Squad Orchestrator Pro)

Goal
- Safe, auditable file changes via **diff-first** workflow.

## Object (embedded in run output)
`approval_requests[]` items:

```json
{
  "id": "ar_1700000000000_01",
  "type": "file_patch",
  "reason": "Generate a launch checklist template file",
  "risk_flags": ["writes_file"],
  "files": [
    {
      "path": "docs/LAUNCH_CHECKLIST.md",
      "op": "create|modify",
      "encoding": "utf-8",
      "diff_unified": "--- /dev/null\n+++ b/docs/LAUNCH_CHECKLIST.md\n@@ ...",
      "sha256_before": null,
      "sha256_after": "<hex>",
      "line_count_after": 42
    }
  ],
  "constraints": {
    "allowed_roots": ["./"],
    "deny_globs": ["**/.env", "**/vault/**", "**/.git/**", "**/node_modules/**"],
    "max_files": 5,
    "max_total_bytes": 200000
  },
  "preview": {
    "summary": "Create docs/LAUNCH_CHECKLIST.md (42 lines)",
    "highlights": ["Adds a step-by-step checklist", "No secrets detected"]
  }
}
```

## Approval result (persisted)
`approvals[]` items:

```json
{
  "approval_request_id": "ar_...",
  "status": "approved|rejected|expired",
  "approved_by": "user",
  "approved_at": "ISO-8601",
  "note": "optional"
}
```

## CLI (suggested)
- `aoi-squad pro run ...` (emits approval_requests)
- `aoi-squad pro approve --run <run_id> --id <approval_request_id>`
- `aoi-squad pro reject --run <run_id> --id <approval_request_id> --note "..."`

## Hard guardrails
- Never allow absolute paths.
- Default deny: `.env`, `vault/`, `.git/`, `node_modules/`.
- Enforce size/file-count limits.
- Re-run banned-term scan on generated content.
