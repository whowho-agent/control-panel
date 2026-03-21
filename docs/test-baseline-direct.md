# Test Baseline — direct transport

This document captures the known-good baseline for the portable standalone topology before `ipsec_transport v2` work.

## Topology

```text
Client -> gateway frontend (95.81.123.248:9444) -> egress relay (147.45.152.57:9443) -> Internet
```

Inter-node transport mode:
- `xray_transport_mode=direct`

## Test nodes
- gateway: `deploy@95.81.123.248:22`
- egress: `deploy@147.45.152.57:22`

## Deployment method
- clean deploy via Ansible only
- inventory: `deploy/ansible/inventory.ini`
- vars: `deploy/ansible/group_vars/all.yml`
- entrypoint: `deploy/ansible/site.yml`

## Expected healthy state

### gateway
- `xray-frontend.service` is `active`
- control-plane health endpoint returns `{"status":"ok"}`

### egress
- `xray-relay.service` is `active`
- relay listens on `9443/tcp`

### topology-health
Expected shape:

```json
{
  "frontend_service": "active",
  "relay_service": "active",
  "relay_reachable": true,
  "expected_egress_ip": "147.45.152.57",
  "egress_probe_ok": true,
  "observed_egress_ip": "147.45.152.57"
}
```

## Important implementation details
- control-plane uses live host frontend runtime, not a container-only copy
- control-plane runs with `network_mode: host` to avoid Docker bridge/NAT drift during network recovery and to preserve direct host-equivalent reachability to egress
- frontend runtime files are mounted individually into the control-plane container
- relay SSH key is mounted into container as a regular file at `/relay_ssh_key`
- control-plane uses that key to query relay service state and synthetic egress probe

## Known non-baseline work
- `ipsec_transport` role exists only as a baseline scaffold and is not yet accepted as working production transport
- do not treat current IPSec implementation as release-ready

## Regression expectations
This baseline should survive:
- `deploy/ansible/playbooks/reset-test.yml`
- fresh `deploy/ansible/site.yml`
- control-plane re-deploy via `deploy/ansible/playbooks/control-plane.yml`
