# Bootstrap scripts

Implemented scripts:
- `init-env.sh`
- `bootstrap-gateway.sh`
- `bootstrap-egress.sh`
- `bootstrap-standalone.sh`
- `bootstrap-control-plane.sh`

Notes:
- gateway/egress scripts automatically download and install the Xray binary if it is missing
- `bootstrap-standalone.sh` is the preferred entrypoint when you want to run everything from the gateway node: it SSHes to egress, stages the relay bootstrap files there, runs remote bootstrap, then configures the local frontend against that egress host
- `bootstrap-standalone.sh` expects `deploy/env/standalone.env`, plus the usual `gateway.env` and `egress.env`
- control-plane script stages the repo, copies `.env`, auto-imports existing frontend runtime files when present, and can auto-copy relay SSH key if `XRAY_RELAY_SSH_KEY_SOURCE` is defined in env
- control-plane script now runs `docker compose up -d --build` itself
