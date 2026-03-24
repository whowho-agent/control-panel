# ⚙️ Deploy Guide

## Topology

```
Client → xray-frontend.service (gateway:9444, VLESS+REALITY)
       → xray-relay.service    (egress:9443)
       → Internet (exit IP = egress public IP)
```

Transport modes:
- `direct` — gateway connects to egress over public internet
- `ipsec`  — gateway connects via strongSwan tunnel (10.10.10.1 ↔ 10.10.10.2)

---

## Prerequisites

### 1. SSH access to both nodes

You need an SSH key that can reach both `gateway` and `egress` with sudo.
The same key is used for the Ansible controller connection **and** is installed
on gateway as the relay key (for control-plane → egress tunnel).

```bash
# Example: generate a dedicated deploy key
ssh-keygen -t ed25519 -f /tmp/claude_agent_key -N ""
# Copy public key to both nodes (done once at node provisioning)
```

### 2. Ansible installed on the controller

Ansible is run **from the gateway node itself** (no local Python/WSL needed on Windows).

```bash
# On gateway:
sudo apt-get install -y ansible
```

### 3. Config files

Copy the example files and fill in real values:

```bash
cp deploy/ansible/inventory.ini.example deploy/ansible/inventory.ini
cp deploy/ansible/group_vars/all.yml.example deploy/ansible/group_vars/all/vars.yml
# vault.yml must be created manually (see Secrets section)
```

---

## Config Files

### `deploy/ansible/inventory.ini`

```ini
[gateway]
gateway-1 ansible_host=<GATEWAY_IP> ansible_user=claude-agent ansible_port=22 \
          ansible_ssh_private_key_file=/tmp/claude_agent_key \
          ansible_python_interpreter=/usr/bin/python3

[egress]
egress-1 ansible_host=<EGRESS_IP> ansible_user=claude-agent ansible_port=22 \
         ansible_ssh_private_key_file=/tmp/claude_agent_key \
         ansible_python_interpreter=/usr/bin/python3
```

### `deploy/ansible/group_vars/all/vars.yml`

Key vars to review:

| Var | Description |
|-----|-------------|
| `xray_transport_mode` | `direct` or `ipsec` |
| `xray_frontend_server_name` | SNI hostname for REALITY |
| `xray_frontend_target` | REALITY target (same host:443) |
| `xray_relay_host` | Egress public hostname/IP |
| `xray_relay_private_host` | Egress tunnel IP (ipsec only, `10.10.10.2`) |
| `xray_relay_ssh_user` | SSH user on egress for relay tunnel |
| `xray_relay_ssh_key_source` | Where relay key lands on gateway |
| `xray_relay_ssh_private_key_local_path` | Path to relay key on Ansible controller |
| `xray_expected_egress_ip` | Expected public exit IP (for health checks) |

### `deploy/ansible/group_vars/all/vault.yml` (gitignored, create manually)

```yaml
xray_frontend_short_ids: "6ba85179e30d4fc2,0123456789abcdef"
xray_frontend_reality_private_key: <key from xray x25519>
xray_relay_uuid: <uuid>
xray_relay_host: <egress public hostname or IP>
xray_expected_egress_ip: <egress public IP>
xray_ipsec_psk: <random PSK for strongSwan>
xray_admin_password: <admin panel password>
```

Generate values:
```bash
# REALITY key pair
docker run --rm teddysun/xray x25519
# UUID
cat /proc/sys/kernel/random/uuid
# short_ids (8-byte hex strings)
openssl rand -hex 8
# PSK
openssl rand -base64 32
```

---

## Full Deploy (fresh nodes)

Run from gateway node:

```bash
cd /opt/control-panel   # or wherever you cloned the repo
ssh-keyscan -H <GATEWAY_IP> <EGRESS_IP> >> ~/.ssh/known_hosts

ansible-playbook -i deploy/ansible/inventory.ini \
  deploy/ansible/playbooks/egress.yml \
  deploy/ansible/playbooks/ipsec.yml \
  deploy/ansible/playbooks/gateway.yml \
  deploy/ansible/playbooks/control-plane.yml
```

> **Important (ipsec mode):** `ipsec.yml` must run before `gateway.yml`.
> Gateway waits for the relay on `10.10.10.2:9443` (tunnel IP) — if IPSec tunnel is not up yet, it will timeout.
> If `xray_transport_mode: direct`, skip `ipsec.yml`.

Or use the IPSec rollout playbook (handles staging + rollback automatically):

```bash
ansible-playbook -i deploy/ansible/inventory.ini \
  deploy/ansible/playbooks/egress.yml \
  deploy/ansible/playbooks/ipsec-rollout.yml
```

> **Note:** On fresh Ubuntu nodes `unattended-upgrades` holds apt locks.
> All playbooks automatically stop and mask it before apt operations.
> If a previous run was aborted and left zombie processes, clean up first:
> ```bash
> sudo kill $(pgrep -f bootstrap-) 2>/dev/null; sudo rm -f /var/lib/dpkg/lock* /var/lib/apt/lists/lock /var/cache/apt/archives/lock
> ```

---

## IPSec Rollout (existing cluster, adding IPSec)

The staged rollout arms a timed rollback before touching network config.
If anything goes wrong (SSH drops, validation fails), the nodes revert automatically.

```bash
# Default rollback window: 5 min. Override with -e rollback_timeout_minutes=15
ansible-playbook -i deploy/ansible/inventory.ini \
  deploy/ansible/playbooks/ipsec-rollout.yml \
  -e rollback_timeout_minutes=10
```

Sequence:
1. `prepare-ipsec-rollback.yml` — arm rollback timers on both nodes
2. `ipsec.yml` — configure strongSwan + XFRM interface
3. `gateway.yml` — redeploy frontend pointing to tunnel IP
4. `control-plane.yml` — redeploy control-plane pointing to tunnel IP
5. `validate-ipsec-app-cutover.yml` — verify all app paths use tunnel
6. `cancel-ipsec-rollback.yml` — disarm rollback timers

To rollback manually at any point:
```bash
ansible-playbook -i deploy/ansible/inventory.ini \
  deploy/ansible/playbooks/recover-network.yml
```

---

## Individual Playbooks

| Playbook | Target | What it does |
|----------|--------|--------------|
| `egress.yml` | egress | Install xray-relay systemd service |
| `gateway.yml` | gateway | Install xray-frontend systemd service |
| `control-plane.yml` | gateway | Deploy FastAPI control-plane in Docker |
| `ipsec.yml` | both | Configure strongSwan IPSec tunnel |
| `ipsec-rollout.yml` | both | Full staged IPSec rollout (see above) |
| `prepare-ipsec-rollback.yml` | both | Arm timed rollback |
| `cancel-ipsec-rollback.yml` | both | Disarm rollback timers |
| `validate-ipsec-app-cutover.yml` | gateway | Verify app uses IPSec path |
| `recover-network.yml` | both | Emergency rollback |

---

## Redeploy (existing cluster)

Update a single component without touching the others:

```bash
# Update only control-plane app code + restart:
ansible-playbook -i deploy/ansible/inventory.ini \
  deploy/ansible/playbooks/control-plane.yml

# Update gateway xray config:
ansible-playbook -i deploy/ansible/playbooks/gateway.yml

# Update egress relay:
ansible-playbook -i deploy/ansible/inventory.ini \
  deploy/ansible/playbooks/egress.yml
```

---

## Admin Panel

Control plane runs at `http://<GATEWAY_IP>:8000`.

```bash
# Health check
curl http://<GATEWAY_IP>:8000/health

# List clients (requires auth)
curl -u admin:<password> http://<GATEWAY_IP>:8000/api/clients
```

Credentials are set via `xray_admin_user` / `xray_admin_password` in vault.yml.

---

## Troubleshooting

### SSH connection drops during bootstrap

Gateway drops long-running SSH sessions (Xray download is ~14 MB).
Use a `screen` session on gateway:

```bash
ssh claude-agent@<GATEWAY_IP> -i /tmp/claude_agent_key
screen -S deploy
ansible-playbook ...
# Ctrl-A D to detach, screen -r deploy to reattach
```

### apt lock timeout

```bash
# On the affected node:
sudo systemctl stop unattended-upgrades apt-daily apt-daily-upgrade
sudo kill $(pgrep -f bootstrap-) 2>/dev/null || true
sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
           /var/lib/apt/lists/lock /var/cache/apt/archives/lock
sudo dpkg --configure -a
```

### Clients disappear after redeploy

`bootstrap-gateway.sh` regenerates `config.json` from template. Clients are
preserved via `restore_clients.py` which reads `clients-meta.json` (written by
the control-plane on every client add/update). If `clients-meta.json` was lost,
clients must be re-added via the admin panel.

### xray-frontend won't start

```bash
ssh gateway
sudo journalctl -u xray-frontend -n 50
sudo cat /opt/xray-frontend/config.json | python3 -m json.tool >/dev/null
```

### IPSec tunnel not up

```bash
ssh gateway
sudo swanctl --list-sas
sudo swanctl --list-conns
sudo ip xfrm state
sudo ip xfrm policy
sudo ip link show xfrm-ipsec0
```

### CRLF errors in shell scripts

Windows git checkout may convert LF to CRLF. The `.gitattributes` file forces
LF for all scripts. If you see `set: pipefail\r: invalid option`, run:

```bash
# On the node where scripts are deployed:
find /opt/control-panel/deploy -name '*.sh' | xargs sed -i 's/\r//'
```

---

## For AI Agents

When taking over this project:

1. **Read `CLAUDE.md`** — role, server list, topology overview.
2. **Read `deploy/ansible/group_vars/all/vars.yml`** — all non-secret config.
3. **Secrets are in `group_vars/all/vault.yml`** (gitignored) — read directly from the file if needed.
4. **Inventory is in `deploy/ansible/inventory.ini`** (gitignored) — current node IPs and SSH params.
5. **Run ansible from gateway** — no local Python/WSL required. SSH into gateway and run from there.
6. **SSH key path on gateway controller**: `/tmp/claude_agent_key` (may need to be re-uploaded each session).
7. **Check for CRLF** before first run on fresh nodes: `find deploy -name '*.sh' | xargs file | grep CRLF`.
8. **Logs**: bootstrap stdout goes to the ansible run; for long deploys use `screen` on gateway and tee to `/tmp/ansible-deploy.log`.
