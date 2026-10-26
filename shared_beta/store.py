"""Transactional shared state with optimistic concurrency and durable retry receipts."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path


class Problem(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def required(data, key, limit=200):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Problem(400, f"{key} is required (maximum {limit} characters).")
    return value.strip()


def number(data, key, minimum=0):
    value = data.get(key)
    if type(value) is not int or not minimum <= value <= 1000000:
        raise Problem(400, f"{key} must be an integer between {minimum} and 1000000.")
    return value


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS beta_meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO beta_meta VALUES (1,0);
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                    size TEXT NOT NULL, wings TEXT NOT NULL, total INTEGER NOT NULL CHECK(total>=0),
                    UNIQUE(name COLLATE NOCASE,category COLLATE NOCASE,size COLLATE NOCASE));
                CREATE TABLE IF NOT EXISTS cadets (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE);
                CREATE TABLE IF NOT EXISTS fittings (
                    cadet INTEGER NOT NULL REFERENCES cadets(id), category TEXT NOT NULL COLLATE NOCASE,
                    size TEXT NOT NULL, PRIMARY KEY(cadet,category));
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY, cadet INTEGER NOT NULL REFERENCES cadets(id),
                    item INTEGER NOT NULL REFERENCES items(id), quantity INTEGER NOT NULL CHECK(quantity>0),
                    state TEXT NOT NULL CHECK(state IN ('checkout','loan','returned','acquired','purchased')),
                    due TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS audit (
                    revision INTEGER PRIMARY KEY, time TEXT NOT NULL, actor TEXT NOT NULL,
                    action TEXT NOT NULL, operation TEXT NOT NULL UNIQUE,
                    before_json TEXT NOT NULL, after_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (
                    operation TEXT PRIMARY KEY, actor TEXT NOT NULL, digest TEXT NOT NULL, response TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS legacy_barcodes (item INTEGER PRIMARY KEY REFERENCES items(id), barcode TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS legacy_archive (table_name TEXT NOT NULL, row_number INTEGER NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(table_name,row_number));
            ''')
            if 'status' not in {r[1] for r in db.execute('PRAGMA table_info(items)')}:
                db.execute("ALTER TABLE items ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def _state(self, db):
        items = [dict(row) for row in db.execute('''SELECT i.*, CASE WHEN i.status IN ('retired','lost') THEN 0 ELSE i.total-COALESCE(
            (SELECT SUM(quantity) FROM issues WHERE item=i.id AND state IN ('loan','checkout')),0)
            END AS available FROM items i ORDER BY category,name,size''')]
        for item in items:
            legacy=db.execute('SELECT barcode FROM legacy_barcodes WHERE item=?',(item['id'],)).fetchone()
            item['barcode'] = legacy[0] if legacy else f"B{item['id']:07d}"
        issues = [dict(row) for row in db.execute('''SELECT x.*, c.name AS cadet_name,
            i.name AS item_name, i.size AS item_size FROM issues x JOIN cadets c ON c.id=x.cadet
            JOIN items i ON i.id=x.item ORDER BY x.id DESC''')]
        for issue in issues:
            issue['overdue'] = issue['state'] == 'loan' and issue['due'] < date.today().isoformat()
        return dict(revision=db.execute('SELECT revision FROM beta_meta').fetchone()[0],
                    items=items, cadets=[dict(r) for r in db.execute('SELECT * FROM cadets ORDER BY name')],
                    fittings=[dict(r) for r in db.execute('SELECT * FROM fittings ORDER BY cadet,category')],
                    issues=issues)

    def snapshot(self):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN')
            return self._state(db)

    def history(self, start='', end=''):
        for value in (start, end):
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    raise Problem(400, 'Report dates must be YYYY-MM-DD.')
        if start and end and start > end:
            raise Problem(400, 'Start date must precede end date.')
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute('''SELECT * FROM audit
                WHERE (?='' OR substr(time,1,10)>=?) AND (?='' OR substr(time,1,10)<=?) ORDER BY revision''',
                (start,start,end,end))]

    def mutate(self, actor, role, request):
        if role != 'operator':
            raise Problem(403, 'This account has read-only access.')
        if request.get('expected_actor',actor)!=actor:
            raise Problem(403,'Pending request belongs to another account. Sign in as the original operator.')
        operation = required(request, 'operation', 100)
        action = required(request, 'action', 40)
        revision = number(request, 'revision')
        data = request.get('data')
        if not isinstance(data, dict):
            raise Problem(400, 'data must be an object.')
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute('SELECT * FROM receipts WHERE operation=?', (operation,)).fetchone()
            if receipt:
                if receipt['actor'] != actor or receipt['digest'] != digest:
                    raise Problem(409, 'Operation ID already used for a different request.')
                return json.loads(receipt['response'])
            before = self._state(db)
            if before['revision'] != revision:
                raise Problem(409, 'Inventory changed in another session. Refresh and review before submitting again.')
            try:
                self._apply(db, action, data, before)
            except sqlite3.IntegrityError:
                raise Problem(409, 'Duplicate item/email or invalid record reference. Update the existing record.')
            db.execute('UPDATE beta_meta SET revision=revision+1')
            after = self._state(db)
            result = {'revision': after['revision'], 'operation': operation}
            db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?,?)', (
                after['revision'], datetime.now(timezone.utc).isoformat(), actor, action, operation,
                json.dumps(before), json.dumps(after)))
            db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (operation, actor, digest, json.dumps(result)))
            return result

    def _apply(self, db, action, d, state):
        def find(collection, key):
            ident = number(d, key, 1)
            return next((r for r in state[collection] if r['id'] == ident), None)

        if action == 'save_item':
            args = [required(d,'name'), required(d,'category'), required(d,'size'),
                    required(d,'wings'), number(d,'total')]
            if d.get('id'):
                item = find('items','id')
                if not item:
                    raise Problem(404, 'Item not found.')
                issued=sum(r['quantity'] for r in state['issues'] if r['item']==item['id'] and r['state'] in ('loan','checkout'))
                if args[-1] < issued:
                    raise Problem(409, 'Total cannot be less than the number currently issued.')
                db.execute('UPDATE items SET name=?,category=?,size=?,wings=?,total=? WHERE id=?',args+[item['id']])
            else:
                db.execute('INSERT INTO items(name,category,size,wings,total) VALUES(?,?,?,?,?)',args)
        elif action == 'save_cadet':
            email = required(d,'email').casefold()
            if email.count('@') != 1 or any(c.isspace() for c in email) or '.' not in email.split('@')[1]:
                raise Problem(400, 'Enter a valid email address.')
            args = [required(d,'name'),email]
            if d.get('id'):
                cadet = find('cadets','id')
                if not cadet:
                    raise Problem(404,'Cadet not found.')
                db.execute('UPDATE cadets SET name=?,email=? WHERE id=?',args+[cadet['id']])
            else:
                db.execute('INSERT INTO cadets(name,email) VALUES(?,?)',args)
        elif action == 'fit':
            cadet,category,size=number(d,'cadet',1),required(d,'category'),required(d,'size')
            found=db.execute('SELECT cadet FROM fittings WHERE cadet=? AND category=?',(cadet,category)).fetchone()
            if found:
                db.execute('UPDATE fittings SET size=? WHERE cadet=? AND category=?',(size,cadet,category))
            else:
                db.execute('INSERT INTO fittings VALUES(?,?,?)',(cadet,category,size))
        elif action == 'issue':
            item = find('items','item')
            qty = number(d,'quantity',1)
            mode = required(d,'state')
            if mode not in ('loan','checkout'):
                raise Problem(400,'Select loan or checkout.')
            due = required(d,'due',10) if mode == 'loan' else ''
            if due:
                try:
                    if date.fromisoformat(due).isoformat() != due:
                        raise ValueError()
                except ValueError:
                    raise Problem(400,'Loan deadline must be YYYY-MM-DD.')
            if not item or item['available'] < qty:
                raise Problem(409,'Insufficient available inventory.')
            db.execute('INSERT INTO issues(cadet,item,quantity,state,due) VALUES(?,?,?,?,?)',
                       (number(d,'cadet',1),item['id'],qty,mode,due))
        elif action == 'resolve':
            issue = find('issues','id')
            if not issue or issue['state'] not in ('loan','checkout'):
                raise Problem(409,'Select an open loan or checkout.')
            mode = required(d,'state')
            if mode not in ('returned','acquired','purchased','checkout'):
                raise Problem(400,'Invalid resolution.')
            if mode == 'checkout' and issue['state'] != 'loan':
                raise Problem(409,'Only a loan can be converted to checkout.')
            qty = number(d,'quantity',1)
            if qty > issue['quantity']:
                raise Problem(400,'Quantity exceeds the open issue.')
            if qty == issue['quantity']:
                db.execute('UPDATE issues SET state=?,due=? WHERE id=?',(mode,'',issue['id']))
            else:
                db.execute('UPDATE issues SET quantity=quantity-? WHERE id=?',(qty,issue['id']))
                db.execute('INSERT INTO issues(cadet,item,quantity,state) VALUES(?,?,?,?)',
                           (issue['cadet'],issue['item'],qty,mode))
            if mode in ('acquired','purchased'):
                db.execute('UPDATE items SET total=total-? WHERE id=?',(qty,issue['item']))
        else:
            raise Problem(400,'Unknown action.')

    def backup(self, destination):
        with closing(self.connect()) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup verification failed.')
