# Ansible deployment

Minimal Ansible entrypoint for the portable standalone topology.

## Layout
- `inventory.ini` — target hosts
- `group_vars/all.yml` — shared variables
- `site.yml` — orchestration entrypoint
- `playbooks/gateway.yml` — bootstrap frontend on gateway
- `playbooks/egress.yml` — bootstrap relay on egress
- `playbooks/control-plane.yml` — deploy containerized control-plane on gateway

## Expected flow
1. Fill `inventory.ini`
2. Fill `group_vars/all.yml`
3. Run:

```bash
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/site.yml
```

## Notes
- Current playbooks are thin wrappers around existing bootstrap scripts.
- This keeps one source of truth for provisioning logic while giving repeatable orchestration.
- Next step would be replacing shell wrappers with native Ansible tasks/templates.
- `xray_transport_mode` controls which relay address frontend/control-plane use:
  - `direct` → `xray_relay_host`
  - `ipsec` → `xray_relay_private_host`
- `playbooks/ipsec.yml` applies role `ipsec_transport` when `xray_transport_mode=ipsec`.
- `playbooks/control-plane.yml` expects `xray_relay_ssh_private_key_local_path` on the Ansible controller and copies it to `xray_relay_ssh_key_source` on the gateway so control-plane can SSH into egress.
- The IPSec role now treats `swanctl + charon-systemd` as the primary v2 implementation path and keeps `starter` as explicit fallback.
- Keep `ipsec_manage_service_cutover=false` for first tests; only enable cutover after transport validation passes on recoverable hosts.
- Leave `ipsec_validate_external_reachability=true` so the role verifies from the Ansible controller that each host still answers on its public SSH port after apply; add `ipsec_external_reachability_ports` (for example `8000`) when other public control paths must remain reachable too.
- After transport-only rollout, use `playbooks/validate-ipsec-app-cutover.yml` as a no-change verifier for actual app-path state:
  - default (`ipsec_expect_private_app_path=false`) checks readiness / pre-cutover direct app path
  - `-e ipsec_expect_private_app_path=true` checks controlled private-path cutover state
- Current recommended posture is: narrow protected-host routing only, explicit rollback preparation, route-based `if_id` selectors, and backend rollback safety preserved for both swanctl and starter.
- Treat the role as a controlled-test transport path, not as fully production-hardened final state.
