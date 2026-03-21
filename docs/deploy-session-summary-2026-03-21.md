# Deploy Session Summary — 2026-03-21

## Goal
Stabilize and finish the standalone gateway/egress + control-plane deployment flow, with staged IPSec rollout and transport-aware control-plane behavior, and make clean-host installs reproducible.

## Final validated state
A full staged rollout completed successfully on test hosts after the refactor/fixes:
1. direct baseline
2. rollback arm
3. transport-only IPSec
4. transport validation
5. baseline app validation
6. gateway cutover to ipsec/private relay
7. control-plane cutover to ipsec/private relay
8. final private app-path validation
9. rollback cancel

This validated:
- direct baseline works
- staged IPSec cutover works
- private relay path works
- control-plane correctly tracks transport mode
- rollback flow works

## Canonical rollout flow
For fresh/test hosts, prefer staged rollout over one-shot full ipsec deployment.

### Direct baseline
```bash
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/reset-test.yml
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/site.yml -e xray_transport_mode=direct
```

### Staged IPSec cutover
```bash
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/prepare-ipsec-rollback.yml -e ipsec_rollback_timeout_minutes=8
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/ipsec.yml -e xray_transport_mode=ipsec -e ipsec_manage_service_cutover=false
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/validate-ipsec-app-cutover.yml
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/gateway.yml -e xray_transport_mode=ipsec
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/control-plane.yml -e xray_transport_mode=ipsec
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/validate-ipsec-app-cutover.yml -e ipsec_expect_private_app_path=true
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/cancel-ipsec-rollback.yml
```

## Why staged rollout is preferred
One-shot clean deploy straight into app-private IPSec mode was flaky because it mixed:
- host bootstrap problems
- package-manager lock problems on fresh Ubuntu
- relay readiness races
- transport validation
- app cutover validation

The staged flow separates transport success from application cutover success.

## Key issues discovered and resolved

### 1. Client creation / frontend apply runtime files
Frontend apply could fail when `/opt/xray-frontend/access.log` did not exist.
Fix: repo hardening to ensure runtime files/directories exist before validate/restart/apply.

### 2. Control-plane transport awareness
Added transport-aware topology/API/UI so direct vs ipsec/private path is visible and honest.
Added degraded IPSec label when private relay is unreachable.

### 3. Reachability hardening
IPSec role now validates external reachability after transport apply (SSH by default; extra ports configurable).

### 4. Clean-host deploy problems
Fresh Ubuntu hosts exposed several problems:
- `unattended-upgrades` / `apt-daily*` causing dpkg/apt locks
- relay readiness race before private endpoint was actually listening
- hardcoded `deploy` ownership assumptions instead of configurable SSH user
- shell portability bugs from Ansible `shell:` tasks using `set -euo pipefail` under `/bin/sh`
- fragile `declare -f ... | sudo bash -c` helper invocation

These were fixed incrementally and then unified in the deploy refactor.

### 5. Deploy/orchestration refactor
Refactored deploy flow to centralize:
- env loading
- required env checks
- apt lock-safe package installation
- relay readiness waits
- common bootstrap directory and asset copy tasks
- common service validation

## Operational behavior verified

### IPSec failure drill
When `strongswan` was stopped on both sides:
- control-plane / panel stayed reachable
- client traffic through private path died
- topology-health showed degraded state
- recovery worked after starting strongSwan and restarting ipsec-xfrm

### Direct fallback
Switching gateway/control-plane back to `direct` mode succeeded without extra special fixes for direct-mode logic.

## Fresh-host caveat
On test/fresh Ubuntu VMs, `unattended-upgrades.service` may hang for a very long time (`unattended-upgrade-shutdown --wait-for-signal`).
For test hosts, it may be practical to explicitly stop/mask:
- unattended-upgrades.service
- apt-daily.service
- apt-daily-upgrade.service
- apt-daily.timer
- apt-daily-upgrade.timer

This is operationally useful for test reproducibility, though it is separate from the product logic itself.

## Important commits from this session

### Functional / feature work
- `f7b9f94` — Harden IPSec rollout reachability validation
- `b2067cf` — Make control-plane transport-mode aware
- `b60ee23` — Wire transport-aware control-plane relay management
- `03468c3` — Show degraded IPSec state in control-plane

### Clean-host / deploy hardening
- `893238a` — Switch test inventory to rabotyaga hosts
- `bd94341` — Relax firewall tooling validation on clean hosts
- `5e54977` — Relax IPSec tunnel-peer policy rule expectation
- `141a594` — Use configured relay SSH user in control-plane deploy
- `c73a6e0` — Harden fresh Ubuntu IPSec rollout readiness
- `4266893` — Refactor deploy preflight and phased orchestration flow
- `cb83e35` — Fix sudo bootstrap helper invocation quoting
- `d0359c1` — Harden bootstrap helper timeout fallbacks
- `dc1e5db` — Run control-plane preflight lock wait under bash
- `1f050ad` — Run IPSec package-lock preflight under bash

## Recommended next step
If weekly token budget is constrained, the safest restart point later is:
1. create fresh hosts
2. create `rabotyaga` with sudo/NOPASSWD
3. verify inventory points to those IPs/users
4. run the canonical staged flow above
5. if fresh Ubuntu auto-upgrades block package steps, stop/mask those services first on test hosts

## Current repo note
Functional deployment changes are committed, but the workspace may still contain unrelated local/untracked files (memory, pycache, local notes, secrets, etc.). Use `git status` before any final cleanup commit.
