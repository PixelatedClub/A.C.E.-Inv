"""Tk integration smoke tests against an isolated database, never operational stock."""
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inventory_app.config import AppSettings
from inventory_app.ui import InventoryApp
from inventory_app.shortcuts import queue_selected
from inventory_app.item_metadata_ui import edit_metadata
from inventory_app.item_metadata import save_metadata


class ItemWorkspaceUiTests(unittest.TestCase):
    def test_workspace_queue_filter_and_image_dialog(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):
                app=InventoryApp(AppSettings(db_path=str(Path(temp)/'inventory.db')))
                try:
                    app.attributes('-alpha',0)
                    app.geometry('1200x760')
                    app.deiconify()
                    for tab,split in [(app.items_tab,app.items_split),
                                      (app.generator_tab,app.generator_split),
                                      (app.returns_tab,app.returns_split),
                                      (app.cadets_tab,app.cadets_split),
                                      (app.cadet_fitting_tab,app.fitting_split)]:
                        app.notebook.select(tab);app.update()
                        self.assertEqual(len(split.panes()),2)
                        before=split.sash_coord(0)[0]
                        split.sash_place(0,before+60,0);app.update()
                        self.assertGreater(split.sash_coord(0)[0],before)
                        split.reset();app.update()
                    app.notebook.select(app.generator_tab);app.update()
                    before=app.generator_stack.sash_coord(0)[1]
                    app.generator_stack.sash_place(0,0,before+25);app.update()
                    self.assertGreater(app.generator_stack.sash_coord(0)[1],before)
                    app.geometry('1000x640');app.notebook.select(app.items_tab);app.update()
                    self.assertLessEqual(app.items_split.winfo_width(),1000)
                    app.item_search_var.set('Keep this text')
                    app.focus_force();app.item_search_entry.focus_set();app.update()
                    app.item_search_entry.event_generate('<KeyPress-g>',state=4);app.update()
                    self.assertEqual(app.notebook.select(),str(app.generator_tab))
                    self.assertEqual(app.item_search_var.get(),'Keep this text')
                    app.generator_quick_find_entry.focus_set();app.update()
                    app.generator_quick_find_entry.event_generate('<KeyPress-f>',state=4);app.update()
                    self.assertEqual(app.notebook.select(),str(app.items_tab))
                    app.item_search_entry.event_generate('<KeyPress-m>',state=4);app.update()
                    self.assertEqual(app.notebook.select(),str(app.cadet_fitting_tab))
                    app.item_search_var.set('');app.notebook.select(app.items_tab);app.update()
                    app.service.create_manual_item(barcode_id='A0000001',item_name='OCP cap',category='ocp',variant='7',item_type='Cap',quantity=2)
                    save_metadata(app.service,'A0000001',['Flags'],'OCP','Summer')
                    app.item_tag_filter_var.set('FLAGS, OCP')
                    app.refresh_items_tree()
                    self.assertEqual(app.items_tree.get_children(),('A0000001',))
                    app.items_tree.selection_set('A0000001')
                    queue_selected(app,app.items_tree)
                    self.assertEqual(app.checkout_queue['A0000001']['quantity'],1)
                    self.assertEqual(app.service.get_item('A0000001')['available_quantity'],2)
                    edit_metadata(app)
                    dialog=app.grab_current()
                    self.assertIsNotNone(dialog)
                    dialog.update_idletasks()
                    self.assertGreater(dialog.winfo_reqwidth(),300)
                    dialog.destroy()
                    admin={'role':'CADRE','display_name':'CADRE','admin_id':None}
                    app.service.checkout_item(barcode_id='A0000001',cadet_name='Undo, A, Cadet',
                        cadet_email='undo@example.com',quantity=1,approved_by=admin)
                    cadet=next(c for c in app.service.list_cadets() if c['email']=='undo@example.com')
                    cid=cadet['cadet_id']
                    ids=[t['transaction_id'] for t in app.service.get_cadet_details(cid)['current_items']]
                    app.service.acquire_checked_out_items(cadet_id=cid,transaction_ids=ids,
                        disposition='Purchased',approved_by=admin)
                    app.selected_cadet_id=cid;app.current_admin=admin
                    with patch('inventory_app.ui.messagebox.askyesno',return_value=True), \
                         patch.object(app,'_show_info') as info,patch.object(app,'_show_error') as error:
                        app._undo_last_cadet_acquisition();app.update()
                        error.assert_not_called();info.assert_called_once()
                    self.assertEqual(len(app.service.get_cadet_details(cid)['current_items']),1)
                    self.assertEqual(len(app.cadet_current_tree.get_children()),1)
                    self.assertEqual(app.service.get_item('A0000001')['total_quantity'],2)
                finally:
                    # Avoid leaving scheduled callbacks behind in a second Tk test.
                    for callback in app.tk.call('after','info'): app.after_cancel(callback)
                    app.destroy();app.service=None;app=None;gc.collect()
