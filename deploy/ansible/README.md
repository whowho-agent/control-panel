# Ansible deployment

Minimal Ansible entrypoint for the portable standalone topology.

## Layout
- `inventory.ini` — target hosts
- `group_vars/all.yml` — shared variables
- `site.yml` — orchestration entrypoint
- `playbooks/gateway.yml` — bootstrap frontend on gateway
- `playbooks/egress.yml` — bootstrap relay on egress
- `playbooks/control-plane.yml` — deploy containerized control-plane on gateway

## Canonical deploy flow
1. Fill `inventory.ini`
2. Fill `group_vars/all.yml`
3. Use one of these flows:

### Direct baseline
```bash
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/site.yml -e xray_transport_mode=direct
```

### IPSec staged rollout
```bash
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/prepare-ipsec-rollback.yml
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/ipsec.yml -e xray_transport_mode=ipsec -e ipsec_manage_service_cutover=false
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/validate-ipsec-app-cutover.yml
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/gateway.yml -e xray_transport_mode=ipsec
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/control-plane.yml -e xray_transport_mode=ipsec
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbooks/validate-ipsec-app-cutover.yml -e ipsec_expect_private_app_path=true
```

## Notes
- Playbooks still call the bootstrap scripts, but now both layers share the same behavior: host preflight, apt/dpkg lock waiting, relay readiness checks, and active relay-host selection.
- Shared Ansible task includes now own the repeated project-directory creation, bootstrap asset copy, relay wait, and service/port validation steps.
- Shared bootstrap helpers now own env loading, required-var validation, phase logging, apt-safe package install, and readiness waits.
- Fresh Ubuntu installs are hardened against `unattended-upgrades` lock races in both bootstrap and Ansible package-install paths (`lock_timeout: 600` plus explicit wait for apt/dpkg/unattended-upgrades to go idle).
- Gateway/control-plane orchestration waits for the effective relay endpoint before bootstrap so direct mode and staged private cutover use the same readiness gate.
- `deploy_project_root` is now the canonical base path for all Ansible deployment playbooks.
- `xray_transport_mode` controls which relay address frontend/control-plane use:
  - `direct` → `xray_relay_host`
  - `ipsec` → `xray_relay_private_host`
- `playbooks/ipsec.yml` applies role `ipsec_transport` when `xray_transport_mode=ipsec`.
- `playbooks/control-plane.yml` expects `xray_relay_ssh_private_key_local_path` on the Ansible controller and copies it to `xray_relay_ssh_key_source` on the gateway so control-plane can SSH into egress.
- In `ipsec` mode the control-plane env keeps both addresses wired: `XRAY_RELAY_HOST`/`XRAY_RELAY_PRIVATE_HOST` point at the active private relay path, while `XRAY_RELAY_PUBLIC_HOST` remains the management/SSH target for service status and synthetic egress probing.
- The IPSec role treats `swanctl + charon-systemd` as the primary v2 implementation path and keeps `starter` as explicit fallback.
- Keep `ipsec_manage_service_cutover=false` for first tests; only enable cutover after transport validation passes on recoverable hosts.
- Leave `ipsec_validate_external_reachability=true` so the role verifies from the Ansible controller that each host still answers on its public SSH port after apply; add `ipsec_external_reachability_ports` (for example `8000`) when other public control paths must remain reachable too.
- After transport-only rollout, use `playbooks/validate-ipsec-app-cutover.yml` as a no-change verifier for actual app-path state:
  - default (`ipsec_expect_private_app_path=false`) checks readiness / pre-cutover direct app path
  - `-e ipsec_expect_private_app_path=true` checks controlled private-path cutover state
- Treat the IPSec role as a controlled-test transport path, not as fully production-hardened final state.
