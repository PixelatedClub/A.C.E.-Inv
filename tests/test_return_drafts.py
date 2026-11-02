import gc,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from inventory_app.config import AppSettings
from inventory_app.ui import InventoryApp

class ReturnDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.settings=AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'))
        self.app=self.make_app();a=self.app
        a.service.create_manual_item(barcode_id='A0000001',item_name='OCP Coat',category='OCP',variant='M-R',item_type='Coat',quantity=5)
        for name,email,quantity,loan in [('Alpha, Cadet','alpha@example.invalid',2,True),('Bravo, Cadet','bravo@example.invalid',1,False)]:
            a.service.checkout_items_bulk(line_items=[dict(barcode_id='A0000001',quantity=quantity)],cadet_name=name,cadet_email=email,approved_by=a.current_admin,
                **(dict(loan_due_date=str(date.today()+timedelta(days=14)),loan_purpose='UI test') if loan else {}))
        self.ids={r['email']:r['cadet_id'] for r in a.service.list_cadets()};a.refresh_all_views();a.update()
    def make_app(self):
        with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):a=InventoryApp(self.settings)
        a.attributes('-alpha',0);a.geometry('1000x640');a.deiconify();a.update();a.current_admin=dict(role='CADRE',display_name='CADRE',admin_id=None)
        return a
    def dispose(self,a):
        for callback in a.tk.call('after','info'):a.after_cancel(callback)
        a.destroy();a.service=None;gc.collect()
    def tearDown(self):self.dispose(self.app);self.app=None;gc.collect();self.temp.cleanup()
    def select_first(self):
        self.app.return_inventory_tree.selection_set(self.app.return_inventory_tree.get_children()[0]);self.app.update()
    def test_independent_cadets_selections_notes_and_restart(self):
        a=self.app;first=a.return_draft_notebook.select();alpha=self.ids['alpha@example.invalid'];bravo=self.ids['bravo@example.invalid']
        a._load_return_cadet_details(alpha);self.select_first();a._set_text(a.return_notes_text,'Alpha notes')
        selected=a._selected_return_transaction_ids()
        second=a._new_return_draft(activate=False);a.update()
        self.assertEqual(a.selected_return_cadet_id,alpha)
        a.return_draft_notebook.select(second);a.update();a._load_return_cadet_details(bravo);self.select_first();a._set_text(a.return_notes_text,'Bravo notes')
        bravo_selection=a._selected_return_transaction_ids()
        a.return_draft_notebook.select(first);a.update()
        self.assertEqual(a.selected_return_cadet_id,alpha);self.assertEqual(a._selected_return_transaction_ids(),selected)
        self.assertEqual(a._get_text(a.return_notes_text),'Alpha notes')
        with patch('inventory_app.ui.messagebox.askyesno',return_value=True),patch.object(a,'_show_info'),patch.object(a,'_show_error') as error:
            a._submit_return();error.assert_not_called()
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],3)
        a.return_draft_notebook.select(second);a.update()
        self.assertEqual(a.selected_return_cadet_id,bravo);self.assertEqual(a._selected_return_transaction_ids(),bravo_selection)
        self.assertEqual(a._get_text(a.return_notes_text),'Bravo notes')
        a._save_return_drafts();self.dispose(a);self.app=self.make_app();a=self.app
        context=next(c for c in a.return_drafts.values() if c['selected_return_cadet_id']==bravo)
        a.return_draft_notebook.select(context['frame']);a.update()
        self.assertEqual(a._selected_return_transaction_ids(),bravo_selection);self.assertEqual(a._get_text(a.return_notes_text),'Bravo notes')
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],3)
    def test_direct_loan_return_cancel_history_and_duplicate_protection(self):
        a=self.app;alpha=self.ids['alpha@example.invalid'];a._load_return_cadet_details(alpha);self.select_first()
        selected=a._selected_return_transaction_ids()[0];a.refresh_loans();a.loan_tree.selection_set(str(selected))
        with patch('inventory_app.loan_ui.messagebox.askyesno',return_value=False):a._return_selected_loans()
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],2)
        with patch('inventory_app.loan_ui.messagebox.askyesno',return_value=True),patch.object(a,'_show_info'),patch.object(a,'_show_error') as error:
            a._return_selected_loans();error.assert_not_called()
        a.update();self.assertEqual(a.service.get_item('A0000001')['available_quantity'],3)
        self.assertEqual(len(a.service.list_loans()),1);self.assertEqual(a._selected_return_transaction_ids(),[])
        with a.service.database.connect() as connection:
            row=connection.execute('SELECT disposition,return_time,return_approved_by_role FROM transactions WHERE transaction_id=?',(selected,)).fetchone()
        self.assertEqual(row['disposition'],'Returned');self.assertTrue(row['return_time']);self.assertEqual(row['return_approved_by_role'],'CADRE')
        a.loan_show_closed.set(True);a.refresh_loans();a.loan_tree.selection_set(str(selected))
        with patch.object(a,'_show_error') as error:a._return_selected_loans();error.assert_called_once()
        self.assertEqual(a.service.get_item('A0000001')['available_quantity'],3)
    def test_return_tabs_reuse_numbers_and_keep_submit_visible(self):
        a=self.app;second=a._new_return_draft();a.update();self.assertEqual(a.return_drafts[str(second)]['number'],2)
        a._close_return_draft();third=a._new_return_draft();a.update();self.assertEqual(a.return_drafts[str(third)]['number'],2)
        a.notebook.select(a.returns_tab);a.returns_notebook.select(a.standard_returns_tab);a.update()
        def children(parent):
            for child in parent.winfo_children():yield child;yield from children(child)
        submit=next(w for w in children(third) if w.winfo_class()=='TButton' and w.cget('text')=='Return Selected Items')
        self.assertLessEqual(submit.winfo_rooty()+submit.winfo_height(),a.winfo_rooty()+a.winfo_height())
