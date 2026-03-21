# Container run for FastAPI control-plane

## Files
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

## Build
```bash
make build
```

## Run
```bash
cp .env.example .env
# edit .env
mkdir -p runtime/frontend runtime/ssh
# place frontend runtime files into runtime/frontend:
# - config.json
# - access.log
# - clients-meta.json
# - xray (binary, optional if public key derivation is needed)
# place SSH private key for relay access into runtime/ssh/relay_ssh_key
chmod 600 runtime/ssh/relay_ssh_key

make up
```

## Helper commands
```bash
make logs
make ps
make down

# or use scripts directly
./scripts/control-plane-up.sh
./scripts/control-plane-logs.sh
./scripts/control-plane-down.sh
```

## Exposed app
- `http://<host>:8000`

## Important note
Current containerized control-plane is designed as a pragmatic bridge stage:
- it can read/write mounted frontend runtime files
- it can probe the active relay path via `XRAY_RELAY_HOST`
- it can SSH to relay management via `XRAY_RELAY_PUBLIC_HOST` (or `XRAY_RELAY_HOST` if unset) using the mounted key
- it surfaces direct vs IPSec topology context from `XRAY_TRANSPORT_MODE`, `XRAY_RELAY_PRIVATE_HOST`, and tunnel IP envs
- it does not yet replace a future node-agent architecture
