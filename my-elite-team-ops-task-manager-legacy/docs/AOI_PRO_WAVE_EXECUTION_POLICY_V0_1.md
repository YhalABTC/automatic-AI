# AOI PRO Wave Execution Policy v0.1

## Goal
Execute many ops/items safely without backlog explosion, keeping **max 5 active** tasks at once.

## Core rules
1) **Max active = 5** (Oracle Scheduler enforces)
2) Work flows as: **TODO → in_progress → review → done**
3) Every task must have:
   - Intent
   - Done Criteria
   - Proof target (artifact path)
   - Next action (single smallest step)
4) L3 tasks (money/on-chain/external posting) are **blocked** until explicit human approval.

## Wave model
- A *wave* is a set of tasks that can run in parallel (no file conflicts, independent outputs).
- Waves execute sequentially.

### Recommended wave heuristics
- Same project + same files touched → avoid parallel (put in same wave sequentially)
- Different projects / different directories → parallel OK

## Suggested default lanes (roles)
- Oracle: routing, prioritization, approvals
- Builder: code changes, UI updates
- Ops: cron/state/paths
- Security: redaction, fail-closed checks
- Memory: SSOT updates, reports

## Evidence discipline
- Every wave emits a brief receipt:
  - tasks executed
  - artifacts created
  - failures + log pointers

## Integration points
- Works with `scripts/ops_task_manager.py` (hygiene) + ADP `/ralph` board.
