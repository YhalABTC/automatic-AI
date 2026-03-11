# PRD — AOI Squad Orchestrator Pro v0.1

## Goal
Turn the Lite (3-role) experience into a **paid, operationally reliable** 5-role team with routing, approvals, and audit/VCP.

## Non-negotiables
- **No AOI internal nicknames** in product output (use pseudonyms + user-renamable).
- Pro v0.1 scope is **A-range**: analysis/summary/code/doc/report only.
- Any local side-effects require **explicit approval** (v0.1: file create/modify only).

## Pricing model (agreed direction)
- Seat-based subscription: agent slots
  - Pro: 5 roles (v0.1)
  - Max: 9+ roles

## Key decisions (agreed)
1) Pro v0.1 default roles count: **5**
2) Approval scope: **(a) file create/modify only** (no git commit in v0.1)
3) Name: **AOI Squad Orchestrator Pro** (alias: **AOI Squad Pro**)
4) Pro v0.1 presets: **two** 5-role presets (A + B)

## Presets (5 roles)
### Pro Preset A (default, general-purpose)
- Planner
- Researcher
- Builder
- Reviewer
- Operator

### Pro Preset B (content + security + ops)
- Researcher
- Writer
- Builder
- Security
- Operator

## User flows
### Quick run
- run → role executions (sequence/parallel) → synthesize → report + VCP

### Customization (Pro differentiator)
- clone preset → edit roles/order/weights → save
- team rename per preset (stable pseudonyms)

### Approval
- run emits `approval_requests[]` when a side-effect is proposed (file create/modify)
- user approves → execute only approved actions

## Output contract
- Keep Lite JSON schema `aoi.squad.report.v0.1`.
- Pro fills richer fields:
  - routing plan
  - approval requests + results
  - audit log + VCP artifacts

## Data (local)
- Names: `~/.openclaw/aoi/squad_names.json` (stable per preset)
- Pro presets: `~/.openclaw/aoi/presets.json`
- Runs/audit: `~/.openclaw/aoi/runs/<run_id>.json`
- Policy: `~/.openclaw/aoi/policy.json`

## Milestones
- M1: preset clone/edit/save + stable names + report schema compliance
- M2: routing engine + 5-role execution graph
- M3: approvals (file create/modify) + audit/VCP artifacts
- M4: packaging/licensing for paid distribution
