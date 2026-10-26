import base64
import gc
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from inventory_app.config import AppSettings
from inventory_app.services import InventoryService
from inventory_app.item_metadata import normalize_tags, save_metadata, inventory_analysis


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=InventoryService(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db')))
        self.service.create_manual_item(barcode_id='A0000001',item_name='OCP cap',category='OcP',
            variant='7',item_type='Caps',quantity=5)

    def tearDown(self):
        self.service=None;gc.collect();self.temp.cleanup()

    def test_normalizes_unicode_whitespace_and_case(self):
        self.assertEqual(normalize_tags(' OCP, ocp, ＯＣＰ, Warm   Weather, warm weather'), ['ocp','warm weather'])

    def test_metadata_preserves_stock_and_audits(self):
        before=self.service.get_item('A0000001')
        save_metadata(self.service,'A0000001',['OCP','ocp',' FLAGS '],'OCP','Summer')
        after=self.service.get_item('A0000001')
        self.assertEqual(before,after)
        row=self.service.list_items()[0]
        self.assertEqual(row['custom_tags'],['flags','ocp'])
        self.assertEqual(row['season'],'Summer')
        with self.service.database.connect() as db:
            audit=db.execute('SELECT * FROM inventory_changes ORDER BY change_id DESC LIMIT 1').fetchone()
            self.assertEqual(audit['quantity_change'],0)
            self.assertEqual(audit['source'],'Admin code 3 - Williams')

    def test_image_roundtrip_and_unchanged_image(self):
        png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6GJkAAAAASUVORK5CYII='
        save_metadata(self.service,'A0000001',[],'','Unclassified',png)
        save_metadata(self.service,'A0000001',['cap'],'OCP','All-season')
        with self.service.database.connect() as db:
            self.assertEqual(db.execute('SELECT image_png FROM item_metadata').fetchone()[0],png)
        with self.assertRaises(ValueError):save_metadata(self.service,'A0000001',[],'','Winter',base64.b64encode(b'bad').decode())
        save_metadata(self.service,'A0000001',[],'','Winter','')
        with self.service.database.connect() as db:
            self.assertEqual(db.execute('SELECT image_png FROM item_metadata').fetchone()[0],'')

    def test_family_and_season_totals_reconcile_separately(self):
        rows=self.service.list_items()
        self.assertEqual(rows[0]['family'],'OCP')
        self.assertEqual(rows[0]['season'],'Unclassified')
        for sheet in inventory_analysis(rows):
            self.assertEqual(sum(r['Total Units'] for r in sheet['rows']),5)

    def test_report_contains_native_charts_and_full_inventory(self):
        output=self.service.export_weekly_activity_spreadsheet(open_after=False)
        with zipfile.ZipFile(output) as book:
            chart_names=[n for n in book.namelist() if n.startswith('xl/charts/')]
            self.assertEqual(len(chart_names),2)
            for name in book.namelist():
                if name.endswith('.xml') or name.endswith('.rels'): ET.fromstring(book.read(name))
            self.assertIn('Current Inventory',book.read('xl/workbook.xml').decode())
            for name in chart_names:
                chart=ET.fromstring(book.read(name))
                ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
                self.assertEqual(chart.find('.//c:numCache/c:pt/c:v',ns).text,'5')


if __name__=='__main__':unittest.main()
