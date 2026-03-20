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

## Safe rollout stages

### Stage 0 — Preconditions
- direct-mode baseline green
- snapshots created
- provider console confirmed
- `recover-network.yml` ready

### Stage 1 — Prepare rollback
- backup `/etc/ipsec.conf`
- backup `/etc/ipsec.secrets`
- install rollback script
- arm timed rollback via `systemd-run --on-active=<timeout>`

### Stage 2 — Apply transport
- install strongSwan
- render IPSec config
- start/enable strongSwan
- create tunnel interface / route-based plumbing
- assign tunnel IPs

### Stage 3 — Validate transport
Must pass before any service cutover:
- `strongswan-starter` active
- tunnel IP present locally
- route to remote tunnel IP present
- private relay endpoint reachable from gateway
- SSH still reachable from controller

### Stage 4 — Service cutover
- set frontend/control-plane relay host to `xray_relay_private_host`
- re-render config
- restart services
- validate application path

### Stage 5 — Confirm success
- cancel rollback timer
- optionally tighten firewall/public relay exposure

## Recovery contract

Rollback script must:
- stop/disable `strongswan-starter`
- restore backed-up IPSec config files if present
- flush firewall rules (`nft` / `iptables`)
- restart SSH
- leave host reachable via public SSH

## Acceptance criteria

IPSec v2 is accepted only if all pass:
- SSH remains reachable during rollout
- tunnel interface/IPs are present
- gateway reaches relay on `xray_relay_private_host:xray_relay_port`
- live frontend config points to private relay host
- control-plane topology is green
- synthetic egress probe passes
- rollback timer can be armed and cancelled cleanly

## Implementation plan

1. add recovery playbooks/scripts
2. add rollback timer management
3. redesign `ipsec_transport` role for route-based transport
4. implement XFRM/VTI interface creation and route installation
5. validate transport before service cutover
6. add firewall hardening as a later step

## Current code status
- recovery/rollback playbooks: present
- `ipsec_transport` role: refactored into staged v2 scaffold (`precheck`, `prepare`, `apply`, `validate`)
- route-based interface/routing implementation: pending
- firewall enforcement: pending
- safe service-path cutover to private relay host: pending
