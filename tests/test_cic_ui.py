import gc,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from inventory_app.config import AppSettings
from inventory_app.ui import InventoryApp


class CicUiTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):
   self.app=InventoryApp(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=10000))
  self.app.withdraw();self.app.update()
  self.app.current_admin={'role':'CADRE','display_name':'CADRE','admin_id':None}
  self.info_patch=patch.object(self.app,'_show_info');self.error_patch=patch.object(self.app,'_show_error')
  self.info_patch.start();self.error_patch.start()
 def tearDown(self):
  self.info_patch.stop();self.error_patch.stop()
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
 def test_microsoft_notice_does_not_switch_tabs(self):
  self.app.notebook.select(self.app.items_tab);self.app.update()
  reader=object();self.app.microsoft_reader=reader
  self.app.microsoft_results.put((reader, (['test-card'], [])))
  from unittest.mock import Mock
  self.app.microsoft_worker=Mock();self.app.microsoft_worker.is_alive.return_value=True
  with patch('inventory_app.cic_ui.tk.Toplevel',side_effect=AssertionError('No notification popup')):
   self.app._poll_microsoft_cic()
  self.assertEqual(self.app.notebook.select(),str(self.app.items_tab))
  self.assertIn('(1 new)',self.app.notebook.tab(self.app.cic_tab,'text'))
  self.app.microsoft_reader=None;self.app.microsoft_worker=None
 def test_local_server_controls_removed(self):
  self.assertFalse(hasattr(self.app,'_start_cic_session'))
  self.assertFalse(hasattr(self.app,'_poll_cic'))

 def test_background_checkout_preserves_current_form_and_selection(self):
  self.app.notebook.select(self.app.items_tab);self.app.update()
  original=self.app.checkout_notebook.select()
  self.app.checkout_email_var.set('original@example.invalid')
  with patch.object(self.app,'_focus_checkout_scan',side_effect=AssertionError('No background focus steal')):
   new=self.app._new_checkout_draft(activate=False);self.app.update()
  self.assertNotEqual(str(new),original)
  self.assertEqual(self.app.checkout_notebook.select(),original)
  self.assertEqual(self.app.checkout_email_var.get(),'original@example.invalid')
  self.assertEqual(self.app.notebook.select(),str(self.app.items_tab))
 def test_routine_windows_are_nonmodal_and_stale_item_edits_are_blocked(self):
  from tkinter import ttk
  self.app.service.create_manual_item(barcode_id='CIC-EDITOR',item_name='Test cap',category='OCP',variant='7',item_type='Cap',quantity=2)
  self.app.refresh_items_tree();self.app.items_tree.selection_set('CIC-EDITOR')
  self.app._edit_selected_item();self.app.update()
  window=next(w for w in self.app.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Edit Barcode CIC-EDITOR')
  self.assertIsNone(self.app.grab_current())
  self.app.service.update_item(barcode_id='CIC-EDITOR',item_name='Newer cap',category='OCP',variant='7',item_type='Cap',total_quantity=3,notes='Newer edit')
  def descendants(w):
   for child in w.winfo_children():yield child;yield from descendants(child)
  button=next(w for w in descendants(window) if isinstance(w,ttk.Button) and w.cget('text')=='Save Changes')
  with patch.object(self.app,'_show_error') as error:button.invoke();error.assert_called_once()
  self.assertEqual(self.app.service.get_item('CIC-EDITOR')['total_quantity'],3)
  window.destroy()
 def test_nonmodal_loan_uses_original_cadet_when_switching_tabs(self):
  from tkinter import ttk
  a=self.app
  a.service.create_manual_item(barcode_id='A0000001',item_name='Test cap',category='OCP',variant='7',item_type='Cap',quantity=4)
  a.checkout_last_name_var.set('Example');a.checkout_first_name_var.set('Jane');a.checkout_email_var.set('jane@example.invalid')
  a.checkout_scan_var.set('A0000001');a._queue_checkout_barcode()
  original=a.checkout_notebook.select();a._submit_checkout_as_loan();a.update()
  window=next(w for w in a.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Loan queued items')
  self.assertIsNone(a.grab_current())
  second=a._new_checkout_draft();a.checkout_last_name_var.set('Other');a.checkout_first_name_var.set('Cadet');a.checkout_email_var.set('other@example.invalid')
  a.checkout_scan_var.set('A0000001');a._queue_checkout_barcode()
  def descendants(w):
   for child in w.winfo_children():yield child;yield from descendants(child)
  button=next(w for w in descendants(window) if isinstance(w,ttk.Button) and w.cget('text')=='Loan Queued Items')
  with patch.object(a,'_show_info'),patch.object(a,'_show_error') as error:button.invoke();error.assert_not_called()
  self.assertEqual(a.checkout_email_var.get(),'other@example.invalid')
  self.assertEqual(a.checkout_notebook.select(),str(second))
  self.assertEqual(a.checkout_queue['A0000001']['quantity'],1)
  self.assertEqual(a.checkout_drafts[original]['checkout_queue'],{})
  self.assertEqual(a.service.list_loans()[0]['cadet_email'],'jane@example.invalid')
 def test_changed_loan_draft_is_not_approved_from_old_window(self):
  from tkinter import ttk
  a=self.app
  a.service.create_manual_item(barcode_id='A0000002',item_name='Test cap',category='OCP',variant='7',item_type='Cap',quantity=4)
  a.checkout_last_name_var.set('Example');a.checkout_first_name_var.set('Jane');a.checkout_email_var.set('jane@example.invalid')
  a.checkout_scan_var.set('A0000002');a._queue_checkout_barcode();a._submit_checkout_as_loan();a.update()
  window=next(w for w in a.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Loan queued items')
  a.checkout_email_var.set('changed@example.invalid')
  def descendants(w):
   for child in w.winfo_children():yield child;yield from descendants(child)
  button=next(w for w in descendants(window) if isinstance(w,ttk.Button) and w.cget('text')=='Loan Queued Items')
  with patch.object(a,'_show_error') as error:button.invoke();error.assert_called_once()
  self.assertEqual(a.service.list_loans(),[])
  self.assertEqual(a.service.get_item('A0000002')['available_quantity'],4)
  window.destroy()
