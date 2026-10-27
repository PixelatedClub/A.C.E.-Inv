import unittest, tempfile, gc
from pathlib import Path
from inventory_app.uniform_search import search_match
from inventory_app.config import AppSettings
from inventory_app.services import InventoryService


class UniformSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=InventoryService(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=10000))
        self.service.create_manual_item(barcode_id='SEARCH-1',item_name='OCP COAT',category='OCP',variant='M-R',item_type='All Weather',quantity=2)
        self.service.create_manual_item(barcode_id='SEARCH-2',item_name='COAT OCP IHWCU',category='Shirts',variant='M-R',item_type='Summer',quantity=1)
        self.service.create_manual_item(barcode_id='SEARCH-HAT',item_name='OCP Patrol Cap',category='Accessories',variant='7-1/2',item_type='OCP',quantity=1)
    def tearDown(self):
        self.service=None;gc.collect();self.temp.cleanup()
    def test_words_across_fields_case_and_sizes_without_tags(self):
        before=self.service.list_items()
        for query in ['ocp blouse medium regular','MED REG OCP TOP','ocp coat mr']:
            self.assertEqual({r['barcode_id'] for r in self.service.list_items(search=query)},{'SEARCH-1','SEARCH-2'})
        self.assertEqual([r['barcode_id'] for r in self.service.list_items(search='ocp coat cold mr')],['SEARCH-1'])
        self.assertEqual([r['barcode_id'] for r in self.service.list_items(search='ocp summer blouse medium regular')],['SEARCH-2'])
        self.assertEqual(before,self.service.list_items())
    def test_numeric_sizes_do_not_match_neighboring_sizes(self):
        for query in ['cover 7.5','ocp hat seven and a half','patrol cap 7 1/2','7.50 cap']:
            self.assertEqual([r['barcode_id'] for r in self.service.list_items(search=query)],['SEARCH-HAT'])
        self.assertFalse(self.service.list_items(search='cap 7.75'))
        self.assertFalse(self.service.list_items(search='coat xs'))
    def test_ids_aliases_and_status_preserved(self):
        with self.service.database.connect() as c:
            c.execute("INSERT INTO barcode_aliases VALUES('OLD-HAT','SEARCH-HAT','2026-10-27','test')")
        self.assertEqual([r['barcode_id'] for r in self.service.list_items(search='old-hat')],['SEARCH-HAT'])
        self.assertFalse(self.service.list_items(search='OLD-HAT',status_filter='Retired'))
    def test_catalog_search_uses_size_and_gender_aliases(self):
        catalog=[dict(item_no='1001',item_name='TROUSERS, OCP',category='Pants',size='M-R',sex='M'),
                 dict(item_no='1002',item_name='TROUSERS, OCP IHWCU',category='Pants',size='M-R',sex='M')]
        self.assertTrue(all(search_match('ocp pants medium regular',r) for r in catalog))
        self.assertTrue(search_match('mens summer pants mr',catalog[1]))
        self.assertFalse(search_match('womens summer pants mr',catalog[1]))
        self.assertFalse(search_match('cold pants mr',catalog[1]))
    def test_live_service_index_query_includes_local_and_official(self):
        with self.service.database.connect() as c:
            c.execute("INSERT INTO wings_catalog(item_no,item_name,size,category,subcategory,sex,stock_number,uom,source,is_wings) VALUES('991111','TROUSERS, OCP','M-R','Pants','OCP','M','123456','PR','test',1)")
        matches=self.service.list_wings_catalog(search='ocp pants medium regular mens')
        self.assertIn('991111',{r['item_no_key'] for r in matches})
        matches=self.service.list_wings_catalog(search='0000991111')
        self.assertEqual([r['item_no_key'] for r in matches],['991111'])
    def test_partial_words_and_no_unknown_word_ignored(self):
        self.assertTrue(self.service.list_items(search='patr cap'))
        self.assertFalse(self.service.list_items(search='patrol banana'))
    def test_shared_categories_do_not_confuse_item_types(self):
        from inventory_app.cic_questions import question_for
        pants=dict(item_name='SLACKS, WOMENS',category='PANTS/SKIRT',subcategory='Blues',size='12-R')
        skirt=dict(pants,item_name='SKIRT, WOMENS')
        self.assertEqual(question_for(pants),'blues.trousers')
        self.assertEqual(question_for(skirt),'blues.skirt')
        self.assertTrue(search_match('blues pants womens',pants))
        self.assertFalse(search_match('blues skirt womens',pants))
        self.assertFalse(search_match('blues pants womens',skirt))
        self.assertEqual(question_for(dict(item_name='IPTU PANTS',category='PT wear',subcategory='Shorts/Pants')),'ptg.pants')


if __name__=='__main__':unittest.main()
