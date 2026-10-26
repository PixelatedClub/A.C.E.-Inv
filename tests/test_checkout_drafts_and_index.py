import tempfile,unittest,gc
from pathlib import Path
from unittest.mock import patch
from inventory_app.config import AppSettings
from inventory_app.ui import InventoryApp
from inventory_app.shortcuts import queue_selected
from inventory_app.services import InventoryError

class CheckoutDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'))
        self.app=self.make_app()
    def make_app(self):
        with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):
            app=InventoryApp(self.settings)
        app.attributes('-alpha',0);app.deiconify();app.update()
        app.current_admin={'role':'CADRE','display_name':'CADRE','admin_id':None}
        return app
    def dispose(self,app):
        for callback in app.tk.call('after','info'):app.after_cancel(callback)
        app.destroy();app.service=None;gc.collect()
    def tearDown(self):
        self.dispose(self.app);self.app=None;gc.collect();self.temp.cleanup()
    def identity(self,last,email):
        a=self.app;a.checkout_last_name_var.set(last);a.checkout_middle_initial_var.set('A')
        a.checkout_first_name_var.set('Cadet');a.checkout_email_var.set(email)
    def queue(self,barcode,quantity):
        self.app.checkout_scan_var.set(barcode);self.app.checkout_qty_var.set(str(quantity));self.app._queue_checkout_barcode()
    def test_independent_tabs_stock_submission_and_restart(self):
        a=self.app
        a.service.create_manual_item(barcode_id='A0000001',item_name='Cap',category='OCP',variant='7',item_type='Cap',quantity=3)
        first=a.standard_checkout_tab;self.identity('First','first@example.com');self.queue('A0000001',2)
        a._set_text(a.checkout_notes_text,'First fitting notes')
        second=a._new_checkout_draft();a.update();self.identity('Second','second@example.com')
        with patch.object(a,'_show_error') as error:self.queue('A0000001',2);error.assert_called_once()
        self.assertEqual(a.checkout_queue,{})
        self.queue('A0000001',1)
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],3)
        with patch.object(a,'_show_info'),patch.object(a,'_show_error') as error:
            a._submit_checkout();error.assert_not_called()
        self.assertEqual(a.checkout_queue,{})
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],2)
        a.checkout_notebook.select(first);a.update()
        self.assertEqual(a.checkout_email_var.get(),'first@example.com')
        self.assertEqual(a.checkout_queue['A0000001']['quantity'],2)
        self.assertEqual(a.checkout_queue['A0000001']['available_quantity'],2)
        self.assertEqual(a._get_text(a.checkout_notes_text),'First fitting notes')
        a._save_checkout_drafts();self.dispose(a);self.app=self.make_app();a=self.app
        self.assertEqual(len(a.checkout_drafts),2)
        first=next(key for key,c in a.checkout_drafts.items() if c['checkout_email_var'].get()=='first@example.com')
        a.checkout_notebook.select(first);a.update()
        self.assertEqual(a.checkout_queue['A0000001']['quantity'],2)
        self.assertEqual(a._get_text(a.checkout_notes_text),'First fitting notes')
        with patch.object(a,'_show_info'),patch.object(a,'_show_error') as error:a._submit_checkout();error.assert_not_called()
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],0)
        _,rows=a.service.get_report('Transaction History')
        self.assertEqual(len(rows),3)
        self.assertEqual(sorted(r['cadet_email'] for r in rows),['first@example.com','first@example.com','second@example.com'])
    def test_right_click_and_shortcuts_target_active_draft_and_loans_moved(self):
        a=self.app
        a.service.create_manual_item(barcode_id='A0000001',item_name='Cap',category='OCP',variant='7',item_type='Cap',quantity=2)
        first=a.standard_checkout_tab;second=a._new_checkout_draft();a.update()
        a.refresh_items_tree();a.items_tree.selection_set('A0000001');queue_selected(a,a.items_tree);a.update()
        self.assertEqual(a.checkout_notebook.select(),str(second))
        self.assertEqual(a.checkout_drafts[str(first)]['checkout_queue'],{})
        self.assertEqual(a.checkout_queue['A0000001']['quantity'],1)
        self.assertEqual(a.loans_tab.winfo_parent(),str(a.returns_notebook))
        a.focus_force();a.checkout_scan_entry.focus_set();a.update()
        a.checkout_scan_entry.event_generate('<KeyPress-l>',state=4|8);a.update()
        self.assertEqual(a.notebook.select(),str(a.returns_tab))
        self.assertEqual(a.returns_notebook.select(),str(a.loans_tab))
        a.direct_shortcuts.actions['r']();a.update()
        self.assertEqual(a.returns_notebook.select(),str(a.standard_returns_tab))
    def test_index_dialog_creates_zero_stock_then_reuses_barcode(self):
        a=self.app
        item_no=a.service.add_custom_catalog_item(item_name='Test local kit',size='',category='Other',
            subcategory='Kits',sex='U',stock_number='',uom='EA',source='Test')
        window=a._show_catalog_barcode_dialog(item_no);a.update()
        def descendants(w):
            for child in w.winfo_children():
                yield child;yield from descendants(child)
        button=next(w for w in descendants(window) if w.winfo_class()=='TButton' and w.cget('text')=='Generate Barcode')
        with patch.object(a,'_show_error') as error:button.invoke();a.update();error.assert_not_called()
        matches=[r for r in a.service.list_items() if r['wings_item_no']==item_no]
        self.assertEqual(len(matches),1);self.assertEqual(matches[0]['total_quantity'],0)
        self.assertEqual(matches[0]['variant'],'ONE SIZE')
        first=matches[0]['barcode_id'];window.destroy()
        record=a.service.save_generated_barcode(category='Other',variant='ONE SIZE',item_type='Kits',
            item_name='Test local kit',wings_item_no=item_no,units_per_barcode=2,allow_zero=True)
        self.assertEqual(record['barcode_id'],first);self.assertEqual(record['total_quantity'],2)
        with self.assertRaises(InventoryError):
            a.service.save_generated_barcode(category='Other',variant='ONE SIZE',item_type='Kits',
                item_name='Test local kit',wings_item_no=item_no,units_per_barcode=-1,allow_zero=True)

    def test_checkout_action_visible_at_minimum_window_size(self):
        a=self.app;a.geometry('1000x640');a.notebook.select(a.checkout_tab);a.update()
        def descendants(w):
            for child in w.winfo_children():
                yield child;yield from descendants(child)
        submit=next(w for w in descendants(a.standard_checkout_tab)
            if w.winfo_class()=='TButton' and w.cget('text')=='Check Out Queued Items')
        self.assertLessEqual(submit.winfo_rooty()+submit.winfo_height(),a.winfo_rooty()+a.winfo_height())

    def test_add_custom_item_can_open_barcode_generation_immediately(self):
        a=self.app;a._open_add_custom_item_dialog();a.update()
        window=next(w for w in a.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Add Custom Catalog Item')
        form=window.winfo_children()[0]
        widgets=form.winfo_children()
        entry=next(w for w in widgets if w.winfo_class()=='TEntry' and
            int(w.grid_info()['row'])==0 and int(w.grid_info()['column'])==3)
        entry.insert(0,'New custom kit')
        for row,col,value in ((1,3,'Other'),(2,1,'Kits')):
            combo=next(w for w in widgets if w.winfo_class()=='TCombobox' and
                int(w.grid_info()['row'])==row and int(w.grid_info()['column'])==col)
            combo.set(value)
        next(w for w in widgets if w.winfo_class()=='TCheckbutton').invoke()
        buttons=next(w for w in widgets if w.winfo_class()=='TFrame' and int(w.grid_info()['row'])==7)
        with patch.object(a,'_show_error') as error:
            next(w for w in buttons.winfo_children() if w.cget('text')=='Add Custom Item').invoke()
            a.update();error.assert_not_called()
        barcode_window=next(w for w in a.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Generate Index Barcode')
        self.assertIsNone(a.grab_current())
        self.assertEqual(len(a.service.list_wings_catalog(search='New custom kit')),1)
        barcode_window.destroy()
