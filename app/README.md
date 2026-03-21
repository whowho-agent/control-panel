# FastAPI control-plane

Pragmatic clean architecture layout:

- `app/domain`
- `app/repos`
- `app/services`
- `app/api`
- `app/templates`

Current scope:
- dashboard UI via FastAPI templates
- clients UI via FastAPI templates
- list/create/delete/enable/disable frontend clients
- topology health with synthetic egress probe
- frontend config API/UI
- relay config API/UI
- live runtime config writes + service restart path

## Entry point

- `app.main:app`

## Runtime assumptions

- frontend config is read from `XRAY_FRONTEND_CONFIG_PATH`
- frontend access log is read from `XRAY_FRONTEND_ACCESS_LOG_PATH`
- client metadata is stored in `XRAY_CLIENT_META_PATH`
- service control is done via `systemctl` or `nsenter ... systemctl` when `XRAY_FRONTEND_USE_NSENTER=1`
- relay health is checked over SSH using `XRAY_RELAY_*` settings

## Validation and operability guarantees

- API payloads are validated for port ranges, hostnames, UUID format, and REALITY short ID format
- duplicate frontend client names are rejected before config mutation
- UI forms redirect back with explicit success/error state instead of raw 500s on common validation failures
- topology health is cached for `XRAY_TOPOLOGY_CACHE_TTL_SECONDS` to avoid hammering the relay node
