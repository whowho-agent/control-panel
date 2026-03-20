# Xray Admin MVP

Lightweight web admin for the standalone Xray frontend.

## Features
- Basic auth protected UI
- List clients from `/opt/xray-frontend/config.json`
- Create client
- Delete client
- Generate VLESS URI
- Generate QR PNG on demand
- Show `xray-frontend` service status
- Check relay TCP reachability

## Runtime env
- `XRAY_ADMIN_USER`
- `XRAY_ADMIN_PASS`
- `XRAY_ADMIN_BIND` (default `0.0.0.0`)
- `XRAY_ADMIN_PORT` (default `9080`)
- `XRAY_FRONTEND_CONFIG` (default `/opt/xray-frontend/config.json`)
- `XRAY_FRONTEND_SERVICE` (default `xray-frontend`)
- `XRAY_RELAY_HOST` (default `72.56.109.197`)
- `XRAY_RELAY_PORT` (default `9443`)

## Notes
This admin is intentionally standalone and does not depend on 3x-ui.
