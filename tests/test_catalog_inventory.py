import unittest,tempfile,gc
from pathlib import Path
from datetime import date
from unittest.mock import patch
from inventory_app.config import AppSettings
from inventory_app.services import InventoryService,InventoryError
from inventory_app.ui import InventoryApp

class CatalogInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=10000)
        self.service=InventoryService(self.settings)
        self.admin={'role':'CADRE','display_name':'CADRE','admin_id':None}
    def tearDown(self):
        self.service=None;gc.collect();self.temp.cleanup()
    def test_baseline_is_complete_repeat_safe_and_preserves_existing_stock(self):
        catalog=self.service.list_wings_catalog();chosen=catalog[0]
        item=self.service.save_generated_barcode(category='Other',variant='Any',item_type='Any',
            wings_item_no=chosen['item_no'],units_per_barcode=7)
        self.service.checkout_item(barcode_id=item['barcode_id'],cadet_name='Count, A, Cadet',
            cadet_email='count@example.com',quantity=2,approved_by=self.admin)
        with self.service.database.connect() as c:
            c.execute('INSERT INTO barcode_aliases(alias_barcode_id,canonical_barcode_id,created_at,reason) VALUES(?,?,?,?)',
                ('A0000002',item['barcode_id'],'2026-10-14','Reserved old label'));c.commit()
            original=dict(c.execute('SELECT * FROM items WHERE barcode_id=?',(item['barcode_id'],)).fetchone())
            tx=[dict(r) for r in c.execute('SELECT * FROM transactions')]
        result=self.service.enable_catalog_inventory()
        self.assertEqual(result['created'],len(catalog)-1)
        self.assertNotIn('A0000002',result['barcodes'])
        with self.service.database.connect() as c:
            self.assertEqual(dict(c.execute('SELECT * FROM items WHERE barcode_id=?',(item['barcode_id'],)).fetchone()),original)
            self.assertEqual([dict(r) for r in c.execute('SELECT * FROM transactions')],tx)
            self.assertEqual(c.execute('SELECT sum(total_quantity),sum(available_quantity) FROM items').fetchone()[:],(7,5))
        self.assertEqual(self.service.ensure_catalog_inventory()['created'],0)
        rows=self.service.list_items()
        self.assertEqual(sum(r['count_status']=='Not counted' for r in rows),len(catalog)-1)
        report=self.service.get_weekly_activity_report_data()
        self.assertEqual(report['summary']['routine_units_added'],7)
        self.assertEqual(report['summary']['new_catalog_rows'],1)
        self.assertFalse(any(r['Change']=='Catalog Baseline Created' for r in report['sheets'][1]['rows']))
    def test_counted_zero_and_available_recount_preserve_cadet_holdings(self):
        self.service.enable_catalog_inventory()
        item=next(r for r in self.service.list_items() if r['count_status']=='Not counted')
        barcode=item['barcode_id']
        zero=self.service.record_available_count(barcode_id=barcode,available_quantity=0,approved_by=self.admin)
        self.assertEqual(zero['count_status'],'Counted')
        self.assertEqual(zero['last_count_available'],0)
        self.service.restock_item(barcode_id=barcode,quantity=4)
        self.service.checkout_item(barcode_id=barcode,cadet_name='Count, A, Cadet',
            cadet_email='count@example.com',quantity=2,approved_by=self.admin)
        with self.service.database.connect() as c:before=[dict(r) for r in c.execute('SELECT * FROM transactions')]
        result=self.service.record_available_count(barcode_id=barcode,available_quantity=0,approved_by=self.admin)
        self.assertEqual((result['total_quantity'],result['available_quantity']),(2,0))
        with self.service.database.connect() as c:
            self.assertEqual([dict(r) for r in c.execute('SELECT * FROM transactions')],before)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with self.assertRaises(InventoryError):self.service.record_available_count(barcode_id=barcode,available_quantity=-1)
    def test_item_filter_and_new_catalog_item_automatically_has_zero_barcode(self):
        with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):
            app=InventoryApp(self.settings,preload_catalog=True)
        try:
            app.attributes('-alpha',0);app.deiconify();app.update()
            app.item_count_filter_var.set('Not counted');app.refresh_items_tree()
            barcode=app.items_tree.get_children()[0]
            app.service.record_available_count(barcode_id=barcode,available_quantity=0)
            app.item_count_filter_var.set('Counted zero');app.refresh_items_tree()
            self.assertEqual(app.items_tree.get_children(),(barcode,))
            from inventory_app.items_ui import submit_item_search
            app.item_search_var.set(barcode);submit_item_search(app,app.item_search_entry)
            self.assertEqual(app.item_count_filter_var.get(),'All counts')
            item_no=app.service.add_custom_catalog_item(item_name='New kit',size='',category='Other',subcategory='Kits',
                sex='U',stock_number='',uom='EA',source='Test')
            app.refresh_all_views()
            matches=[r for r in app.service.list_items() if r['wings_item_no']==item_no]
            self.assertEqual(len(matches),1);self.assertEqual(matches[0]['total_quantity'],0)
        finally:
            for callback in app.tk.call('after','info'):app.after_cancel(callback)
            app.destroy();app.service=None;app=None;gc.collect()
