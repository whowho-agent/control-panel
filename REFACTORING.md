# Refactoring Plan: control-panel

## Обзор

Пять независимых фаз. Каждая деплоится отдельно, тесты зелёные на каждом шаге.
Поведение не меняется до Фазы 5.

```
Фаза 1 ──► Фаза 2 ──► Фаза 3 ──► Фаза 4

Фаза 5 — независима, можно параллельно после Фазы 1
```

---

## Фаза 1 — Hygiene

> ~2 часа · нулевой риск · нет изменений в поведении

### 1.1 Subprocess timeouts

Все вызовы `subprocess.run` без `timeout=` — добавить:
- `timeout=30` — xray, systemctl
- `timeout=10` — ssh

### 1.2 Logging

Добавить `logger = logging.getLogger(__name__)` в `XrayFrontendRepo` и `XrayFrontendService`.

Логировать:
- Старт и финиш `apply_config`
- `restart_frontend` (до и после)
- Rollback (с причиной)
- SSH errors в `RelayNodeRepo`

### 1.3 Переместить `_parse_activity()` в `XrayFrontendRepo`

Метод читает файл через репозиторий, но живёт в сервисе — нарушение слоёв.

```python
# было: service._parse_activity()

# стало: repo
def parse_activity(self) -> dict[str, ActivityRecord]: ...

# service — просто вызов
activity = self._frontend_repo.parse_activity()
```

### 1.4 Разбить `list_clients()` на приватные методы

65 строк в одном методе → три чётких шага:

```python
def list_clients(self) -> list[FrontendClient]:
    activity = self._frontend_repo.parse_activity()
    clients = self._build_clients(activity)
    self._sync_meta(clients)
    return clients
```

---

## Фаза 2 — Domain extractions

> ~3 часа · низкий риск · чистые добавления в `domain/`

### 2.1 `VlessUriBuilder`

Protocol knowledge (Reality query params, URL encoding) живёт в сервисе — должна быть в domain.

```python
# domain/vless_uri.py
@dataclass
class VlessUriBuilder:
    def build(
        self,
        client: FrontendClient,
        host: str,
        config: FrontendConfigResult,
    ) -> str: ...
```

### 2.2 `ClientStatus`

Логика определения статуса (online / offline / activity-unattributed) размазана по `list_clients()`.

```python
# domain/client_status.py
def compute_status(
    client_id: str,
    enabled: bool,
    last_seen: str | None,
    window_minutes: int,
    is_sole_enabled_client: bool,
) -> str: ...
```

Тестируется изолированно без БД и репозиториев.

### 2.3 `TransportMode`

IPSec-логика встречается в трёх местах (`__init__`, `get_topology_health`, `_transport_label`).

```python
# domain/transport_mode.py
@dataclass(frozen=True)
class TransportMode:
    mode: str  # "direct" | "ipsec"

    @property
    def label(self) -> str: ...

    @property
    def is_ipsec(self) -> bool: ...
```

---

## Фаза 3 — `XrayConfigAccessor`

> ~4 часа · средний риск · prerequisite для Фазы 4

Самое важное перед разбивкой сервиса. Текущая навигация по JSON хрупкая:

```python
# сейчас везде так — сломается при переименовании тега
config["inbounds"][0]["settings"]["clients"]
config["outbounds"][tag="to-relay"]["settings"]["vnext"][0]
```

Создать типизированный accessor. Теги `"frontend-in"` и `"to-relay"` живут только здесь.

```python
# domain/xray_config.py
class XrayConfigAccessor:
    def __init__(self, raw: dict) -> None: ...

    def frontend_clients(self) -> list[dict]: ...
    def set_frontend_clients(self, clients: list[dict]) -> None: ...
    def relay_outbound(self) -> dict: ...
    def frontend_inbound(self) -> dict: ...
    def to_dict(self) -> dict: ...
```

`XrayFrontendRepo` принимает и возвращает `XrayConfigAccessor` вместо голого `dict`.

---

## Фаза 4 — Разбивка `XrayFrontendService`

> ~6 часов · средний риск · требует Фазы 1–3

После фаз 1–3 сервис уже ~200 строк и чище. Разбиваем на три:

```
app/services/
  client_service.py      # CRUD клиентов + статусы + URI
  config_service.py      # validate / apply frontend / relay config
  topology_service.py    # health aggregation + TTL cache
```

`XrayFrontendService` остаётся как **фасад** — API layer не меняется:

```python
class XrayFrontendService:
    def __init__(self, ...):
        self._clients = ClientService(...)
        self._config = ConfigService(...)
        self._topology = TopologyService(...)

    def list_clients(self):
        return self._clients.list()

    def get_topology_health(self):
        return self._topology.get()

    # ... остальные методы делегируют
```

`deps.py` не трогаем — деплой без изменений в API.

### TTL Cache

Заменить ручной TTL на декоратор:

```python
# было
if self._cache and (now - self._cache_time) < self._ttl:
    return self._cache

# стало
@ttl_cache(seconds=10)
def get(self) -> TopologyHealthResult: ...
```

---

## Фаза 5 — Relay Agent

> ~1 день · отдельный сервис · независима от Фаз 2–4

Заменяет SSH-вызовы в `RelayNodeRepo` на HTTP. SSH-ключ из `docker-compose.yml` убирается.

### 5.1 Новый минисервис `relay-agent/`

```
relay-agent/
  main.py               # FastAPI, ~80 строк
  Dockerfile
  relay-agent.service   # systemd unit
```

Эндпоинты:

| Method | Path | Ответ |
|--------|------|-------|
| `GET` | `/health` | `{"ok": true}` |
| `GET` | `/status` | `{"service": "active", "egress_ip": "1.2.3.4"}` |

Агент сам опрашивает `systemctl is-active` и `ipify.org` в фоне (раз в 60с), отдаёт закэшированное состояние.

### 5.2 Обновить `RelayNodeRepo`

```python
# было: SSH + subprocess
class RelayNodeRepo:
    def __init__(self, host, port, ssh_key_path, ...): ...

# стало: HTTP client
class RelayNodeRepo:
    def __init__(self, agent_url: str):  # "http://10.10.0.2:9100"
        self._url = agent_url

    def get_status(self) -> RelayStatus:
        r = httpx.get(f"{self._url}/status", timeout=3)
        data = r.json()
        return RelayStatus(
            service=data["service"],
            egress_ip=data["egress_ip"],
            reachable=True,
        )
```

### 5.3 Ansible role `relay_agent`

Деплой агента на egress-ноду. Добавить в `site.yml` после существующих ролей.

---

## Что не делаем

- Не меняем API контракт (endpoints, схемы) — отдельная задача
- Не добавляем DI-фреймворк — фасад в Фазе 4 достаточен
- Не трогаем bootstrap/deploy скрипты — вне scope этого плана
- Не добавляем async — текущий sync-стек достаточен для масштаба

---

## Checklist по фазам

### Фаза 1 ✓
- [x] `timeout=` на всех subprocess вызовах
- [x] logging в repo и service
- [x] `_parse_activity()` перенесён в `XrayFrontendRepo`
- [x] `list_clients()` разбит на приватные методы
- [x] Тесты зелёные

### Фаза 2 ✓
- [x] `domain/vless_uri.py` + тесты
- [x] `domain/client_status.py` + тесты
- [x] `domain/transport_mode.py` + тесты
- [x] Сервис обновлён на новые domain-классы
- [x] Тесты зелёные

### Фаза 3
- [ ] `domain/xray_config.py` с `XrayConfigAccessor`
- [ ] Тесты для accessor (все теги, edge cases)
- [ ] `XrayFrontendRepo` переведён на accessor
- [ ] Голые dict-навигации убраны
- [ ] Тесты зелёные

### Фаза 4
- [ ] `services/client_service.py` + тесты
- [ ] `services/config_service.py` + тесты
- [ ] `services/topology_service.py` + тесты
- [ ] `XrayFrontendService` — фасад, делегирует
- [ ] `ttl_cache` декоратор
- [ ] `deps.py` не изменён
- [ ] Тесты зелёные

### Фаза 5 ✓
- [x] `relay-agent/main.py`
- [ ] `relay-agent/Dockerfile` (не нужен — сервис нативный на ноде)
- [x] `relay-agent/relay-agent.service` (через Ansible template)
- [x] `RelayNodeRepo` переведён на HTTP
- [x] Ansible role `relay_agent`
- [x] SSH-ключ убран из `docker-compose.yml`
- [x] Тесты зелёные
