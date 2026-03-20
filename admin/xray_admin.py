#!/usr/bin/env python3
import base64
import html
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import urllib.parse
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG_PATH = Path(os.environ.get('XRAY_FRONTEND_CONFIG', '/opt/xray-frontend/config.json'))
META_PATH = Path(os.environ.get('XRAY_ADMIN_META', '/opt/xray-frontend/clients-meta.json'))
SERVICE_NAME = os.environ.get('XRAY_FRONTEND_SERVICE', 'xray-frontend')
BIND = os.environ.get('XRAY_ADMIN_BIND', '0.0.0.0')
PORT = int(os.environ.get('XRAY_ADMIN_PORT', '9080'))
ADMIN_USER = os.environ.get('XRAY_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('XRAY_ADMIN_PASS', '')
EGRESS_HOST = os.environ.get('XRAY_RELAY_HOST', '72.56.109.197')
EGRESS_PORT = int(os.environ.get('XRAY_RELAY_PORT', '9443'))
DEFAULT_LABEL = os.environ.get('XRAY_CLIENT_LABEL', 'xray-client')

if not ADMIN_PASS:
    raise SystemExit('XRAY_ADMIN_PASS is required')


def sh(*args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def load_config():
    return json.loads(CONFIG_PATH.read_text())


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + '\n')


def load_meta():
    if META_PATH.exists():
        return json.loads(META_PATH.read_text())
    return {"clients": {}}


def save_meta(meta):
    META_PATH.write_text(json.dumps(meta, indent=2) + '\n')


def frontend_inbound(cfg):
    for inbound in cfg.get('inbounds', []):
        if inbound.get('tag') == 'frontend-in':
            return inbound
    raise KeyError('frontend-in not found')


def client_list(cfg, meta):
    inbound = frontend_inbound(cfg)
    clients = inbound['settings'].get('clients', [])
    result = []
    for c in clients:
        cid = c['id']
        info = meta.get('clients', {}).get(cid, {})
        result.append({
            'id': cid,
            'name': info.get('name') or c.get('email') or cid,
            'email': c.get('email', ''),
            'created_at': info.get('created_at', ''),
            'short_id': info.get('short_id') or '',
            'enabled': c.get('enable', True),
        })
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
    port = inbound['port']
    public_key = rs.get('settings', {}).get('publicKey', '') or derive_public_key(rs.get('privateKey', ''))
    return {
        'port': port,
        'server_names': rs.get('serverNames', []),
        'public_key': public_key,
        'fingerprint': rs.get('settings', {}).get('fingerprint', 'firefox'),
        'short_ids': rs.get('shortIds', []),
        'spider_x': rs.get('settings', {}).get('spiderX', '/'),
    }


def build_uri(host, port, client_id, params, label, short_id=None):
    sid = short_id or (params['short_ids'][0] if params['short_ids'] else '')
    sni = params['server_names'][0] if params['server_names'] else ''
    q = {
        'type': 'tcp',
        'security': 'reality',
        'pbk': params['public_key'],
        'fp': params['fingerprint'],
        'sni': sni,
        'sid': sid,
        'spx': params['spider_x'],
        'encryption': 'none',
    }
    return f"vless://{client_id}@{host}:{port}?{urllib.parse.urlencode(q)}#{urllib.parse.quote(label)}"


def restart_frontend():
    sh('systemctl', 'restart', SERVICE_NAME)


def service_status(name):
    res = sh('systemctl', 'is-active', name, check=False)
    return res.stdout.strip() or res.stderr.strip()


def relay_reachable():
    try:
        with socket.create_connection((EGRESS_HOST, EGRESS_PORT), timeout=3):
            return True
    except OSError:
        return False


def create_client(name, host):
    cfg = load_config()
    meta = load_meta()
    inbound = frontend_inbound(cfg)
    params = frontend_params(cfg)
    client_id = str(uuid.uuid4())
    short_id = secrets.choice(params['short_ids']) if params['short_ids'] else ''
    client = {
        'id': client_id,
        'email': name,
        'flow': '',
        'level': 0,
    }
    inbound['settings'].setdefault('clients', []).append(client)
    save_config(cfg)
    meta.setdefault('clients', {})[client_id] = {
        'name': name,
        'created_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'short_id': short_id,
    }
    save_meta(meta)
    restart_frontend()
    return build_uri(host, inbound['port'], client_id, params, name, short_id)


def delete_client(client_id):
    cfg = load_config()
    meta = load_meta()
    inbound = frontend_inbound(cfg)
    before = len(inbound['settings'].get('clients', []))
    inbound['settings']['clients'] = [c for c in inbound['settings'].get('clients', []) if c.get('id') != client_id]
    if len(inbound['settings']['clients']) == before:
        return False
    save_config(cfg)
    meta.get('clients', {}).pop(client_id, None)
    save_meta(meta)
    restart_frontend()
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = 'XrayAdmin/0.1'

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

    def _redirect(self, location):
        self.send_response(303)
        self.send_header('Location', location)
        self.end_headers()

    def _html(self, body, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body.encode())

    def _png(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.end_headers()
        self.wfile.write(data)

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
        if parsed.path != '/':
            return self._html('not found', 404)
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host', '').split(':')[0] or '127.0.0.1'
        cfg = load_config()
        meta = load_meta()
        params = frontend_params(cfg)
        clients = client_list(cfg, meta)
        cards = []
        for c in clients:
            uri = build_uri(host, params['port'], c['id'], params, c['name'], c['short_id'])
            cards.append(f"""
<tr>
  <td>{html.escape(c['name'])}</td>
  <td><code>{html.escape(c['id'])}</code></td>
  <td><code>{html.escape(c['short_id'])}</code></td>
  <td><a href=\"{html.escape(uri)}\">URI</a></td>
  <td><a href=\"/qr?uri={urllib.parse.quote(uri, safe='')}\" target=\"_blank\">QR</a></td>
  <td>
    <form method=\"post\" action=\"/delete\" onsubmit=\"return confirm('Удалить клиента?')\"> 
      <input type=\"hidden\" name=\"id\" value=\"{html.escape(c['id'])}\" />
      <button type=\"submit\">Delete</button>
    </form>
  </td>
</tr>
""")
        body = f"""
<!doctype html><html><head><meta charset='utf-8'><title>Xray Admin</title>
<style>
body {{ font-family: sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }}
code {{ font-size: .9rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td,th {{ border: 1px solid #ddd; padding: .5rem; vertical-align: top; }}
form.inline {{ display:inline; }}
.card {{ padding: 1rem; border:1px solid #ddd; margin-bottom:1rem; border-radius: 8px; }}
input[type=text] {{ width: 320px; padding: .4rem; }}
button {{ padding: .4rem .8rem; }}
.small {{ color:#666; font-size:.9rem; }}
</style></head><body>
<h1>Xray Admin</h1>
<div class='card'>
  <b>Frontend service:</b> {html.escape(service_status(SERVICE_NAME))}<br>
  <b>Relay reachable:</b> {'yes' if relay_reachable() else 'no'} ({html.escape(EGRESS_HOST)}:{EGRESS_PORT})<br>
  <b>Client entry:</b> <code>{html.escape(host)}:{params['port']}</code><br>
  <b>Public key:</b> <code>{html.escape(params['public_key'])}</code><br>
  <b>SNI:</b> <code>{html.escape(params['server_names'][0] if params['server_names'] else '')}</code>
</div>
<div class='card'>
  <form method='post' action='/create'>
    <label>Client name</label><br>
    <input type='text' name='name' placeholder='{DEFAULT_LABEL}' required />
    <button type='submit'>Create client</button>
  </form>
</div>
<table>
<thead><tr><th>Name</th><th>UUID</th><th>Short ID</th><th>URI</th><th>QR</th><th>Action</th></tr></thead>
<tbody>
{''.join(cards) or '<tr><td colspan="6">No clients</td></tr>'}
</tbody></table>
</body></html>
"""
        self._html(body)

    def do_POST(self):
        if not self._authorized():
            return self._require_auth()
        length = int(self.headers.get('Content-Length', '0'))
        data = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if self.path == '/create':
            name = (data.get('name', [''])[0] or DEFAULT_LABEL).strip()
            host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host', '').split(':')[0] or '127.0.0.1'
            create_client(name, host)
            return self._redirect('/')
        if self.path == '/delete':
            delete_client((data.get('id', [''])[0]).strip())
            return self._redirect('/')
        return self._html('not found', 404)


def main():
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f'Listening on {BIND}:{PORT}', flush=True)
    httpd.serve_forever()


if __name__ == '__main__':
    main()
