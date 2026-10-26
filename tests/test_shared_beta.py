import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from shared_beta.store import Store, Problem
from shared_beta.server import make_server


class SharedBetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3')
        self.save('save_item',dict(name='Coat',category='Blues',size='40 R',wings='TEST-1',total=5))
        self.save('save_cadet',dict(name='Example',email='example@example.invalid'))

    def tearDown(self):self.tmp.cleanup()

    def request(self,action,data):
        return dict(operation=str(uuid.uuid4()),revision=self.store.snapshot()['revision'],action=action,data=data)

    def save(self,action,data):return self.store.mutate('Operator','operator',self.request(action,data))

    def test_retry_conflict_and_payload_reuse(self):
        req=self.request('fit',dict(cadet=1,category='Coat',size='40 R'))
        first=self.store.mutate('Operator','operator',req)
        self.assertEqual(first,self.store.mutate('Operator','operator',req))
        self.assertEqual(len(self.store.history()),3)
        with self.assertRaises(Problem):
            self.store.mutate('Other','operator',req)
        with self.assertRaises(Problem):
            self.store.mutate('Operator','operator',dict(req,operation=str(uuid.uuid4())))
        self.assertEqual(len(self.store.snapshot()['fittings']),1)

    def test_concurrent_requests_only_one_wins(self):
        a=self.request('issue',dict(cadet=1,item=1,quantity=4,state='checkout'))
        b=dict(a,operation=str(uuid.uuid4()))
        def attempt(req):
            try:self.store.mutate('Operator','operator',req);return 200
            except Problem as exc:return exc.status
        with ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(attempt,[a,b])),[200,409])
        self.assertEqual(self.store.snapshot()['items'][0]['available'],1)

    def test_loan_partial_return_acquire_and_convert(self):
        self.save('issue',dict(cadet=1,item=1,quantity=4,state='loan',due='2020-01-01'))
        self.assertTrue(self.store.snapshot()['issues'][0]['overdue'])
        self.save('resolve',dict(id=1,state='returned',quantity=1))
        self.save('resolve',dict(id=1,state='acquired',quantity=1))
        self.save('resolve',dict(id=1,state='checkout',quantity=2))
        state=self.store.snapshot()
        self.assertEqual((state['items'][0]['total'],state['items'][0]['available']),(4,2))
        self.assertFalse(any(x['overdue'] for x in state['issues']))
        self.save('resolve',dict(id=1,state='returned',quantity=2))
        self.assertEqual(self.store.snapshot()['items'][0]['available'],4)

    def test_rollback_invalid_reference_and_duplicate(self):
        before=self.store.snapshot()
        with self.assertRaises(Problem):self.save('issue',dict(cadet=999,item=1,quantity=2,state='checkout'))
        with self.assertRaises(Problem):self.save('save_cadet',dict(name='Other',email='EXAMPLE@example.invalid'))
        with self.assertRaises(Problem):self.save('save_item',dict(name='coat',category='blues',size='40 r',wings='OTHER',total=1))
        self.assertEqual(before,self.store.snapshot())

    def test_total_cannot_drop_below_issued(self):
        self.save('issue',dict(cadet=1,item=1,quantity=4,state='checkout'))
        with self.assertRaises(Problem):self.save('save_item',dict(id=1,name='Coat',category='Blues',size='40 R',wings='TEST-1',total=3))

    def test_viewer_and_validation(self):
        with self.assertRaises(Problem):self.store.mutate('Viewer','viewer',self.request('fit',dict(cadet=1,category='Coat',size='M')))
        for due in ['bad-date','2020-99-01']:
            with self.assertRaises(Problem):self.save('issue',dict(cadet=1,item=1,quantity=1,state='loan',due=due))
        for qty in [-1,0,True,1.5,6]:
            with self.assertRaises(Problem):self.save('issue',dict(cadet=1,item=1,quantity=qty,state='checkout'))
        with self.assertRaises(Problem):self.store.history('2026-10-01','2026-01-01')
        self.assertEqual(self.store.history('2000-01-01','2000-01-02'),[])

    def test_backup_restores_state_and_retry_receipts(self):
        req=self.request('fit',dict(cadet=1,category='Coat',size='M'))
        result=self.store.mutate('Operator','operator',req)
        target=Path(self.tmp.name)/'restore.sqlite3'
        self.store.backup(target)
        restored=Store(target)
        self.assertEqual(restored.snapshot(),self.store.snapshot())
        self.assertEqual(restored.mutate('Operator','operator',req),result)

    def test_http_auth_roles_origin_and_save(self):
        accounts=[dict(name='Operator',role='operator',hash=hashlib.sha256(b'secret').hexdigest()),
                  dict(name='Viewer',role='viewer',hash=hashlib.sha256(b'view').hexdigest())]
        server=make_server(self.store,accounts,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def call(path,token='',data=None,origin=None):
            headers={'Authorization':'Bearer '+token}
            if origin:headers['Origin']=origin
            req=Request(base+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
            with urlopen(req,timeout=3) as response:return json.load(response)
        try:
            with self.assertRaises(HTTPError) as error:call('/v1/state')
            self.assertEqual(error.exception.code,401)
            self.assertEqual(call('/v1/state','view')['account']['role'],'viewer')
            payload=self.request('fit',dict(cadet=1,category='Cap',size='7'))
            with self.assertRaises(HTTPError) as error:call('/v1/operations','view',payload)
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(HTTPError):call('/v1/state','secret',origin='https://example.com')
            result=call('/v1/operations','secret',payload)
            self.assertEqual(call('/v1/operations','secret',payload),result)
            self.assertEqual(call('/v1/state','secret')['fittings'][0]['size'],'7')
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
