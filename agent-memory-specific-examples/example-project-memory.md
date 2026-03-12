# CURRENT_STATE

_Last updated: 2026-03-12 14:31 CST_

## One-line status
`network-framework` has moved beyond baseline docs into an executable first-pass rollout toolkit for both Syncthing and sing-box, but the first real live execution on the VPS/node path is still pending.

## Read this first in a new session
1. `CURRENT_STATE.md`
2. `README.md`
3. `docs/work-status.md`
4. `docs/first-live-execution-plan.md`
5. `docs/first-live-checklist.md`

Then branch by track:
- Syncthing: `syncthing/live-execution-notes-server-node1.md`
- sing-box: `singbox/live-execution-notes.md`

## Current reality
### Syncthing
The first-pass server-side execution chain now exists as runnable helpers:
- `server/scripts/preflight-first-live-pass.sh`
- `server/scripts/run-first-syncthing-live-pass.sh`
- `server/scripts/validate-syncthing-shared-drop.sh`
- `server/scripts/check-syncthing-return-file.sh`
- `server/scripts/create-syncthing-live-record.sh`

This means the intended first live path is now:
1. preflight
2. backup
3. bootstrap/checks
4. write server-side smoke file into `shared-drop`
5. verify node1 sees it
6. create node1 return file
7. verify node1 -> server return path
8. record the execution result

### sing-box
The first-pass server/client validation chain now exists as runnable helpers:
- `server/scripts/preflight-singbox-first-pass.sh`
- `server/scripts/run-first-singbox-lab-pass.sh`
- `server/scripts/validate-singbox-config.py`
- `server/scripts/validate-singbox-client-config.sh`
- `node/scripts/validate-singbox-client-first-pass.sh`

This means the intended first lab path is now:
1. scaffold/install server side
2. validate real server config before service bring-up
3. enable/start service
4. validate listener/service state
5. validate client config
6. run one proxy-target test and one direct-target test only

## What was completed in the recent push streak
Recent commits:
- `4bd523d` feat: add sing-box client first-pass helper
- `a130cfc` feat: add syncthing return-file checker
- `aad9aa9` feat: add syncthing live validation helpers
- `70ca282` feat: add sing-box config validators
- `09310d3` feat: add sing-box first-pass helpers
- `75b63a4` feat: add syncthing first-pass runner
- `39bc3b6` feat: add first-live preflight helper

Functional outcome:
- Syncthing now has runnable preflight, runner, smoke validation, return-path validation, and execution-record helpers.
- sing-box now has runnable preflight, runner, server/client config validation, and client first-pass validation helpers.
- First live deployment docs are now much closer to actual operator runbooks than abstract planning notes.

## Highest-value next steps
Closeout is now the active mode: stop expanding broad scaffolding and focus on the smallest path to first live execution plus result recording.

### P0 — execute the first real Syncthing pass
Run on the VPS:
```bash
sudo ./server/scripts/run-first-syncthing-live-pass.sh
```
Then do:
- pair node1 only
- add `shared-drop` only
- confirm server -> node1 smoke file arrival
- create `node1-return-smoke.txt` on node1
- run:
```bash
sudo ./server/scripts/check-syncthing-return-file.sh /srv node1-return-smoke.txt
./server/scripts/create-syncthing-live-record.sh
```

### P1 — execute the first real sing-box lab pass
Run on the VPS:
```bash
sudo ./server/scripts/run-first-singbox-lab-pass.sh
```
Then on the client side:
```bash
./node/scripts/validate-singbox-client-first-pass.sh <client-config-path>
```
Then test:
- one proxy target
- one direct target

### P2 — record real execution results cleanly
After either live pass, update the corresponding notes/template instead of leaving outcomes only in chat.

## Boundaries / stop lines
- Do **not** add `shared-projects`, node2, or full mesh before `shared-drop` is calm.
- Do **not** widen sing-box route complexity before the first server+client baseline works.
- Keep changes reversible and avoid bundling Syncthing widening with sing-box routing experimentation in the same execution window.

## Current blocker profile
No architecture blocker is known.
The real remaining blocker is that the project now needs actual live execution on the VPS/node path, not more baseline scaffolding.

## Repo status snapshot
- Branch: `main`
- Local state: ahead of `origin/main` with the recent helper commits
- Practical meaning: there is a good chunk of unpushed implementation progress worth preserving/pushing when appropriate
