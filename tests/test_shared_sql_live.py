"""Optional acceptance test against an EMPTY university-approved TEST SQL database.

Set ACE_TEST_SQL_ODBC to opt in. This creates the beta schema and leaves synthetic
records for inspection; it never drops existing tables or truncates any data.
"""
import os
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from shared_beta.sql_store import SQLStore,azure_engine
from shared_beta.store import Problem


@unittest.skipUnless(os.environ.get('ACE_TEST_SQL_ODBC'),'No approved test Azure SQL connection supplied')
class AzureSQLAcceptance(unittest.TestCase):
    def test_managed_identity_schema_writes_retry_and_concurrency(self):
        store=SQLStore(azure_engine(os.environ['ACE_TEST_SQL_ODBC']))
        store.initialize_schema()
        state=store.snapshot()
        self.assertFalse(state['items'] or state['cadets'],'Use an EMPTY disposable test database; existing records were preserved.')
        def request(action,data):return dict(operation=str(uuid4()),revision=store.snapshot()['revision'],action=action,data=data)
        store.mutate('Acceptance test','operator',request('save_item',dict(name='TEST Coat',category='TEST',size='M',wings='LOCAL-TEST',total=5)))
        store.mutate('Acceptance test','operator',request('save_cadet',dict(name='TEST Cadet',email='test@example.invalid')))
        state=store.snapshot()
        payload=request('issue',dict(item=state['items'][0]['id'],cadet=state['cadets'][0]['id'],quantity=4,state='loan',due='2030-01-01'))
        other=dict(payload,operation=str(uuid4()))
        def run(p):
            try:return store.mutate('Acceptance test','operator',p)
            except Problem as exc:return exc.status
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,[payload,other]))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertIn(409,results)
        winner=payload if isinstance(results[0],dict) else other
        store.mutate('Acceptance test','operator',winner)
        state=store.snapshot();self.assertEqual(state['items'][0]['available'],1)
        self.assertEqual(len(store.history()),3)
        store.engine.dispose()
