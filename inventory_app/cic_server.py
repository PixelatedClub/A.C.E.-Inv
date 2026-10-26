"""Explicitly started, expiring local-network phone intake. No remote admin routes."""
from collections import defaultdict,deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hmac,json,secrets,socket,ssl,threading,time,uuid
from urllib.parse import urlsplit
from .cic_phone import PHONE_HTML


def local_addresses():
    try:return sorted({ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if ':' not in ip and not ip.startswith('127.')})
    except OSError:return []


class CicSession:
    def __init__(self,service,*,host='127.0.0.1',port=0,advertise_host='127.0.0.1',hours=2,certfile='',keyfile=''):
        if not 0<hours<=8:raise ValueError('Session duration must be 1 to 8 hours.')
        socket.inet_aton(advertise_host)
        self.service=service;self.token=secrets.token_urlsafe(32);self.code=f'{secrets.randbelow(1000000):06d}';self.session_id=str(uuid.uuid4())
        self.joins=defaultdict(deque)
        self.expires=time.monotonic()+hours*3600;self.events=deque();self.lock=threading.Lock();self.rate=defaultdict(deque)
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass  # No names, tokens or URLs in HTTP logs.
            def _reply(self,status,data,kind='application/json',filename=''):
                if kind=='application/json':data=json.dumps(data).encode()
                elif isinstance(data,str):data=data.encode()
                self.send_response(status);self.send_header('Content-Type',kind)
                self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
                if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
                self.end_headers();self.wfile.write(data)
            def _guard(self):
                if time.monotonic()>outer.expires:self._reply(410,{'error':'This session has expired. Ask staff for a new link.'});return False
                host=self.headers.get('Host','')
                if host not in outer.allowed_hosts:self._reply(403,{'error':'Invalid host.'});return False
                origin=self.headers.get('Origin')
                if origin and origin!=outer.scheme+'://'+host:self._reply(403,{'error':'Cross-origin requests are not allowed.'});return False
                if self.headers.get('Sec-Fetch-Site')=='cross-site' and not (self.command=='GET' and urlsplit(self.path).path in ('/','/det005','/det005/')):
                    self._reply(403,{'error':'Cross-site request rejected.'});return False
                with outer.lock:
                    key=self.client_address[0];q=outer.rate[key];stamp=time.monotonic()
                    while q and q[0]<stamp-60:q.popleft()
                    if len(q)>=90:self._reply(429,{'error':'Too many requests. Please wait a minute.'});return False
                    q.append(stamp)
                return True
            def _token(self):
                value=self.headers.get('Authorization','').removeprefix('Bearer ')
                return value if value.isascii() and len(value)<=100 else ''
            def _session(self):
                if not hmac.compare_digest(self._token(),outer.token):self._reply(401,{'error':'Invalid session link. Ask ACE staff for the current link.'});return False
                return True
            def do_GET(self):
                if not self._guard():return
                path=urlsplit(self.path).path
                try:
                    if path in ('/','/det005','/det005/'):self._reply(200,PHONE_HTML,'text/html; charset=utf-8');return
                    if path=='/api/catalog':
                        if self._session():self._reply(200,outer.service.cic_catalog())
                        return
                    if path=='/api/questions':
                        from .cic_questions import QUESTIONS
                        if self._session():self._reply(200,[{'id':q[0],'family':q[1],'label':q[2]} for q in QUESTIONS])
                        return
                    parts=path.split('/')
                    if len(parts) in (4,5) and parts[1:3]==['api','cards']:
                        card_id=parts[3];card=outer.service.cic_receipt(card_id,self._token())
                        if len(parts)==4:self._reply(200,card);return
                        if parts[4]=='wings':file=outer.service.export_cic_wings(card_id);mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        elif parts[4]=='copy':file=outer.service.export_cic_copy(card_id);mime='text/html; charset=utf-8'
                        else:self._reply(404,{'error':'Not found.'});return
                        self._reply(200,file.read_bytes(),mime,file.name);return
                    self._reply(404,{'error':'Not found.'})
                except Exception as error:self._error(error)
            def do_POST(self):
                if not self._guard():return
                path=urlsplit(self.path).path
                if path not in ('/api/cards','/api/join'):self._reply(404,{'error':'Not found.'});return
                if path!='/api/join' and not self._session():return
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':self._reply(415,{'error':'Expected JSON.'});return
                try:
                    if self.headers.get('Transfer-Encoding'):raise ValueError('Chunked requests are not accepted.')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=65536:self._reply(413,{'error':'Card exceeds the allowed size.'});return
                    payload=json.loads(self.rfile.read(length))
                    if path=='/api/join':
                        with outer.lock:
                            stamp=time.monotonic();q=outer.joins[self.client_address[0]]
                            while q and q[0]<stamp-60:q.popleft()
                            if len(q)>=10:self._reply(429,{'error':'Too many join attempts. Wait one minute.'});return
                            q.append(stamp)
                        if not isinstance(payload,dict) or not hmac.compare_digest(str(payload.get('code','')),outer.code):self._reply(401,{'error':'Incorrect session code.'});return
                        self._reply(200,{'token':outer.token});return
                    card=outer.service.submit_cic(payload,session_id=outer.session_id)
                    with outer.lock:outer.events.append({'card_id':card['card_id'],'status':card['status']})
                    self._reply(201,{'card_id':card['card_id'],'status':card['status']})
                except Exception as error:self._error(error)
            def _error(self,error):
                from .services import InventoryError
                if isinstance(error,InventoryError):self._reply(400,{'error':str(error)})
                elif isinstance(error,(ValueError,TypeError,UnicodeError)):self._reply(400,{'error':'Invalid card data.'})
                else:self._reply(500,{'error':'ACE could not process this card. Ask staff to check the host.'})
            def setup(self):
                super().setup();self.connection.settimeout(10)
        class Server(ThreadingHTTPServer):
            daemon_threads=True
            request_queue_size=20
            slots=threading.BoundedSemaphore(16)
            def process_request(self,request,address):
                if not self.slots.acquire(blocking=False):request.close();return
                try:super().process_request(request,address)
                except Exception:self.slots.release();raise
            def process_request_thread(self,request,address):
                try:super().process_request_thread(request,address)
                finally:self.slots.release()
        self.httpd=Server((host,port),Handler)
        self.scheme='http'
        try:
            if certfile or keyfile:
                if not certfile or not keyfile:raise ValueError('Select both TLS certificate and key.')
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(certfile,keyfile);self.httpd.socket=context.wrap_socket(self.httpd.socket,server_side=True);self.scheme='https'
        except Exception:self.httpd.server_close();raise
        port=self.httpd.server_port
        self.allowed_hosts={f'{advertise_host}:{port}',f'127.0.0.1:{port}',f'localhost:{port}'}
        self.url=f'{self.scheme}://{advertise_host}:{port}/det005#{self.token}'
        self.join_url=f'{self.scheme}://{advertise_host}:{port}/det005'
        self.thread=threading.Thread(target=self.httpd.serve_forever,name='ACE CIC phone intake',daemon=True);self.thread.start()
    def notifications(self):
        with self.lock:events=list(self.events);self.events.clear()
        return events
    def stop(self):
        self.expires=0;self.httpd.shutdown();self.httpd.server_close();self.thread.join(timeout=3)
