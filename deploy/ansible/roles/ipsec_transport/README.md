# ipsec_transport role

Route-based IPSec v2 implementation for a protected gateway↔egress segment.

## Purpose
- enable `xray_transport_mode=ipsec`
- make `swanctl + charon-systemd` the primary v2 backend
- keep `ipsec.conf`/starter available as an explicit fallback path
- create a route-based XFRM interface + dedicated route table
- keep the implementation staged as `precheck -> prepare -> apply -> validate`

## Current status
- validates single-gateway + single-egress inventory shape
- keeps datapath semantics explicit: `ipsec_validation_host` is separate from `ipsec_policy_route_destinations`
- installs narrow destination-based routing rules (`gateway -> relay private host`, `egress -> gateway tunnel IP`) instead of conflating probes with policy intent
- installs an XFRM helper script, cleanup helper, and systemd unit
- uses `swanctl.conf` + `strongswan.conf` with ``strongswan.service` (charon-systemd-based on these hosts) as the default route-based control path
- explicitly loads and initiates the swanctl child during apply
- keeps route-based `ipsec.conf` + `ipsec.secrets` as fallback starter backend artifacts
- validates service state, interface state, route/rule state, CHILD_SA establishment, and protected endpoint reachability
- optional service cutover hooks exist but default to **disabled**
- firewall enforcement and explicit management-path bypass enforcement are still intentionally deferred

## Required variables
- `xray_ipsec_psk`
- `xray_ipsec_gateway_tunnel_ip`
- `xray_ipsec_egress_tunnel_ip`
- `xray_relay_private_host`

## Useful optional variables
- `ipsec_backend` (defaults to `swanctl`; fallback `starter` remains supported)
- `ipsec_interface_id` (defaults to `ipsec_mark`)
- `ipsec_manage_service_cutover` (default `false`)
- `ipsec_frontend_service_name`
- `ipsec_control_plane_service_name`

## Safety contract
Use together with:
- `playbooks/prepare-ipsec-rollback.yml`
- `playbooks/cancel-ipsec-rollback.yml`
- `playbooks/recover-network.yml`

Recommended rollout order:
1. confirm direct baseline is green
2. create VM snapshots and verify OOB console access
3. run `prepare-ipsec-rollback.yml`
4. run `ipsec.yml`
5. validate tunnel health from the controller
6. only then opt into service cutover if desired

Rollback safety is preserved by keeping:
- direct-mode baseline unchanged
- timed rollback playbooks capable of stopping both starter and swanctl-era units
- starter templates available for explicit fallback
- service cutover disabled by default

Treat this role as controlled-test-ready transport automation, not as final production hardening.
