import unittest,tempfile,gc
from datetime import date
from pathlib import Path
from inventory_app.config import AppSettings
from inventory_app.services import InventoryService
from inventory_app.report_html import write_activity_html


class HtmlReportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.service=InventoryService(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=10000))
 def tearDown(self):
  self.service=None;gc.collect();self.temp.cleanup()
 def test_html_export_includes_today_and_all_sections_without_coa(self):
  self.service.create_manual_item(barcode_id='HTML-TEST',item_name='<script>alert(1)</script>',category='Test',variant='S',item_type='OCP',quantity=2)
  day=date.today().isoformat()
  report=self.service.get_weekly_activity_report_data(start_date=day,end_date=day,coa_validation='DO NOT SHOW COA')
  self.assertEqual(report['summary']['routine_units_added'],2)
  with self.service.database.connect() as c:before=c.execute('SELECT COUNT(*) FROM inventory_changes').fetchone()[0]
  path=self.service.export_activity_html(start_date=day,end_date=day,bluf='Test <BLUF> \u2014 safe',open_after=False)
  doc=path.read_text(encoding='utf-8')
  self.assertEqual(path.suffix,'.html')
  for sheet in report['sheets'][1:]:self.assertIn(sheet['sheet_name'],doc)
  self.assertNotIn('<script>',doc);self.assertIn('&lt;script&gt;',doc)
  self.assertIn('Test &lt;BLUF&gt;',doc)
  self.assertNotIn('COURSE OF ACTION',doc);self.assertNotIn('coa_validation',doc)
  self.assertNotIn('\u2014',doc);self.assertEqual(doc.count('<svg '),2)
  with self.service.database.connect() as c:self.assertEqual(before,c.execute('SELECT COUNT(*) FROM inventory_changes').fetchone()[0])
  direct=write_activity_html(Path(self.temp.name)/'direct.html',report)
  self.assertNotIn('DO NOT SHOW COA',direct.read_text(encoding='utf-8'))
 def test_monday_uses_same_html_format(self):
  path=self.service.export_monday_report(monday=date(2026,10,19))
  self.assertEqual(path.suffix,'.html')
  doc=path.read_text(encoding='utf-8')
  self.assertIn('2026-10-12 through 2026-10-18',doc)
  self.assertIn('Current Inventory',doc)
  self.assertNotIn('COURSE OF ACTION',doc)
