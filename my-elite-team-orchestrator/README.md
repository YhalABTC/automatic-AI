# AOI Squad Orchestrator Pro

Paid/private distribution.

License: **Proprietary Beta** (see `LICENSE_PROPRIETARY_BETA.md`).

## Scope (v0.1)
- 5-role presets (two defaults)
- Routing engine (sequence + parallel groups)
- Diff-first approvals for local file create/modify
- Audit logs + VCP artifacts

## Non-negotiables
- Product output must never expose AOI internal nicknames.
- Public-safe behavior by default; any side-effects require explicit approval.

## Docs
- PRD: (mirror from workspace) `context/PRD_AOI_SQUAD_ORCHESTRATOR_PRO_V0_1.md`
- Approval schema: `context/PRO_APPROVAL_REQUEST_SCHEMA_V0_1.md`

---

## AOI Guard Cheat Sheet (When commits are blocked)

This repo uses **AOI Guard** (default-deny). If a commit/push is blocked:

1) See what you staged:
```bash
git status
```

2) If you added a new file/folder intentionally, allow it (with Edmond approval):
```bash
# edit allowlist
nano .aoi-allowlist

# then
git add .aoi-allowlist
```

3) Re-stage only what you want, then commit:
```bash
git add <files>
git commit -m "..."
```

Rule of thumb: **new paths must be added to `.aoi-allowlist` first**, otherwise commits will be blocked.
