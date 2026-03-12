# Memory Index

_Last updated: 2026-03-12 15:42 CST_

This file explains how the current memory files are organized and which files should be treated as primary vs secondary references.

## Preferred memory hierarchy

### 1. Daily primary logs
These are the main chronological memory files and should remain the default first stop for recent history:
- `2026-03-08.md`
- `2026-03-09.md`
- `2026-03-10.md`
- `2026-03-11.md`
- `2026-03-12.md`

Use these for:
- durable day-by-day decisions
- user preference updates
- project direction changes
- milestone summaries

### 2. Session / current-state capture files
These are useful but secondary; they are session-specific recovery aids, not the primary long-term timeline:
- `2026-03-12-current-state.md`

Use these for:
- dense session-state capture
- handoff context that would be too bulky for the daily log
- temporary resume support

Preferred rule going forward:
- keep these when they materially reduce resume cost
- avoid multiplying them unless there is a clear handoff need

### 3. Topic-specific work logs
These are narrow memory files tied to a specific debugging or implementation thread:
- `2026-03-09-state-reconcile.md`
- `2026-03-09-tray-menu.md`
- `2026-03-10-entry-fix.md`
- `2026-03-10-okx-verification-state-machine.md`
- `2026-03-10-reset-smoke.md`
- `2026-03-10-test-cooldown.md`
- `2026-03-10-trade-calibrate.md`
- `2026-03-11-mode-layer.md`
- `2026-03-11-review-aggregator.md`
- `2026-03-12-codex-switch.md`

Use these for:
- focused investigation history
- specialized implementation threads worth preserving separately
- situations where a daily log would become too noisy

Preferred rule going forward:
- create them only when a topic is substantial enough to deserve its own thread
- once a topic stabilizes, distill the durable outcome back into the relevant daily log and/or durable project docs
- avoid treating these as the first place to look unless the topic clearly matches

## Current reading order
When recalling recent history, prefer:
1. the relevant daily file(s)
2. `INDEX.md`
3. topic-specific files only if the topic clearly matches
4. current-state/session files only when handoff density matters

## Cleanup guidance
### Keep
Keep all current files for now because they still provide useful traceability.

### Avoid going forward
- too many one-off session-state files
- storing environment-specific operational facts in daily memory if they belong in `TOOLS.md`
- storing durable user preferences in topic files when they belong in `USER.md`

### Distillation rule
When a topic-specific memory file contains durable conclusions:
- copy the durable conclusion into the relevant daily file
- copy long-lived environment facts into `TOOLS.md`
- copy long-lived user preferences into `USER.md`
- leave the topic file as supporting detail, not the main source of truth

## Current assessment
The memory directory is usable, but it had begun to drift into three mixed layers:
- daily timeline
- topic logs
- session-state dumps

That is now explicitly normalized by this index.
