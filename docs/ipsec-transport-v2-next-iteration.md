# IPSec Transport v2 — Next Iteration Design

## Status

This document describes the next safe iteration after switching repo direction toward `swanctl + charon-systemd`.
It still does **not** declare the transport path production-ready.
The direct baseline remains the canonical known-good fallback.

## What changed in the repo direction

The repo now treats the following as the primary implementation path:
- `swanctl.conf`
- `strongswan.conf`
- `charon-systemd`
- explicit `swanctl --load-all` and child initiation during apply

The following remain intentionally available for rollback and comparison:
- `ipsec.conf`
- `ipsec.secrets`
- `strongswan-starter`

## Design goals

1. Keep the current `direct` transport baseline intact.
2. Make IPSec transport **management-safe by default**.
3. Separate:
   - underlay/public path
   - IPSec control plane (IKE/ESP/NAT-T)
   - management path (SSH/controller reachability)
   - protected application path (gateway -> relay private host)
4. Keep application cutover separate from tunnel bring-up.
5. Preserve explicit rollback to starter or fully back to direct mode.

## Route/policy model

### 1. Traffic classes

#### A. Underlay/public endpoint traffic
Traffic between public node IPs must never depend on the tunnel itself.
Examples:
- gateway public IP <-> egress public IP
- provider metadata / routing dependencies if required

This class must stay on the main routing table.

#### B. IPSec control traffic
Must bypass protected-host policy routing and use underlay directly:
- UDP/500 (IKE)
- UDP/4500 (NAT-T)
- ESP (IP proto 50) when applicable

This is not application traffic and must not be redirected into the XFRM route table.

#### C. Management traffic
Must remain recoverable independently of app cutover:
- SSH/22 to each public host
- controller -> gateway public IP
- controller -> egress public IP
- optionally additional operator-defined management CIDRs

This traffic stays on the underlay/main table.

#### D. Protected application traffic
This is the only traffic that should use the IPSec private path in v2:
- gateway -> `xray_relay_private_host:xray_relay_port`
- optional control-plane -> relay private endpoint if it shares the same path requirement

Only this class should be policy-routed into the dedicated IPSec route table.

### 2. Core routing contract

#### Main table
Must preserve:
- default route via public uplink
- route to peer public IP via public uplink
- SSH/controller reachability
- IKE/ESP/NAT-T underlay reachability

#### IPSec table
Dedicated route table should contain only the minimum protected-path routes:
- remote tunnel IP `/32` via XFRM interface
- protected private relay host `/32` via XFRM interface

Avoid broad routes like `0.0.0.0/0` or public-peer `/32` in the IPSec table.

### 3. Policy-rule contract

Recommended v2 rule shape:
- destination-based rule for `xray_relay_private_host/32` -> `ipsec_route_table`
- optionally destination-based rule for additional protected private endpoints
- **no** generic source-based full-tunnel rules in this iteration

This keeps blast radius small and rollback trivial.

### 4. Management-path bypass contract

Bypass is primarily a **routing-policy contract**, not only a firewall rule.

Meaning:
- no policy rule may capture controller/public SSH traffic
- no policy rule may capture peer public IP traffic
- no policy rule may capture UDP/500, UDP/4500, or ESP to the peer public IP

If firewall hardening is later added, it must preserve these bypass classes explicitly.

## Rollback implications

Rollback must restore three things, not just stop strongSwan:

1. **Routing state**
   - remove policy rules to `ipsec_route_table`
   - remove protected-host routes from `ipsec_route_table`
   - remove XFRM interface addresses and the interface itself

2. **Daemon state**
   - stop/disable `strongswan.service` / `charon-systemd`
   - stop/disable `strongswan-starter` and `strongswan-swanctl` if present from fallback or distro helpers
   - restore prior IPSec config files if backups exist

3. **Application path**
   - restore frontend/control-plane relay host to public/direct host if app cutover happened
   - restart impacted services only after transport rollback is complete

Important: transport rollback and app rollback are separate boundaries. If transport comes up but cutover never happened, app rollback must be a no-op.

## Validation priorities still required

Before declaring the swanctl direction accepted on live hosts, keep validating:
- route to peer public IP remains in main table
- no policy rule captures peer public IP
- no policy rule captures management CIDRs
- relay private host is the only protected app destination by default
- backend-specific service health (`charon-systemd` primary, `strongswan-starter` fallback)
- reboot convergence on both hosts
- rollback back to public SSH reachability

## Controlled live-test sequence

1. snapshot both nodes
2. confirm OOB access
3. keep `ipsec_manage_service_cutover=false`
4. arm `prepare-ipsec-rollback.yml`
5. run transport-only `ipsec.yml -e xray_transport_mode=ipsec`
6. verify SSH continuity and protected endpoint reachability
7. cancel rollback only after controller-side checks are green
8. test explicit fallback only if swanctl path shows a hard issue

## Acceptance for this iteration

This iteration is good enough for controlled transport-only tests only if:
- direct baseline remains unchanged and documented
- swanctl path establishes and validates on disposable/recoverable hosts
- rollback contract still covers routing, daemon, and application-path restoration
- starter fallback remains available for emergency regression handling
- service cutover stays disabled by default
