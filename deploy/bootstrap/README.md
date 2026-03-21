# Bootstrap scripts

Implemented scripts:
- `init-env.sh`
- `bootstrap-gateway.sh`
- `bootstrap-egress.sh`
- `bootstrap-standalone.sh`
- `bootstrap-control-plane.sh`

Notes:
- `lib.sh` is now the canonical bootstrap behavior layer: env loading, required-var validation, host preflight logging, apt/dpkg lock-safe package installs, Xray binary install, and TCP readiness waits live there.
- gateway/egress scripts automatically download and install the Xray binary if it is missing.
- bootstrap scripts wait out `unattended-upgrades` / apt / dpkg lock contention on fresh Ubuntu hosts instead of failing fast on `lock-frontend` races.
- `bootstrap-standalone.sh` is the preferred entrypoint when you want to run everything from the gateway node: it SSHes to egress, stages the relay bootstrap files there, runs remote bootstrap, waits for relay readiness, then configures the local frontend against that egress host.
- `bootstrap-standalone.sh` expects `deploy/env/standalone.env`, plus the usual `gateway.env` and `egress.env`.
- gateway/control-plane bootstrap block on the configured relay endpoint before proceeding, which prevents premature private cutover to `10.10.10.2:9443`.
- control-plane bootstrap now loads the env file before readiness checks, so relay wait logic works consistently in both direct and IPSec modes.
- control-plane script stages the repo, copies `.env`, auto-imports existing frontend runtime files when present, and can auto-copy relay SSH key if `XRAY_RELAY_SSH_KEY_SOURCE` is defined in env.
- control-plane script runs `docker compose up -d --build` itself.
