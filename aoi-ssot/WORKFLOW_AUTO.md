# WORKFLOW_AUTO.md (Bootstrap)

Status: ACTIVE
Last updated: 2026-02-20 (KST)

> NOTE: This file was missing after compaction; recreated as a minimal bootstrap.
> If a previous canonical WORKFLOW_AUTO.md exists elsewhere, replace this file with the canonical version.

## Operating SSOT
1) `CURRENT_STATE.md`
2) `context/SSOT_INDEX.md`
3) `MEMORY.md`
4) `memory/YYYY-MM-DD.md`

## Automation boundaries
- L1/L2: auto OK (docs, indexing, report-only, dry-run)
- L3: NEVER auto (money/wallet/on-chain signing/external posting/irreversible)

## Longform ingest
- Never reprint full raw PDFs/DOCX in chat.
- Provide: paths + summary + key quotes + drafts + approval gate.

## Skill scouting autopilot
- Policy: `context/SKILL_SCOUTING_AUTOPILOT_POLICY_V0_1.md`
- Decisions mirrored to Notion Decision Log.

## ACP micro-preapproval
- Policy: `aoi-core/state/acp_automation_policy_v0_1.json`
- Default: swap-only, USDC, providers privy/coinbase, caps ($2/tx, $7/day), Base-only.

---

## /reset Recovery Command (copy/paste) — AOI Core resume
When context is near limit and you recommend `/reset`, include the following command block for the user to paste after reset.

### Mandatory re-load order
1) `WORKFLOW_AUTO.md`
2) `memory/YYYY-MM-DD.md` (today)
3) `CURRENT_STATE.md`
4) `context/SSOT_INDEX.md`
5) `context/AOI_CORE_ALIGNMENT_MAP_V0_1.md`

### If working on Brand/Whitepaper/7-Pillars alignment (add)
6) `context/strategy_tft/aoi_core_brand_alignment/BRAND_SYSTEM_SSOT_V0_2_DRAFT.md`
7) `context/BRAND_AOI_CHUNGHO_SSOT_V0_1.md`
8) `context/strategy_tft/aoi_core_brand_alignment/SEVEN_PILLARS_AUDIT_V0_1_DRAFT.md`
9) `context/strategy_tft/aoi_core_brand_alignment/WHITEPAPER_PLATFORM_GAP_MATRIX_V0_1_DRAFT.md`
10) `context/NOTION_DECISION_LOG_TARGET_SSOT_V0_1.md`
11) `MEMORY.md` (rules/forbidden/exposure tiers)

### Post-reload output requirement (assistant)
After reading, the assistant must output:
- **Recovery checklist** (which files were read)
- **State in 10 lines** (current priorities + blockers)
- **Next 3 actions** (tight/executable)

### Optional integrity check (report-only)
- Run: `python3 skills/aoineco-state-guardian/scripts/state_integrity.py`
- If ALL GREEN: update “현재를 저장” snapshot with proof (paths + timestamps).

---

## Public/TEASER proof regeneration (one-click)
Use this when you need fresh, deterministic, public-safe evidence bundles (without mutating existing samples).

- Run: `bash scripts/run_public_teaser_proofs.sh`
- Output: a new folder under `/tmp/aoi_public_teaser_proofs_<timestamp>/`
- What it does:
  1) Runs deterministic proof tests (fail-closed)
  2) Rebuilds Bazaar registry + README + search index
  3) Rebuilds Audit Stall PASS/FAIL bundles
  4) Rebuilds S-DNA verify-only demo bundle

**Rule:** External copy must use claims listed in `context/PUBLIC_CLAIMS_REGISTRY_V0_1.md`.

