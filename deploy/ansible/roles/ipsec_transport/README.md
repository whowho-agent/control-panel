# ipsec_transport role

Baseline Ansible role for a protected gateway↔egress inter-node segment.

## Purpose
- enable `xray_transport_mode=ipsec`
- install strongSwan
- render `/etc/ipsec.conf` and `/etc/ipsec.secrets`
- start `strongswan-starter`

## Required variables
- `xray_ipsec_psk`
- `xray_ipsec_gateway_tunnel_ip`
- `xray_ipsec_egress_tunnel_ip`
- `xray_relay_private_host`

## Notes
- This role is a starting point, not a fully hardened production IPSec implementation.
- It currently models a PSK-based IKEv2 tunnel contract and should be extended with policy/firewall/routing validation before production rollout.
