"""Loopback-only development API. Does not accept local A.C.E. admin codes."""
import argparse
import hashlib
import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .store import Problem, Store

DEFAULT_DATA = Path(__file__).resolve().parent.parent / 'beta_data'


def make_server(store, accounts, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass  # Never write tokens or request payloads to console logs.

        def respond(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(body)

        def dispatch(self, write=False):
            try:
                if self.headers.get('Origin'):
                    raise Problem(403,'Browser requests are disabled for this development API.')
                token = self.headers.get('Authorization','').removeprefix('Bearer ')
                digest = hashlib.sha256(token.encode()).hexdigest()
                account = next((a for a in accounts if hmac.compare_digest(a['hash'],digest)),None)
                if not account:
                    raise Problem(401,'Valid beta credentials are required.')
                url = urlsplit(self.path)
                if write:
                    if url.path != '/v1/operations':
                        raise Problem(404,'Endpoint not found.')
                    try:
                        length = int(self.headers.get('Content-Length','0'))
                    except ValueError:
                        raise Problem(400,'Invalid request length.')
                    if not 0 < length <= 32768:
                        raise Problem(413,'Request must be between 1 and 32768 bytes.')
                    try:
                        payload = json.loads(self.rfile.read(length))
                    except (ValueError,UnicodeError):
                        raise Problem(400,'Invalid JSON.')
                    if not isinstance(payload,dict):
                        raise Problem(400,'Expected a JSON object.')
                    result = store.mutate(account['name'],account['role'],payload)
                elif url.path == '/v1/state':
                    result = store.snapshot()
                    result['account'] = {'name':account['name'],'role':account['role']}
                elif url.path == '/v1/audit':
                    q = parse_qs(url.query)
                    result = store.history(q.get('start',[''])[0],q.get('end',[''])[0])
                else:
                    raise Problem(404,'Endpoint not found.')
                self.respond(200,result)
            except Problem as exc:
                self.respond(exc.status,{'error':str(exc)})
            except Exception:
                self.respond(500,{'error':'Server operation failed; no successful save is confirmed. Retry the same operation.'})

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch(True)

    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads = True
    return server


def initialize(directory):
    directory.mkdir(parents=True,exist_ok=True)
    dbfile = directory/'beta.sqlite3'
    credentials = directory/'accounts.json'
    if dbfile.exists() or credentials.exists():
        raise SystemExit('Beta already initialized. Existing data was preserved.')
    accounts = []
    for name,role in [('Test Williams','operator'),('Test Operator Two','operator'),('Test Viewer','viewer')]:
        token = secrets.token_urlsafe(32)
        accounts.append(dict(name=name,role=role,hash=hashlib.sha256(token.encode()).hexdigest()))
        profile = name.lower().replace(' ','_')+'.json'
        (directory/profile).write_text(json.dumps(dict(url='http://127.0.0.1:8765',token=token),indent=2))
    credentials.write_text(json.dumps(accounts,indent=2))
    store = Store(dbfile)
    for action,data in [
        ('save_item',dict(name='TEST Blues service coat',category='Blues',size='40 R',wings='LOCAL-TEST-001',total=10)),
        ('save_item',dict(name='TEST OCP patrol cap',category='OCP',size='7 1/8',wings='LOCAL-TEST-002',total=8)),
        ('save_cadet',dict(name='Example Cadet',email='example@example.invalid')),
    ]:
        store.mutate('Synthetic setup','operator',dict(operation=secrets.token_hex(16),
            revision=store.snapshot()['revision'],action=action,data=data))
    store.backup(directory/'initial-backup.sqlite3')
    print('Created isolated synthetic beta data and three local test profiles.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--init',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    if args.init:
        initialize(args.data)
        return
    credentials = args.data/'accounts.json'
    if not credentials.exists():
        raise SystemExit('Run python -m shared_beta.server --init first.')
    store = Store(args.data/'beta.sqlite3')
    store.backup(args.data/'startup-backup.sqlite3')
    server = make_server(store,json.loads(credentials.read_text()),args.port)
    print(f'A.C.E. Shared Beta 0.2.0: http://127.0.0.1:{server.server_port} (synthetic testing only)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
