# Bootstrap scripts

Implemented scripts:
- `init-env.sh`
- `bootstrap-gateway.sh`
- `bootstrap-egress.sh`
- `bootstrap-control-plane.sh`

Notes:
- gateway/egress scripts automatically download and install the Xray binary if it is missing
- control-plane script stages the repo, copies `.env`, auto-imports existing frontend runtime files when present, and can auto-copy relay SSH key if `XRAY_RELAY_SSH_KEY_SOURCE` is defined in env
- control-plane script now runs `docker compose up -d --build` itself
