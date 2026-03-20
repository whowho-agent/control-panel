#!/usr/bin/env python3
import base64
import html
import json
import os
import re
import secrets
import socket
import subprocess
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG_PATH = Path(os.environ.get('XRAY_FRONTEND_CONFIG', '/opt/xray-frontend/config.json'))
META_PATH = Path(os.environ.get('XRAY_ADMIN_META', '/opt/xray-frontend/clients-meta.json'))
ACCESS_LOG = Path(os.environ.get('XRAY_FRONTEND_ACCESS_LOG', '/opt/xray-frontend/access.log'))
FRONTEND_SERVICE = os.environ.get('XRAY_FRONTEND_SERVICE', 'xray-frontend')
RELAY_SERVICE = os.environ.get('XRAY_RELAY_SERVICE', 'xray-relay')
BIND = os.environ.get('XRAY_ADMIN_BIND', '0.0.0.0')
PORT = int(os.environ.get('XRAY_ADMIN_PORT', '9080'))
ADMIN_USER = os.environ.get('XRAY_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('XRAY_ADMIN_PASS', '')
WG_HOST = os.environ.get('XRAY_WG_HOST', 'gateway.example.com')
GATEWAY_LABEL = os.environ.get('XRAY_GATEWAY_LABEL', 'gateway')
RELAY_HOST = os.environ.get('XRAY_RELAY_HOST', 'relay.example.com')
RELAY_LABEL = os.environ.get('XRAY_RELAY_LABEL', 'egress')
RELAY_PORT = int(os.environ.get('XRAY_RELAY_PORT', '9443'))
RELAY_UUID = os.environ.get('XRAY_RELAY_UUID', '')
DEFAULT_LABEL = os.environ.get('XRAY_CLIENT_LABEL', 'xray-client')
ONLINE_WINDOW_MINUTES = int(os.environ.get('XRAY_ONLINE_WINDOW_MINUTES', '5'))

if not ADMIN_PASS:
    raise SystemExit('XRAY_ADMIN_PASS is required')


def sh(*args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def load_json(path: Path):
    return json.loads(path.read_text())


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def load_config():
    return load_json(CONFIG_PATH)


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


def load_meta():
    if META_PATH.exists():
        return load_json(META_PATH)
    return {"clients": {}}


def save_meta(meta):
    save_json(META_PATH, meta)


def frontend_inbound(cfg):
    for inbound in cfg.get('inbounds', []):
        if inbound.get('tag') == 'frontend-in':
            return inbound
    raise KeyError('frontend-in not found')


def frontend_outbound(cfg):
    for outbound in cfg.get('outbounds', []):
        if outbound.get('tag') == 'to-relay':
            return outbound
    raise KeyError('to-relay not found')


def relay_inbound(cfg):
    for inbound in cfg.get('inbounds', []):
        if inbound.get('tag') == 'relay-in':
            return inbound
    raise KeyError('relay-in not found')


def parse_access_activity():
    result = {}
    if not ACCESS_LOG.exists():
        return result
    line_re = re.compile(r'^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+) from (?P<ip>[^:]+):\d+ accepted .*? \[(?P<inbound>[^\]]+) ->')
    try:
        lines = ACCESS_LOG.read_text(errors='ignore').splitlines()[-2000:]
    except Exception:
        return result
    for line in lines:
        m = line_re.search(line)
        if not m or m.group('inbound') != 'frontend-in':
            continue
        ip = m.group('ip')
        try:
            ts = datetime.strptime(m.group('ts'), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        prev = result.get(ip)
        if not prev or ts > prev['last_seen_dt']:
            result[ip] = {'last_seen_dt': ts, 'last_seen': ts.isoformat().replace('+00:00', 'Z'), 'source_ip': ip}
    return result


def derive_public_key(private_key):
    try:
        p = sh('/opt/xray-frontend/xray', 'x25519', '-i', private_key, check=True)
        for line in p.stdout.splitlines():
            if line.startswith('Password:'):
                return line.split(':', 1)[1].strip()
            if line.startswith('Public key:'):
                return line.split(':', 1)[1].strip()
    except Exception:
        return ''
    return ''


def frontend_params(cfg):
    inbound = frontend_inbound(cfg)
    rs = inbound['streamSettings']['realitySettings']
    outbound = frontend_outbound(cfg)
    vnext = outbound['settings']['vnext'][0]
    public_key = derive_public_key(rs.get('privateKey', ''))
    return {
        'port': inbound['port'],
        'server_name': (rs.get('serverNames') or [''])[0],
        'public_key': public_key,
        'private_key': rs.get('privateKey', ''),
        'fingerprint': rs.get('settings', {}).get('fingerprint', 'firefox'),
        'short_ids': rs.get('shortIds', []),
        'spider_x': rs.get('settings', {}).get('spiderX', '/'),
        'target': rs.get('target', ''),
        'relay_host': vnext['address'],
        'relay_port': vnext['port'],
        'relay_uuid': vnext['users'][0]['id'],
    }


def relay_params_from_frontend(cfg):
    outbound = frontend_outbound(cfg)
    vnext = outbound['settings']['vnext'][0]
    return {
        'port': vnext['port'],
        'uuid': vnext['users'][0]['id'] or RELAY_UUID,
        'listen': 'remote',
        'host': vnext['address'],
    }


def build_uri(host, port, client_id, params, label, short_id=None):
    sid = short_id or (params['short_ids'][0] if params['short_ids'] else '')
    q = {
        'type': 'tcp',
        'security': 'reality',
        'pbk': params['public_key'],
        'fp': params['fingerprint'],
        'sni': params['server_name'],
        'sid': sid,
        'spx': params['spider_x'],
        'encryption': 'none',
    }
    return f"vless://{client_id}@{host}:{port}?{urllib.parse.urlencode(q)}#{urllib.parse.quote(label)}"


def restart_service(name):
    sh('systemctl', 'restart', name)


def service_status(name):
    res = sh('systemctl', 'is-active', name, check=False)
    return res.stdout.strip() or res.stderr.strip()


def port_open(host, port, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def clients(cfg, meta):
    inbound = frontend_inbound(cfg)
    listed = inbound['settings'].get('clients', [])
    activity = parse_access_activity()
    now = datetime.now(timezone.utc)
    out = []
    latest = max(activity.values(), key=lambda x: x['last_seen_dt']) if activity else None
    for idx, c in enumerate(listed):
        cid = c['id']
        info = meta.get('clients', {}).get(cid, {})
        observed = info.get('last_seen') or ('')
        source_ip = info.get('source_ip', '')
        if not observed and idx == 0 and latest:
            observed = latest['last_seen']
            source_ip = latest['source_ip']
        status = 'offline'
        if observed:
            try:
                dt = datetime.fromisoformat(observed.replace('Z', '+00:00'))
                if now - dt <= timedelta(minutes=ONLINE_WINDOW_MINUTES):
                    status = 'online'
            except Exception:
                pass
        out.append({
            'id': cid,
            'name': info.get('name') or c.get('email') or cid,
            'email': c.get('email', ''),
            'short_id': info.get('short_id', ''),
            'created_at': info.get('created_at', ''),
            'last_seen': observed,
            'source_ip': source_ip,
            'status': status,
        })
    return out


def create_client(name, host):
    cfg = load_config()
    meta = load_meta()
    inbound = frontend_inbound(cfg)
    params = frontend_params(cfg)
    client_id = str(uuid.uuid4())
    short_id = secrets.choice(params['short_ids']) if params['short_ids'] else ''
    inbound['settings'].setdefault('clients', []).append({'id': client_id})
    save_config(cfg)
    meta.setdefault('clients', {})[client_id] = {
        'name': name,
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'short_id': short_id,
        'last_seen': '',
        'source_ip': '',
    }
    save_meta(meta)
    restart_service(FRONTEND_SERVICE)
    return build_uri(host, params['port'], client_id, params, name, short_id)


def delete_client(client_id):
    cfg = load_config()
    inbound = frontend_inbound(cfg)
    before = len(inbound['settings'].get('clients', []))
    inbound['settings']['clients'] = [c for c in inbound['settings'].get('clients', []) if c.get('id') != client_id]
    if len(inbound['settings']['clients']) == before:
        return False
    save_config(cfg)
    meta = load_meta()
    meta.get('clients', {}).pop(client_id, None)
    save_meta(meta)
    restart_service(FRONTEND_SERVICE)
    return True


def update_frontend(form):
    cfg = load_config()
    inbound = frontend_inbound(cfg)
    outbound = frontend_outbound(cfg)
    rs = inbound['streamSettings']['realitySettings']
    inbound['port'] = int(form['frontend_port'])
    rs['target'] = form['frontend_target']
    rs['serverNames'] = [form['frontend_sni']]
    rs['settings'] = rs.get('settings', {})
    rs['settings']['fingerprint'] = form['frontend_fp']
    rs['settings']['spiderX'] = form.get('frontend_spider', '/') or '/'
    rs['shortIds'] = [x.strip() for x in form['frontend_shortids'].split(',') if x.strip()]
    outbound['settings']['vnext'][0]['address'] = form['relay_host']
    outbound['settings']['vnext'][0]['port'] = int(form['relay_port'])
    save_config(cfg)
    restart_service(FRONTEND_SERVICE)


def update_relay(form):
    fcfg = load_config()
    fob = frontend_outbound(fcfg)
    fob['settings']['vnext'][0]['address'] = form['relay_public_host'].strip()
    fob['settings']['vnext'][0]['port'] = int(form['relay_listen_port'])
    fob['settings']['vnext'][0]['users'][0]['id'] = form['relay_uuid'].strip()
    save_config(fcfg)
    restart_service(FRONTEND_SERVICE)


def page_template(title, body):
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>
<style>
:root {{ --bg:#0b1020; --panel:#121933; --panel2:#182240; --text:#e9eefc; --muted:#9aa8d6; --ok:#25c27a; --bad:#f05d5e; --warn:#f0b24d; --link:#7ab8ff; --line:#2b3561; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background:linear-gradient(180deg,#0b1020,#0d1428); color:var(--text); }}
a {{ color:var(--link); text-decoration:none; }}
.wrap {{ max-width: 1380px; margin: 0 auto; padding: 24px; }}
.nav {{ display:flex; gap:10px; margin-bottom:20px; flex-wrap:wrap; }}
.nav a {{ background:var(--panel); border:1px solid var(--line); padding:10px 14px; border-radius:10px; }}
.grid {{ display:grid; grid-template-columns: repeat(12,1fr); gap:16px; }}
.card {{ background:rgba(18,25,51,.9); border:1px solid var(--line); border-radius:16px; padding:18px; box-shadow:0 8px 28px rgba(0,0,0,.25); }}
.kpi {{ font-size:28px; font-weight:700; margin-top:8px; }}
.small {{ color:var(--muted); font-size:13px; }}
.badge {{ display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; }}
.ok {{ background:rgba(37,194,122,.15); color:#7ef0b0; }}
.bad {{ background:rgba(240,93,94,.15); color:#ff9b9b; }}
.warn {{ background:rgba(240,178,77,.15); color:#ffd28a; }}
.topology {{ display:grid; grid-template-columns: 1fr 120px 1fr 120px 1fr; align-items:center; gap:10px; margin-top:8px; }}
.node {{ background:var(--panel2); border:1px solid var(--line); border-radius:14px; padding:16px; min-height:120px; }}
.arrow {{ text-align:center; color:var(--muted); font-size:22px; }}
input, textarea {{ width:100%; background:#0b1020; color:var(--text); border:1px solid var(--line); border-radius:10px; padding:10px; }}
textarea {{ min-height:88px; }}
button {{ background:#3b82f6; color:white; border:none; padding:10px 14px; border-radius:10px; cursor:pointer; }}
button.danger {{ background:#c0392b; }}
table {{ width:100%; border-collapse: collapse; }}
th, td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
label {{ display:block; font-size:13px; color:var(--muted); margin-bottom:6px; }}
.row2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
.row3 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }}
code {{ font-size:12px; word-break:break-all; }}
hr {{ border:none; border-top:1px solid var(--line); margin:16px 0; }}
</style></head><body><div class='wrap'>
<div class='nav'><a href='/'>Dashboard</a><a href='/clients'>Clients</a><a href='/config'>Config</a></div>
{body}
</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = 'XrayAdmin/0.3'

    def _authorized(self):
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Basic '):
            return False
        try:
            raw = base64.b64decode(auth.split(' ', 1)[1]).decode()
        except Exception:
            return False
        user, _, pw = raw.partition(':')
        return secrets.compare_digest(user, ADMIN_USER) and secrets.compare_digest(pw, ADMIN_PASS)

    def _require_auth(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="xray-admin"')
        self.end_headers()

    def _redirect(self, location='/'):
        self.send_response(303)
        self.send_header('Location', location)
        self.end_headers()

    def _html(self, body, status=200, title='Xray Admin'):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(page_template(title, body).encode())

    def _png(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.end_headers()
        self.wfile.write(data)

    def dashboard(self):
        cfg = load_config()
        params = frontend_params(cfg)
        rparams = relay_params_from_frontend(cfg)
        meta = load_meta()
        cls = clients(cfg, meta)
        online = sum(1 for c in cls if c['status'] == 'online')
        body = f"""
<h1>Dashboard</h1>
<div class='grid'>
  <div class='card' style='grid-column: span 3'><div class='small'>Clients</div><div class='kpi'>{len(cls)}</div></div>
  <div class='card' style='grid-column: span 3'><div class='small'>Online now</div><div class='kpi'>{online}</div></div>
  <div class='card' style='grid-column: span 3'><div class='small'>Frontend</div><div class='kpi'>{html.escape(service_status(FRONTEND_SERVICE))}</div></div>
  <div class='card' style='grid-column: span 3'><div class='small'>Relay</div><div class='kpi'>{html.escape(service_status(RELAY_SERVICE))}</div></div>
  <div class='card' style='grid-column: span 12'>
    <h2 style='margin-top:0'>Topology</h2>
    <div class='topology'>
      <div class='node'><div class='small'>Client Edge</div><div class='kpi'>Internet Clients</div><div><span class='badge ok'>Traffic present</span></div></div>
      <div class='arrow'>→</div>
      <div class='node'><div class='small'>Gateway Node</div><div class='kpi'>{html.escape(GATEWAY_LABEL)}</div><div>Frontend service: <span class='badge {'ok' if service_status(FRONTEND_SERVICE)=='active' else 'bad'}'>{html.escape(service_status(FRONTEND_SERVICE))}</span></div><div class='small'>Entry {html.escape(WG_HOST)}:{params['port']}</div></div>
      <div class='arrow'>→</div>
      <div class='node'><div class='small'>Egress Node</div><div class='kpi'>{html.escape(RELAY_LABEL)}</div><div>Relay port: <span class='badge {'ok' if port_open(RELAY_HOST, rparams['port']) else 'bad'}'>{'reachable' if port_open(RELAY_HOST, rparams['port']) else 'down'}</span></div><div class='small'>{html.escape(RELAY_HOST)}:{rparams['port']}</div></div>
    </div>
  </div>
  <div class='card' style='grid-column: span 6'>
    <h2 style='margin-top:0'>Frontend health</h2>
    <div>Port: <code>{params['port']}</code></div>
    <div>SNI: <code>{html.escape(params['server_name'])}</code></div>
    <div>Target: <code>{html.escape(params['target'])}</code></div>
    <div>Public key: <code>{html.escape(params['public_key'])}</code></div>
    <div>Short IDs: <code>{html.escape(', '.join(params['short_ids']))}</code></div>
  </div>
  <div class='card' style='grid-column: span 6'>
    <h2 style='margin-top:0'>Relay health</h2>
    <div>Service: <span class='badge {'ok' if service_status(RELAY_SERVICE)=='active' else 'bad'}'>{html.escape(service_status(RELAY_SERVICE))}</span></div>
    <div>Relay UUID: <code>{html.escape(rparams['uuid'])}</code></div>
    <div>Frontend → Relay: <span class='badge {'ok' if port_open(RELAY_HOST, rparams['port']) else 'bad'}'>{'reachable' if port_open(RELAY_HOST, rparams['port']) else 'unreachable'}</span></div>
    <div>Expected egress IP: <code>{html.escape(RELAY_HOST)}</code></div>
  </div>
</div>
"""
        return self._html(body)

    def clients_page(self):
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host', '').split(':')[0] or WG_HOST
        cfg = load_config()
        meta = load_meta()
        params = frontend_params(cfg)
        rows = []
        for c in clients(cfg, meta):
            uri = build_uri(host, params['port'], c['id'], params, c['name'], c['short_id'])
            badge = 'ok' if c['status'] == 'online' else 'bad'
            rows.append(f"""
<tr>
<td>{html.escape(c['name'])}</td>
<td><span class='badge {badge}'>{html.escape(c['status'])}</span></td>
<td>{html.escape(c['last_seen']) or '-'}</td>
<td>{html.escape(c['source_ip']) or '-'}</td>
<td><code>{html.escape(c['id'])}</code></td>
<td><code>{html.escape(c['short_id'])}</code></td>
<td><a href=\"{html.escape(uri)}\">URI</a></td>
<td><a href=\"/qr?uri={urllib.parse.quote(uri, safe='')}\" target=\"_blank\">QR</a></td>
<td><form method='post' action='/delete' onsubmit=\"return confirm('Delete client?')\"><input type='hidden' name='id' value='{html.escape(c['id'])}'/><button class='danger'>Delete</button></form></td>
</tr>""")
        body = f"""
<h1>Clients</h1>
<div class='card'>
<form method='post' action='/create'>
<label>Client name</label>
<div class='row2'><input type='text' name='name' placeholder='{DEFAULT_LABEL}' required /><div><button type='submit'>Create client</button></div></div>
</form>
</div>
<div class='card'>
<table>
<thead><tr><th>Name</th><th>Status</th><th>Last seen</th><th>Source IP</th><th>UUID</th><th>Short ID</th><th>URI</th><th>QR</th><th>Action</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="9">No clients</td></tr>'}</tbody>
</table>
</div>
"""
        return self._html(body, title='Clients')

    def config_page(self):
        fcfg = load_config()
        fp = frontend_params(fcfg)
        rp = relay_params_from_frontend(fcfg)
        body = f"""
<h1>Config Editor</h1>
<div class='grid'>
  <div class='card' style='grid-column: span 7'>
    <h2 style='margin-top:0'>Frontend</h2>
    <form method='post' action='/config/frontend'>
      <div class='row3'>
        <div><label>Frontend port</label><input name='frontend_port' value='{fp['port']}' /></div>
        <div><label>SNI</label><input name='frontend_sni' value='{html.escape(fp['server_name'])}' /></div>
        <div><label>Fingerprint</label><input name='frontend_fp' value='{html.escape(fp['fingerprint'])}' /></div>
      </div>
      <div class='row2'>
        <div><label>Target</label><input name='frontend_target' value='{html.escape(fp['target'])}' /></div>
        <div><label>SpiderX</label><input name='frontend_spider' value='{html.escape(fp['spider_x'])}' /></div>
      </div>
      <div class='row2'>
        <div><label>Relay host</label><input name='relay_host' value='{html.escape(fp['relay_host'])}' /></div>
        <div><label>Relay port</label><input name='relay_port' value='{fp['relay_port']}' /></div>
      </div>
      <label>Short IDs (comma separated)</label>
      <textarea name='frontend_shortids'>{html.escape(','.join(fp['short_ids']))}</textarea>
      <hr />
      <button type='submit'>Save frontend config</button>
    </form>
  </div>
  <div class='card' style='grid-column: span 5'>
    <h2 style='margin-top:0'>Relay</h2>
    <form method='post' action='/config/relay'>
      <label>Relay public host</label>
      <input name='relay_public_host' value='{html.escape(RELAY_HOST)}' />
      <label>Relay listen port</label>
      <input name='relay_listen_port' value='{rp['port']}' />
      <label>Relay UUID</label>
      <input name='relay_uuid' value='{html.escape(rp['uuid'])}' />
      <hr />
      <button type='submit'>Save relay config</button>
    </form>
  </div>
</div>
"""
        return self._html(body, title='Config')

    def do_GET(self):
        if not self._authorized():
            return self._require_auth()
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/qr':
            q = urllib.parse.parse_qs(parsed.query)
            uri = q.get('uri', [''])[0]
            if not uri:
                return self._html('missing uri', 400)
            p = subprocess.run(['qrencode', '-o', '-', '-s', '8', '-m', '2', uri], capture_output=True)
            if p.returncode != 0:
                return self._html('qrencode failed', 500)
            return self._png(p.stdout)
        if parsed.path == '/':
            return self.dashboard()
        if parsed.path == '/clients':
            return self.clients_page()
        if parsed.path == '/config':
            return self.config_page()
        return self._html('not found', 404)

    def do_POST(self):
        if not self._authorized():
            return self._require_auth()
        length = int(self.headers.get('Content-Length', '0'))
        data = urllib.parse.parse_qs(self.rfile.read(length).decode())
        form = {k: v[0] for k, v in data.items()}
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host', '').split(':')[0] or WG_HOST
        if self.path == '/create':
            create_client((form.get('name') or DEFAULT_LABEL).strip(), host)
            return self._redirect('/clients')
        if self.path == '/delete':
            delete_client((form.get('id') or '').strip())
            return self._redirect('/clients')
        if self.path == '/config/frontend':
            update_frontend(form)
            return self._redirect('/config')
        if self.path == '/config/relay':
            update_relay(form)
            return self._redirect('/config')
        return self._html('not found', 404)


def main():
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f'Listening on {BIND}:{PORT}', flush=True)
    httpd.serve_forever()


if __name__ == '__main__':
    main()
