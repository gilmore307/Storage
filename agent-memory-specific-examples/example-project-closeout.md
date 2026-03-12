# CLOSEOUT_CHECKLIST

_Last updated: 2026-03-12 14:42 CST_

## Goal
Move `network-framework` out of scaffold-building mode and into first live execution + closeout mode.

Quick execution entrypoint:
- `OPERATOR_SEQUENCE.md`

## What is effectively done
### Server/tooling development
These are now considered basically complete for first-pass use:
- Syncthing server preflight / bootstrap / validation helpers
- Syncthing first-pass runner
- Syncthing smoke validation / return-file validation / live record helper
- sing-box server preflight / runner / config validation helpers
- sing-box client validation / first-pass helper
- sing-box live record helper
- project handoff spine (`CURRENT_STATE.md`)

## What still must happen
### P0 — Syncthing first live execution
- [ ] run `sudo ./server/scripts/run-first-syncthing-live-pass.sh`
- [ ] pair node1 only
- [ ] add `shared-drop` only
- [ ] confirm server -> node1 smoke file arrival
- [ ] create `node1-return-smoke.txt` on node1
- [ ] run `sudo ./server/scripts/check-syncthing-return-file.sh /srv node1-return-smoke.txt`
- [ ] create live record via `./server/scripts/create-syncthing-live-record.sh`

### P1 — sing-box first lab execution
- [ ] run `sudo ./server/scripts/run-first-singbox-lab-pass.sh`
- [ ] validate client config with `./node/scripts/validate-singbox-client-first-pass.sh <client-config-path>`
- [ ] test one proxy target
- [ ] test one direct target
- [ ] create live record via `./server/scripts/create-singbox-live-record.sh`

## Allowed closeout work
Only do these before live execution if they directly reduce execution risk:
- tiny bug fixes discovered during dry checks
- doc wording fixes that unblock an operator step
- state/handoff cleanup

## Avoid during closeout
Do not reopen broad new development tracks such as:
- richer routing logic
- node2 rollout work
- `shared-projects` expansion
- production hardening beyond what the first live pass needs
- additional large refactors

## Definition of done for this phase
This phase is done when:
1. Syncthing first live pass has been executed and recorded
2. sing-box first lab pass has been executed and recorded
3. any execution-discovered fixes are small and documented
4. the next work moves from scaffolding to operational refinement
