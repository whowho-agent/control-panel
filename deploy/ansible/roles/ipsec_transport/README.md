# ipsec_transport role

Route-based IPSec v2 scaffold for a protected gateway↔egress segment.

## Purpose
- enable `xray_transport_mode=ipsec`
- install strongSwan baseline packages
- render `/etc/ipsec.conf` and `/etc/ipsec.secrets`
- keep the implementation staged as `precheck -> prepare -> apply -> validate`

## Current status
- this role is now structured for IPSec v2 work
- it now installs an XFRM helper script and systemd unit to create a route-based tunnel interface scaffold
- it now also lays down a dedicated route table and destination-based rule for the private relay endpoint
- it is **not yet a fully working route-based tunnel implementation**
- firewall enforcement and end-to-end acceptance testing still need to be completed

## Required variables
- `xray_ipsec_psk`
- `xray_ipsec_gateway_tunnel_ip`
- `xray_ipsec_egress_tunnel_ip`
- `xray_relay_private_host`

## Safety contract
Use together with:
- `playbooks/prepare-ipsec-rollback.yml`
- `playbooks/cancel-ipsec-rollback.yml`
- `playbooks/recover-network.yml`

Do not treat this role as production-ready until route-based plumbing and recovery-tested validation are complete.
