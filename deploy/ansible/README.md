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
