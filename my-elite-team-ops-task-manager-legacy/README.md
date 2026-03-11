# AOI PRO — Ops Task Manager

License: **Proprietary Beta**

AOI PRO component that keeps `ops/items` healthy:
- duplicate canonicalization (Oracle task families)
- labeling hygiene (`ralph-loop`)
- lightweight routing defaults (project → assignee)
- proof-first reports under `ops/reports/task_manager/`

## Quickstart (local)

```bash
python3 skills/aoi-pro-ops-task-manager/scripts/ops_task_manager.py --dry-run
python3 skills/aoi-pro-ops-task-manager/scripts/ops_task_manager.py --apply
```

## Recommended scheduling
Use OpenClaw cron (example):
- 08:05 / 20:05 KST (silent)

> Note: This skill is intended to be managed by **🧿 Oracle** (scheduling/slotting) while Aoineco maintains hygiene rules.
