import gc
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from inventory_app.config import AppSettings
from inventory_app.services import InventoryService
from inventory_app.items_ui import submit_item_search


class Var:
    def __init__(self,value): self.value=value
    def get(self): return self.value
    def set(self,value): self.value=value


class ItemScanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=InventoryService(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=1000))
        self.service.create_manual_item(barcode_id='A1234567',item_name='Test coat',category='BLUES',variant='38R',item_type='Service Coats',quantity=2)
        with self.service.database.connect() as db:
            db.execute("UPDATE items SET wings_item_no='3189' WHERE barcode_id='A1234567'")
            db.execute("INSERT INTO barcode_aliases(alias_barcode_id,canonical_barcode_id,created_at,reason) VALUES('OLD123','A1234567','2026-09-16','test')")

    def tearDown(self):
        self.service=None;gc.collect();self.temp.cleanup()

    def test_search_barcode_alias_wings_and_text(self):
        for query in ('A1234567',' a1234567\r\n','old123','3189','coat'):
            self.assertEqual([r['barcode_id'] for r in self.service.list_items(search=query)],['A1234567'])
        self.assertEqual(self.service.list_items(search='missing'),[])
        self.assertEqual(self.service.list_items(search='OLD123',status_filter='Retired'),[])

    def app(self,query):
        app=SimpleNamespace(service=self.service,item_search_var=Var(query),item_status_filter_var=Var('Retired'),
                            items_tree=Mock(),_clear_item_form=Mock(),_on_item_selected=Mock(),_show_error=Mock(),item_cache={})
        def refresh():
            app.item_cache={r['barcode_id']:r for r in self.service.list_items(search=app.item_search_var.get(),status_filter=app.item_status_filter_var.get())}
        app.refresh_items_tree=refresh
        return app

    def test_scan_resolves_alias_selects_and_preserves_inventory(self):
        before=self.service.get_item('A1234567')
        app=self.app('old123\r\n');entry=Mock()
        self.assertEqual(submit_item_search(app,entry),'break')
        self.assertEqual(app.item_search_var.get(),'A1234567')
        self.assertEqual(app.item_status_filter_var.get(),'All')
        app.items_tree.selection_set.assert_called_once_with('A1234567')
        app._on_item_selected.assert_called_once()
        entry.selection_range.assert_called_once()
        self.assertEqual(self.service.get_item('A1234567'),before)

    def test_missing_scan_clears_stale_selection(self):
        app=self.app('NOTFOUND')
        submit_item_search(app,Mock())
        app._clear_item_form.assert_called_once()
        app.items_tree.selection_set.assert_not_called()

    def test_text_search_keeps_filter(self):
        app=self.app('coat')
        submit_item_search(app,Mock())
        self.assertEqual(app.item_status_filter_var.get(),'Retired')

    def test_timestamp_wrapped_scan(self):
        self.service.create_manual_item(barcode_id='A0000174',item_name='Scanner test',category='BLUES',variant='40R',item_type='Service Coats',quantity=1)
        app=self.app('2026/09/17 01:40:00 A0000174 2026/09/17 01:40:00')
        submit_item_search(app,Mock())
        self.assertEqual(app.item_search_var.get(),'A0000174')
        app.items_tree.selection_set.assert_called_once_with('A0000174')
        app._show_error.assert_not_called()

    def test_timestamp_wrapped_alias(self):
        with self.service.database.connect() as db:
            db.execute("INSERT INTO barcode_aliases VALUES('A0000009','A1234567','2026-09-17','test')")
        app=self.app('2026/09/17 01:40:00 a0000009 2026/09/17 01:40:00')
        submit_item_search(app,Mock())
        self.assertEqual(app.item_search_var.get(),'A1234567')
        app.items_tree.selection_set.assert_called_once_with('A1234567')

    def test_multiple_scanned_barcodes_are_rejected(self):
        app=self.app('A1234567 A0000174')
        submit_item_search(app,Mock())
        app.items_tree.selection_set.assert_not_called()
        app._show_error.assert_called_once()


if __name__=='__main__': unittest.main()
