# IPSec Transport v2 — Safe Rollout Design

## Goal

Introduce a protected gateway↔egress transport segment without risking loss of SSH management access or breaking the current direct-mode baseline.

## Non-goals
- No in-place experimentation on production paths
- No one-shot firewall lockdown in the same step as first tunnel bring-up
- No service-path cutover before transport validation passes

## Safety principles

1. **Snapshot before test**
   - Both test VMs must have a provider restore point/snapshot before IPSec rollout.

2. **Out-of-band access required**
   - Console/VNC/serial/rescue access must exist before testing.

3. **Timed rollback required**
   - Every IPSec apply arms an automatic rollback timer.
   - If rollout is not explicitly confirmed, the node restores network/SSH automatically.

4. **Two-phase rollout**
   - Phase A: prepare rollback + install config + start tunnel
   - Phase B: validate tunnel + then switch frontend relay host to private path

5. **No public relay shutdown on first pass**
   - Public relay hardening happens only after the private path is validated.

## Target topology

```text
Client -> gateway frontend -> relay over private IPSec path -> egress -> Internet
```

Example tunnel addressing:
- gateway tunnel IP: `10.10.10.1`
- egress tunnel IP: `10.10.10.2`
- relay private endpoint: `10.10.10.2:9443`

## Backend direction

Primary path:
- `swanctl + charon-systemd`
- route-based XFRM interface
- - dedicated route table with narrow `/32` protected destinations

Fallback path retained for rollback safety:
- `ipsec.conf + ipsec.secrets + strongswan-starter`

The direct baseline remains the canonical known-good fallback outside IPSec mode.

## Safe rollout stages

### Stage 0 — Preconditions
- direct-mode baseline green
- snapshots created
- provider console confirmed
- `recover-network.yml` ready

### Stage 1 — Prepare rollback
- backup `/etc/ipsec.conf`
- backup `/etc/ipsec.secrets`
- backup `/etc/strongswan.conf`
- backup `/etc/swanctl/swanctl.conf`
- install rollback script
- arm timed rollback via `systemd-run --on-active=<timeout>`
- ensure rollback also stops `ipsec-xfrm.service`, `charon-systemd`, and any fallback starter units, then removes the XFRM device/routes/rules

### Stage 2 — Apply transport
- install strongSwan swanctl/charon packages
- render `swanctl.conf` + `strongswan.conf`
- start/enable `charon-systemd`
- `swanctl --load-all`
- create XFRM tunnel interface
- assign point-to-point tunnel IPs
- install dedicated route table + protected-host policy rule

### Stage 3 — Validate transport
Must pass before any service cutover:
- `strongswan.service` active (charon-systemd-based on the current test distro)
- `ipsec-xfrm.service` active
- tunnel IP present locally
- route to remote tunnel IP present
- route/rule to host-specific protected endpoint present
- `swanctl --list-sas` reports an established or installed SA
- protected endpoint reachable (`gateway -> relay:9443`, `egress -> gateway:ssh`)
- SSH still reachable from controller

### Stage 4 — Service cutover
- keep `ipsec_manage_service_cutover=false` on the first transport-only run
- once transport validation is green, set frontend/control-plane relay host to `xray_relay_private_host`
- if desired, enable `ipsec_manage_service_cutover=true` so gateway-side services restart after transport is up
- validate application path

### Stage 5 — Confirm success
- cancel rollback timer
- optionally tighten firewall/public relay exposure

## Recovery contract

Rollback script must:
- stop/disable `ipsec-xfrm.service`
- remove XFRM interface + routes + rules
- stop/disable `strongswan.service` / `charon-systemd`
- stop/disable `strongswan-starter` when fallback path had been used
- restore backed-up IPSec config files if present
- flush firewall rules (`nft` / `iptables`)
- restart SSH
- leave host reachable via public SSH

## Acceptance criteria

IPSec v2 is accepted only if all pass:
- SSH remains reachable during rollout
- tunnel interface/IPs are present
- gateway reaches relay on `xray_relay_private_host:xray_relay_port`
- live frontend config points to private relay host when cutover is enabled
- control-plane topology is green
- synthetic egress probe passes
- rollback timer can be armed and cancelled cleanly

## Controlled test procedure

1. Keep `xray_transport_mode=direct` baseline validated.
2. Set inventory/group vars for IPSec, but keep `ipsec_manage_service_cutover=false`.
3. Run:
   ```bash
   ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/prepare-ipsec-rollback.yml
   ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/ipsec.yml -e xray_transport_mode=ipsec
   ```
4. Verify controller-side SSH remains stable and validation tasks pass.
5. Run the no-change app-path verifier after transport-only validation succeeds:
   ```bash
   ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/validate-ipsec-app-cutover.yml
   ```
6. If doing a controlled private cutover, switch the app path intentionally and then verify it explicitly:
   ```bash
   ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/validate-ipsec-app-cutover.yml -e ipsec_expect_private_app_path=true
   ```
7. Cancel rollback only after transport and app-path checks are green.
8. Use `-e ipsec_backend=starter` only as an explicit fallback/rollback experiment, not as the primary direction.

## Current code status
- recovery/rollback playbooks: present, clean up XFRM state, and stop both swanctl-era and starter-era units
- `ipsec_transport` role: staged route-based implementation with host-specific protected route handling
- swanctl/charon-systemd is now the primary backend in repo defaults
- starter backend remains available as fallback baseline
- XFRM helper script + systemd unit scaffold: present
- dedicated route table + destination-based rule scaffold: present
- service cutover hooks: present but opt-in and disabled by default
- firewall enforcement: pending
- acceptance on live hosts: pending controlled test
