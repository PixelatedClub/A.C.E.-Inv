import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from shared_beta.identity import EntraValidator,validate_profile
from shared_beta.hosted import create_app
from shared_beta.store import Store,Problem
from shared_beta.migrate import inspect,migrate
from shared_beta.secure_files import protect,read_pending,write_pending
from shared_beta.sharepoint import upload_report


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.tenant=str(uuid4());self.api=str(uuid4());self.client=str(uuid4())
        self.validator=EntraValidator(self.tenant,self.api,self.client)
        self.validator.keys=SimpleNamespace(get_signing_key_from_jwt=lambda _:SimpleNamespace(key=self.key.public_key()))
        now=int(time.time())
        self.claims=dict(exp=now+300,iat=now,nbf=now-1,aud=self.api,iss=f'https://login.microsoftonline.com/{self.tenant}/v2.0',
                         tid=self.tenant,oid=str(uuid4()),azp=self.client,ver='2.0',scp='access_as_user',roles=['ACE.Operator'])

    def token(self,**changes):return jwt.encode(dict(self.claims,**changes),self.key,algorithm='RS256')

    def test_valid_operator_and_viewer(self):
        self.assertEqual(self.validator.authenticate(self.token())['role'],'operator')
        self.assertEqual(self.validator.authenticate(self.token(roles=['ACE.Viewer']))['role'],'viewer')

    def test_wrong_token_claims_and_signature(self):
        for changes in [dict(exp=int(time.time())-100),dict(aud=str(uuid4())),dict(tid=str(uuid4())),dict(azp=str(uuid4())),
                        dict(iss='https://attacker.invalid'),dict(ver='1.0'),dict(scp=''),dict(roles=[]),dict(oid='bad')]:
            with self.subTest(changes=changes),self.assertRaises(Problem):self.validator.authenticate(self.token(**changes))
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        with self.assertRaises(Problem):self.validator.authenticate(jwt.encode(self.claims,other,algorithm='RS256'))
        with self.assertRaises(Problem):self.validator.authenticate(jwt.encode(self.claims,key='',algorithm='none'))

    def test_profile_rejects_insecure_origins(self):
        base=dict(auth='entra',url='https://ace.example.invalid',tenant_id=self.tenant,client_id=self.client,api_client_id=self.api)
        validate_profile(base)
        for url in ['http://ace.example.invalid','https://user:secret@ace.example.invalid','https://ace.example.invalid?x=1']:
            with self.assertRaises(ValueError):validate_profile(dict(base,url=url))
        with self.assertRaises(ValueError):validate_profile(dict(base,token='secret'))
        with self.assertRaises(ValueError):validate_profile(dict(auth='local',url='https://ace.example.invalid',token='test'))

    def test_hosted_api_rejects_wrong_tokens_and_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            with TestClient(create_app(store,self.validator)) as client:
                self.assertEqual(client.get('/v1/state').status_code,401)
                self.assertEqual(client.get('/v1/state',headers={'Authorization':'Bearer local-test-token'}).status_code,401)
                headers={'Authorization':'Bearer '+self.token()}
                actor=client.get('/v1/state',headers=headers).json()['account']['name']
                payload=dict(operation=str(uuid4()),revision=0,action='save_cadet',expected_actor=actor,data=dict(name='Test',email='test@example.invalid'))
                response=client.post('/v1/operations',headers=headers,json=payload)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(client.post('/v1/operations',headers=headers,json=payload).json(),response.json())
                viewer={'Authorization':'Bearer '+self.token(roles=['ACE.Viewer'])}
                self.assertEqual(client.post('/v1/operations',headers=viewer,json=payload).status_code,403)
                self.assertEqual(client.post('/v1/operations',headers=headers,content=b'x'*32769).status_code,413)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'legacy.db'
        with closing(sqlite3.connect(self.source)) as db,db:
            db.executescript('''
                CREATE TABLE items(barcode_id TEXT,wings_item_no TEXT,item_name TEXT,category TEXT,variant TEXT,item_type TEXT,
                status TEXT,total_quantity INT,available_quantity INT);
                INSERT INTO items VALUES('A0000042','W-001','Coat','Blues','40 R','Service coat','Available',5,4);
                CREATE TABLE cadets(cadet_id INT,full_name TEXT,email TEXT);
                INSERT INTO cadets VALUES(3,'Test Cadet','test@example.invalid');
                CREATE TABLE transactions(transaction_id INT,barcode_id TEXT,cadet_id INT,disposition TEXT,return_time TEXT,loan_due_date TEXT);
                INSERT INTO transactions VALUES(10,'A0000042',3,'',NULL,'2026-11-18');
                CREATE TABLE cadet_size_entries(cadet_id INT,size_label TEXT,size_value TEXT,category TEXT);
                INSERT INTO cadet_size_entries VALUES(3,'Coat','40 R','Blues');
                INSERT INTO cadet_size_entries VALUES(3,'Pants','32 R','Blues');
                CREATE TABLE admin_codes(code_value TEXT);
                INSERT INTO admin_codes VALUES('NEVER_COPY_THIS');
            ''')

    def tearDown(self):self.temp.cleanup()

    def test_preview_import_preserves_inventory_barcodes_and_history(self):
        before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        report=inspect(self.source)[0]
        self.assertTrue(report['ready'],report)
        target=self.root/'import.db';migrate(self.source,target)
        state=Store(target).snapshot()
        self.assertEqual(state['items'][0]['barcode'],'A0000042')
        self.assertEqual(state['items'][0]['available'],4)
        self.assertEqual(state['issues'][0]['id'],10)
        self.assertEqual(len(state['fittings']),2)
        self.assertEqual(state['cadets'][0]['id'],3)
        self.assertEqual(before,hashlib.sha256(self.source.read_bytes()).hexdigest())
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM legacy_archive WHERE table_name='admin_codes'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM legacy_archive WHERE table_name='transactions'").fetchone()[0],1)
        with self.assertRaises(ValueError):migrate(self.source,target)

    def test_mismatch_blocks_without_creating_destination(self):
        with closing(sqlite3.connect(self.source)) as db,db:db.execute('UPDATE items SET available_quantity=5')
        self.assertFalse(inspect(self.source)[0]['ready'])
        target=self.root/'import.db'
        with self.assertRaises(ValueError):migrate(self.source,target)
        self.assertFalse(target.exists())

    def test_retired_stock_keeps_zero_availability(self):
        with closing(sqlite3.connect(self.source)) as db,db:
            db.execute("INSERT INTO items VALUES('A0000043','W-002','Old polo','Polo','M','Shirt','Retired',12,0)")
        target=self.root/'import.db';report=migrate(self.source,target)
        self.assertTrue(report['ready'])
        store=Store(target);row=next(r for r in store.snapshot()['items'] if r['barcode']=='A0000043')
        self.assertEqual((row['total'],row['available'],row['status']),(12,0,'retired'))
        request=dict(operation=str(uuid4()),revision=1,action='issue',data=dict(cadet=3,item=row['id'],quantity=1,state='checkout'))
        with self.assertRaises(Problem):store.mutate('Test','operator',request)


class ProtectedFilesTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows user-bound encryption')
    def test_dpapi_round_trip_and_tamper(self):
        data=b'synthetic pending operation'
        encrypted=protect(data)
        self.assertNotIn(data,encrypted)
        self.assertEqual(protect(encrypted,True),data)
        with self.assertRaises(OSError):protect(encrypted[:-10],True)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pending.dpapi';payload={'operation':'test','revision':1}
            write_pending(path,payload,True)
            self.assertEqual(read_pending(path,True),payload)

    def test_sharepoint_upload_uses_selected_folder_and_new_name(self):
        from io import BytesIO
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'report.csv';path.write_bytes(b'TEST')
            profile={'sharepoint':{'drive_id':'approved-drive','folder_id':'approved-folder'}}
            with patch('shared_beta.sharepoint.build_opener') as opener:
                opener.return_value.open.return_value=BytesIO(json.dumps({'size':4,'name':'report'}).encode())
                result=upload_report(profile,path,'test-token')
                req=opener.return_value.open.call_args.args[0]
                self.assertIn('/drives/approved-drive/items/approved-folder:/report-',req.full_url)
                self.assertEqual(req.method,'PUT');self.assertEqual(result['size'],4)
            with self.assertRaises(ValueError):upload_report({},path,'token')


if __name__=='__main__':unittest.main()
