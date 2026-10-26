import gc,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from inventory_app.config import AppSettings
from inventory_app.ui import InventoryApp
from inventory_app.cic_server import CicSession


class CicUiTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):
   self.app=InventoryApp(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=10000))
  self.app.withdraw();self.app.update()
  self.app.current_admin={'role':'CADRE','display_name':'CADRE','admin_id':None}
 def tearDown(self):
  for callback in self.app.tk.call('after','info'):self.app.after_cancel(callback)
  self.app.destroy();self.app.service=None;self.app=None;gc.collect();self.temp.cleanup()
 def test_queue_and_review_dialog_builds(self):
  import secrets,uuid
  cat=self.app.service.cic_catalog()[0]
  card=self.app.service.submit_cic({'name':'Example, Jane','email':'jane@example.invalid','request_id':str(uuid.uuid4()),'receipt_token':secrets.token_urlsafe(32),
   'lines':[{'item_no':cat['item_no'],'name':cat['name'],'size':cat['size'],'quantity':1}]},session_id='ui-test')
  self.app.refresh_cic();self.app.cic_tree.selection_set(card['card_id']);self.app.update()
  self.app._review_cic();self.app.update()
  self.assertIn('Cadet Inventory Cards',[self.app.notebook.tab(t,'text') for t in self.app.notebook.tabs()])
  dialogs=[w for w in self.app.winfo_children() if w.winfo_class()=='Toplevel'];self.assertTrue(dialogs)
  for d in dialogs:d.destroy()
 def test_stop_session_revokes_listener(self):
  self.app.cic_session=CicSession(self.app.service)
  session=self.app.cic_session;self.app._stop_cic_session()
  self.assertIsNone(self.app.cic_session);self.assertFalse(session.thread.is_alive())
 def test_database_change_blocked_while_hosting(self):
  self.app.cic_session=CicSession(self.app.service)
  with patch.object(self.app,'_show_error') as error:self.app._save_settings();error.assert_called_once()
