import gc,json,secrets,tempfile,threading,unittest,uuid,zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit
from inventory_app.config import AppSettings
from inventory_app.services import InventoryService,InventoryError
from inventory_app.cic_server import CicSession
from inventory_app.cic import item_key

ADMIN={'role':'CADRE','display_name':'CADRE','admin_id':None}


class CicTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.service=InventoryService(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=10000))
  self.cat=self.service.cic_catalog()[0]
 def tearDown(self):
  self.service=None;gc.collect();self.temp.cleanup()
 def payload(self,qty=2,**overrides):
  value={'name':'Example, Jane','email':'jane@example.invalid','request_id':str(uuid.uuid4()),'receipt_token':secrets.token_urlsafe(32),
   'lines':[{'item_no':self.cat['item_no'],'name':self.cat['name'],'size':self.cat['size'],'quantity':qty}]}
  value.update(overrides);return value
 def submit(self,p=None):return self.service.submit_cic(p or self.payload(),session_id='test-session')
 def approve(self,card,**identity):
  if not identity:identity={'create_new':True}
  view=self.service.preview_cic(card['card_id'],**identity)
  return self.service.approve_cic(card['card_id'],approved_by=ADMIN,review_token=view['review_token'],**identity)
 def operational(self):
  with self.service.database.connect() as c:
   return {t:[tuple(x) for x in c.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in ('items','transactions','cadets','inventory_changes')}
 def test_intake_does_not_mutate_operational_data(self):
  before=self.operational();card=self.submit()
  self.assertEqual(card['status'],'Pending');self.assertEqual(before,self.operational())
  self.assertNotIn('receipt_hash',card)
 def test_unknown_and_misspelled_lines_held(self):
  for field,value in [('item_no','NO-SUCH-ID'),('name','Typpo'),('size','Wrong')]:
   p=self.payload();p['lines'][0][field]=value;card=self.submit(p)
   self.assertEqual(card['status'],'Held')
   with self.assertRaises(InventoryError):self.approve(card)
   with self.assertRaises(InventoryError):self.service.export_cic_wings(card['card_id'])
 def test_map_hold_then_approve(self):
  p=self.payload();p['lines'][0]['name']='Mispelled';card=self.submit(p);line=card['lines'][0]
  self.service.map_cic_line(card['card_id'],line['line_id'],self.cat['item_no'],approved_by=ADMIN)
  self.assertEqual(self.service.get_cic(card['card_id'])['status'],'Pending')
  approved=self.approve(card);self.assertEqual(approved['status'],'Approved')
 def test_new_profile_stock_and_checkouts_created_together(self):
  result=self.approve(self.submit());self.assertIsNotNone(result['cadet_id'])
  with self.service.database.connect() as c:
   item=c.execute('SELECT * FROM items WHERE barcode_id=?',(result['lines'][0]['barcode_id'],)).fetchone()
   self.assertEqual((item['total_quantity'],item['available_quantity']),(2,0))
   self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],2)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM cic_events WHERE action=?',('Approved',)).fetchone()[0],1)
   self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
 def test_existing_stock_stays_available_and_does_not_get_double_issued(self):
  self.service.ensure_catalog_inventory(item_nos=[self.cat['item_no']])
  with self.service.database.connect() as c:
   item=c.execute('SELECT * FROM items').fetchone();bc=item['barcode_id']
   c.execute('UPDATE items SET total_quantity=5,available_quantity=5 WHERE barcode_id=?',(bc,));c.commit()
  first=self.approve(self.submit());cid=first['cadet_id']
  with self.service.database.connect() as c:
   item=c.execute('SELECT * FROM items WHERE barcode_id=?',(bc,)).fetchone();self.assertEqual((item['total_quantity'],item['available_quantity']),(7,5))
  self.approve(self.submit(),cadet_id=cid)
  with self.service.database.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],2)
 def test_name_matches_require_choice_email_duplicate_cannot_create(self):
  cadet=self.service.save_cadet(cadet_name='Example, A, Jane',cadet_email='jane@example.invalid');card=self.submit()
  self.assertEqual(len(self.service.cic_candidates(card['card_id'])),1)
  with self.assertRaises(InventoryError):self.service.preview_cic(card['card_id'])
  with self.assertRaises(InventoryError):self.service.preview_cic(card['card_id'],create_new=True)
  self.approve(card,cadet_id=cadet['cadet_id'])
  self.assertEqual(self.service.list_cadets()[0]['full_name'],'Example, A, Jane')
 def test_same_name_different_email_can_be_confirmed_new_person(self):
  self.service.save_cadet(cadet_name='Example, Jane',cadet_email='different@example.invalid')
  self.approve(self.submit());self.assertEqual(len(self.service.list_cadets()),2)
 def test_returned_items_can_be_reconciled_but_owned_items_are_not_reopened(self):
  first=self.approve(self.submit(qty_payload:=self.payload(2)));bc=first['lines'][0]['barcode_id']
  self.service.return_item(barcode_id=bc,quantity=1,approved_by=ADMIN)
  second=self.approve(self.submit(),cadet_id=first['cadet_id'])
  self.assertEqual(second['lines'][0]['added_quantity'],1)
 def test_purchased_items_stay_purchased_without_new_stock(self):
  card=self.approve(self.submit());cid=card['cadet_id']
  ids=json.loads(card['lines'][0]['transaction_ids'])
  self.service.acquire_checked_out_items(cadet_id=cid,transaction_ids=ids,disposition='Purchased',approved_by=ADMIN)
  before=self.operational();view=self.service.preview_cic(self.submit()['card_id'],cadet_id=cid)
  self.assertEqual(view['plan'][0]['owned'],2);self.assertEqual(view['plan'][0]['add'],0)
  from unittest.mock import patch
  with patch.object(self.service,'_sync_item_state',side_effect=AssertionError('Already recorded ownership must not touch stock')):
   self.service.approve_cic(view['card']['card_id'],cadet_id=cid,approved_by=ADMIN,review_token=view['review_token'])
  self.assertEqual(before,self.operational())
 def test_unbalanced_existing_stock_blocks_reconciliation(self):
  self.service.ensure_catalog_inventory(item_nos=[self.cat['item_no']])
  with self.service.database.connect() as c:c.execute('UPDATE items SET total_quantity=4,available_quantity=0');c.commit()
  card=self.submit()
  with self.assertRaises(InventoryError):self.service.preview_cic(card['card_id'],create_new=True)
 def test_reconciliation_reported_as_recovered_not_new_receipt(self):
  self.approve(self.submit())
  from datetime import date
  report=self.service.get_weekly_activity_report_data(start_date=date.today().isoformat(),end_date=date.today().isoformat())
  self.assertEqual(report['summary']['routine_units_added'],0)
  self.assertEqual(report['summary']['recovered_units'],2)
  self.assertEqual(report['summary']['checkout_transactions'],2)
 def test_approval_replay_and_duplicate_submission_are_safe(self):
  p=self.payload();card=self.submit(p);self.assertEqual(self.submit(p)['card_id'],card['card_id'])
  view=self.service.preview_cic(card['card_id'],create_new=True)
  approved=self.service.approve_cic(card['card_id'],create_new=True,approved_by=ADMIN,review_token=view['review_token'])
  before=self.operational()
  again=self.service.approve_cic(card['card_id'],create_new=True,approved_by=ADMIN,review_token=view['review_token'])
  self.assertEqual(again['card_id'],approved['card_id']);self.assertEqual(before,self.operational())
 def test_duplicate_lines_aggregate_once(self):
  p=self.payload();p['lines']*=2;card=self.approve(self.submit(p))
  self.assertEqual(sum(x['added_quantity'] for x in card['lines']),4)
  path=self.service.export_cic_wings(card['card_id']);self.assertTrue(path.is_file())
 def test_stale_preview_rejected_and_no_partial_writes(self):
  card=self.submit();view=self.service.preview_cic(card['card_id'],create_new=True)
  self.service.save_cadet(cadet_name='Example, Jane',cadet_email='jane@example.invalid')
  before=self.operational()
  with self.assertRaises(InventoryError):self.service.approve_cic(card['card_id'],create_new=True,approved_by=ADMIN,review_token=view['review_token'])
  self.assertEqual(before,self.operational())
 def test_missing_admin_is_rejected(self):
  card=self.submit();view=self.service.preview_cic(card['card_id'],create_new=True)
  with self.assertRaises(InventoryError):self.service.approve_cic(card['card_id'],create_new=True,review_token=view['review_token'])
 def test_receipt_is_private_and_export_blocked_for_local(self):
  p=self.payload();card=self.submit(p)
  with self.assertRaises(InventoryError):self.service.cic_receipt(card['card_id'],'wrong')
  self.assertEqual(self.service.cic_receipt(card['card_id'],p['receipt_token'])['card_id'],card['card_id'])
  with self.service.database.connect() as c:
   c.execute("INSERT INTO wings_catalog(item_no,item_name,size,category,subcategory,is_wings) VALUES('LOCAL-CIC','Local Jacket','M','Outerwear','Jacket',0)");c.commit()
  p=self.payload(lines=[{'item_no':'LOCAL-CIC','name':'Local Jacket','size':'M','quantity':1}]);card=self.approve(self.submit(p))
  with self.assertRaises(InventoryError):self.service.export_cic_wings(card['card_id'])
  self.assertTrue(self.service.export_cic_copy(card['card_id']).exists())
 def test_official_wings_workbook_contains_cadet_and_required_columns(self):
  card=self.approve(self.submit());path=self.service.export_cic_wings(card['card_id'])
  with zipfile.ZipFile(path) as z:
   book=z.read('xl/workbook.xml').decode();sheet=z.read('xl/worksheets/sheet2.xml').decode();cover=z.read('xl/worksheets/sheet1.xml').decode()
  self.assertIn('WINGs Inventory',book);self.assertIn('Qty Issued',sheet);self.assertIn('Stock #',sheet);self.assertIn('jane@example.invalid',cover)
 def test_rejection_keeps_inventory_unchanged(self):
  card=self.submit();before=self.operational();self.service.reject_cic(card['card_id'],approved_by=ADMIN,reason='Duplicate')
  self.assertEqual(before,self.operational());self.assertEqual(self.service.get_cic(card['card_id'])['status'],'Rejected')
 def test_concurrent_approvals_only_apply_once(self):
  card=self.submit();view=self.service.preview_cic(card['card_id'],create_new=True)
  def approve():return self.service.approve_cic(card['card_id'],create_new=True,approved_by=ADMIN,review_token=view['review_token'])
  with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(lambda _:approve(),range(2)))
  with self.service.database.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],2)
 def test_limits(self):
  for qty in [0,-1,True,1.5,101]:
   with self.assertRaises(InventoryError):self.submit(self.payload(qty))
  with self.assertRaises(InventoryError):self.submit(self.payload(lines=[]))
 def test_quantity_first_questionnaire_and_explicit_none_answers(self):
  from inventory_app.cic_questions import QUESTIONS
  cat=next(x for x in self.service.cic_catalog() if x['group']=='ocp.cover')
  counts={q[0]:0 for q in QUESTIONS};counts['ocp.cover']=1
  p=self.payload(lines=[{'item_no':cat['item_no'],'name':cat['name'],'size':cat['size'],'quantity':1,'group':'ocp.cover'}],assessment=counts)
  card=self.submit(p);self.assertEqual(json.loads(card['assessment_json'])['ptg.shirt'],0)
  self.assertEqual(card['lines'][0]['group_key'],'ocp.cover')
  p=self.payload(lines=p['lines'],assessment=dict(counts,**{'ocp.cover':2}))
  with self.assertRaises(InventoryError):self.submit(p)
 def test_all_none_creates_profile_without_stock_or_checkouts(self):
  from inventory_app.cic_questions import QUESTIONS
  card=self.submit(self.payload(lines=[],no_items=True,assessment={q[0]:0 for q in QUESTIONS}))
  approved=self.approve(card);self.assertEqual(approved['status'],'Approved')
  with self.service.database.connect() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM items').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM cadets').fetchone()[0],1)


class CicServerTests(CicTests):
 # The inherited service tests are also exercised against the server-enabled setup.
 def setUp(self):
  super().setUp();self.session=CicSession(self.service)
 def tearDown(self):
  self.session.stop();super().tearDown()
 def call(self,path,method='GET',data=None,token=None,origin=None,host=None,site=None):
  headers={}
  if token:headers['Authorization']='Bearer '+token
  if origin:headers['Origin']=origin
  if host:headers['Host']=host
  if site:headers['Sec-Fetch-Site']=site
  body=None
  if data is not None:body=json.dumps(data).encode();headers['Content-Type']='application/json'
  address=urlsplit(self.session.join_url)
  request=Request(f'{address.scheme}://{address.netloc}'+path,data=body,headers=headers,method=method)
  try:
   with urlopen(request,timeout=10) as r:return r.status,r.read(),dict(r.headers)
  except HTTPError as e:return e.code,e.read(),dict(e.headers)
 def test_http_auth_origin_and_no_admin_routes(self):
  self.assertEqual(len(self.session.code),6)
  self.assertTrue(self.session.code.isdigit())
  self.assertTrue(self.session.join_url.endswith('/det005'))
  self.assertEqual(self.call('/det005',site='cross-site')[0],200)
  self.assertEqual(self.call('/',site='cross-site')[0],200)
  self.assertEqual(self.call('/api/catalog',token=self.session.token,site='cross-site')[0],403)
  self.assertEqual(self.call('/api/catalog')[0],401)
  self.assertEqual(self.call('/api/catalog',token=self.session.token,origin='https://evil.invalid')[0],403)
  self.assertEqual(self.call('/api/catalog',token=self.session.token,host='evil.invalid')[0],403)
  self.assertEqual(self.call('/api/approve',method='POST',data={},token=self.session.token)[0],404)
  self.assertEqual(self.call('/api/catalog',token=self.session.token)[0],200)
 def test_join_submit_receipt_download(self):
  status,body,_=self.call('/api/join','POST',{'code':self.session.code});self.assertEqual(status,200)
  token=json.loads(body)['token'];p=self.payload();status,body,_=self.call('/api/cards','POST',p,token=token)
  self.assertEqual(status,201);cid=json.loads(body)['card_id']
  self.assertEqual(self.call('/api/cards/'+cid,token=token)[0],400)
  self.assertEqual(self.call('/api/cards/'+cid,token=p['receipt_token'])[0],200)
  self.assertEqual(self.call('/api/cards/'+cid+'/wings',token=p['receipt_token'])[0],400)
  self.approve(self.service.get_cic(cid))
  status,body,headers=self.call('/api/cards/'+cid+'/wings',token=p['receipt_token'])
  self.assertEqual(status,200);self.assertTrue(body.startswith(b'PK'));self.assertIn('.xlsx',headers['Content-Disposition'])
  self.assertEqual(len(self.session.notifications()),1)
 def test_expiration(self):
  self.session.expires=0;self.assertEqual(self.call('/api/catalog',token=self.session.token)[0],410)


if __name__=='__main__':unittest.main()
