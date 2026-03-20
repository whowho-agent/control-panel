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
- The current IPSec role provisions a baseline strongSwan PSK tunnel contract and config files. Treat it as the starting point for a hardened production IPSec role, not the final word.
