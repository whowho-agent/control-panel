# Portable v1 Deployment Blueprint

## Goal

Make the current Xray control-plane system portable so it can be deployed on any compatible pair of Linux hosts with minimal host-specific handwork.

Canonical topology:

```text
Client -> standalone Xray frontend on gateway node -> Xray relay on egress node -> Internet
```

## Scope of portable v1

Portable v1 covers a **single installation** consisting of:
- 1 gateway node
- 1 egress node
- 1 control-plane deployment

It does **not** target multi-tenant or multi-installation orchestration yet.

## Required deployment contract

### 1. Nodes
- `gateway` node
  - runs standalone `xray-frontend`
  - runs control-plane (containerized or host mode)
- `egress` node
  - runs standalone `xray-relay`
  - provides final internet egress

### 2. Runtime assumptions
- Linux host
- systemd available for Xray services
- outbound internet access
- SSH connectivity from control-plane host to egress node for health/status checks
- optional private/IPSec transport between gateway and egress

## What must be parameterized

### Gateway parameters
- gateway public IP / DNS
- frontend port
- frontend reality server name
- frontend target
- frontend fingerprint
- frontend short IDs
- frontend reality private key
- relay host
- relay port
- relay UUID

### Egress parameters
- egress public IP / DNS
- relay listen port
- relay UUID
- egress interface (if needed later)

### Control-plane parameters
- admin user
- admin password
- runtime paths
- relay SSH user
- relay SSH key path
- cache TTL
- expected egress IP

### Branding/UI parameters
- app title
- node labels
- optional logo/favicon later

## File layout target

```text
deploy/
  env/
    gateway.env.example
    egress.env.example
    control-plane.env.example
  templates/
    xray-frontend.config.json.j2
    xray-relay.config.json.j2
    control-plane.env.j2
  bootstrap/
    bootstrap-gateway.sh
    bootstrap-egress.sh
    bootstrap-control-plane.sh
  validate/
    validate-gateway.sh
    validate-egress.sh
    validate-end-to-end.sh
```

## Environment contract

### gateway.env
Should define:
- `XRAY_FRONTEND_PORT`
- `XRAY_FRONTEND_SERVER_NAME`
- `XRAY_FRONTEND_TARGET`
- `XRAY_FRONTEND_FINGERPRINT`
- `XRAY_FRONTEND_SHORT_IDS`
- `XRAY_FRONTEND_REALITY_PRIVATE_KEY`
- `XRAY_RELAY_HOST`
- `XRAY_RELAY_PORT`
- `XRAY_RELAY_UUID`

### egress.env
Should define:
- `XRAY_RELAY_PORT`
- `XRAY_RELAY_UUID`
- `XRAY_EXPECTED_EGRESS_IP`

### control-plane.env
Should define:
- `XRAY_FRONTEND_CONFIG_PATH`
- `XRAY_FRONTEND_ACCESS_LOG_PATH`
- `XRAY_FRONTEND_SERVICE_NAME`
- `XRAY_BINARY_PATH`
- `XRAY_CLIENT_META_PATH`
- `XRAY_RELAY_HOST`
- `XRAY_RELAY_PORT`
- `XRAY_RELAY_SERVICE_NAME`
- `XRAY_RELAY_SSH_KEY_PATH`
- `XRAY_RELAY_SSH_USER`
- `XRAY_ONLINE_WINDOW_MINUTES`
- `XRAY_EXPECTED_EGRESS_IP`
- `XRAY_ADMIN_USER`
- `XRAY_ADMIN_PASSWORD`
- `XRAY_TOPOLOGY_CACHE_TTL_SECONDS`

## Bootstrap plan

### bootstrap-gateway.sh
Responsibilities:
- install runtime dependencies
- place xray binary
- render frontend config from env/template
- write systemd unit for `xray-frontend.service`
- enable and start service
- create runtime directories for control-plane if needed

### bootstrap-egress.sh
Responsibilities:
- install runtime dependencies
- place xray binary
- render relay config from env/template
- write systemd unit for `xray-relay.service`
- enable and start service

### bootstrap-control-plane.sh
Responsibilities:
- prepare control-plane directory
- place app/runtime files
- place relay SSH key
- write `.env`
- start containerized control-plane via docker compose

## Validation plan

### validate-gateway.sh
Checks:
- `xray-frontend.service` active
- frontend port listening
- frontend config exists

### validate-egress.sh
Checks:
- `xray-relay.service` active
- relay port listening
- relay config exists

### validate-end-to-end.sh
Checks:
- control-plane reachable
- relay reachable from gateway/control-plane
- client can connect to frontend
- observed egress IP equals expected egress IP

## Secrets handling

Portable v1 rules:
- do not commit runtime secrets
- use `.env` and mounted secret files
- keep SSH private keys outside git
- keep reality private key outside git
- keep relay UUID configurable

## Runtime mode policy

### Portable v1 recommended split
- Xray frontend: host-managed systemd service
- Xray relay: host-managed systemd service
- control-plane: Docker container

This is the stable bridge design for v1.

## What should be standardized next

1. config templates
2. bootstrap scripts
3. validation scripts
4. runtime directory contract
5. backup/rollback contract before config apply
6. production auth/secret handling

## Success criteria for portable v1

Portable v1 is done when:
- a new gateway host can be bootstrapped from env/template/script
- a new egress host can be bootstrapped from env/template/script
- control-plane can be started from env/template/script
- health checks can confirm the installation
- a client can connect and see the configured egress IP
