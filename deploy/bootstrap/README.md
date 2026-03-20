# Bootstrap scripts

Implemented scripts:
- `bootstrap-gateway.sh`
- `bootstrap-egress.sh`
- `bootstrap-control-plane.sh`

Notes:
- gateway/egress scripts expect the Xray binary to already exist at `/opt/xray-frontend/xray` or `/opt/xray-relay/xray`
- control-plane script stages the repo and `.env`, then expects runtime frontend files and relay SSH key to be placed before `docker compose up -d --build`
