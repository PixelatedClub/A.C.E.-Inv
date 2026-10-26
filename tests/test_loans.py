import gc
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from inventory_app.config import AppSettings
from inventory_app.services import InventoryService, InventoryError

ADMIN={'admin_id':None,'role':'CADRE','display_name':'CADRE'}


class LoanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=InventoryService(AppSettings(db_path=str(Path(self.temp.name)/'inventory.db'),backup_interval_ops=1000))
        self.item=self.service.save_generated_barcode(category='BLUES',item_type='Coat',item_name='Test Coat',variant='40 R',units_per_barcode=5)

    def tearDown(self):
        self.service=None;gc.collect();self.temp.cleanup()

    def issue(self, quantity=2, **kwargs):
        return self.service.checkout_items_bulk(line_items=[{'barcode_id':self.item['barcode_id'],'quantity':quantity}],cadet_name='Test, A, Cadet',cadet_email='test@example.edu',approved_by=ADMIN,**kwargs)

    def test_loan_deadline_partial_return_and_overdue(self):
        due=date.today()+timedelta(days=21)
        self.issue(loan_due_date=str(due),loan_purpose='Flags')
        loans=self.service.list_loans(today=due+timedelta(days=1))
        self.assertEqual(len(loans),2);self.assertTrue(all(r['overdue'] for r in loans))
        self.assertFalse(self.service.list_loans(today=due)[0]['overdue'])
        self.service.return_cadet_items(cadet_id=loans[0]['cadet_id'],transaction_ids=[loans[0]['transaction_id']],approved_by=ADMIN)
        self.assertEqual(len(self.service.list_loans()),1)
        self.assertEqual(len(self.service.list_loans(include_closed=True)),2)
        self.assertEqual(self.service.get_item(self.item['barcode_id'])['available_quantity'],4)

    def test_deadline_conversion_does_not_change_inventory_and_rejects_closed(self):
        self.issue()
        with self.service.database.connect() as c:
            rows=c.execute('SELECT * FROM transactions WHERE barcode_id=?',(self.item['barcode_id'],)).fetchall()
        before=self.service.get_item(self.item['barcode_id'])
        ids=[r['transaction_id'] for r in rows]
        self.service.set_loan_deadline(ids,str(date.today()+timedelta(days=21)),'Flags',ADMIN)
        self.assertEqual(before,self.service.get_item(self.item['barcode_id']))
        self.service.acquire_checked_out_items(cadet_id=rows[0]['cadet_id'],transaction_ids=[ids[0]],disposition='Acquired / Permanent Issue',approved_by=ADMIN)
        self.assertEqual(len(self.service.list_loans()),1)
        old_due=self.service.list_loans()[0]['loan_due_date']
        with self.assertRaises(InventoryError):
            self.service.set_loan_deadline(ids,str(date.today()+timedelta(days=28)),'Extend',ADMIN)
        self.assertEqual(self.service.list_loans()[0]['loan_due_date'],old_due)

    def test_active_loan_can_be_converted_to_standard_checkout(self):
        due = date.today() + timedelta(days=21)
        self.issue(quantity=1, loan_due_date=str(due), loan_purpose='Game day flags')
        loan = self.service.list_loans()[0]
        before = self.service.get_item(self.item['barcode_id'])

        converted = self.service.convert_loans_to_standard_checkout(
            [loan['transaction_id']],
            ADMIN,
        )

        self.assertEqual(converted, 1)
        self.assertEqual(self.service.list_loans(), [])
        self.assertEqual(self.service.get_item(self.item['barcode_id']), before)
        with self.service.database.connect() as connection:
            transaction = connection.execute(
                'SELECT return_time, disposition, loan_due_date, loan_purpose FROM transactions WHERE transaction_id=?',
                (loan['transaction_id'],),
            ).fetchone()
            event = connection.execute(
                'SELECT action, details FROM loan_events WHERE transaction_id=? ORDER BY event_id DESC LIMIT 1',
                (loan['transaction_id'],),
            ).fetchone()
        self.assertIsNone(transaction['return_time'])
        self.assertEqual(transaction['disposition'], '')
        self.assertEqual(transaction['loan_due_date'], '')
        self.assertEqual(transaction['loan_purpose'], '')
        self.assertEqual(event['action'], 'Converted to standard checkout')
        self.assertIn(str(due), event['details'])

    def test_invalid_date_or_stock_is_atomic(self):
        for due in ('bad','2026-02-30',str(date.today()-timedelta(days=1))):
            with self.assertRaises(InventoryError):self.issue(loan_due_date=due)
        with self.assertRaises(InventoryError):self.issue(quantity=6,loan_due_date=str(date.today()))
        with self.service.database.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions WHERE barcode_id=?',(self.item['barcode_id'],)).fetchone()[0],0)
        self.assertEqual(self.service.get_item(self.item['barcode_id'])['available_quantity'],5)

    def test_merge_moves_history_and_fittings(self):
        self.issue(quantity=1)
        old=self.service.list_cadets(search='test@example.edu')[0]
        new=self.service.save_cadet(cadet_name='Test, A, Cadet',cadet_email='correct@example.edu')
        self.service.save_cadet_size_entry(cadet_id=old['cadet_id'],size_label='Coat',size_value='40 R')
        self.service.merge_cadet_profiles(new['cadet_id'],old['cadet_id'],ADMIN)
        with self.service.database.connect() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM cadets WHERE cadet_id=?',(old['cadet_id'],)).fetchone())
            self.assertEqual(c.execute('SELECT cadet_id FROM transactions WHERE barcode_id=?',(self.item['barcode_id'],)).fetchone()[0],new['cadet_id'])
            self.assertEqual(c.execute('SELECT cadet_id FROM cadet_size_entries WHERE size_label=?',('Coat',)).fetchone()[0],new['cadet_id'])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_report_has_period_and_loans(self):
        self.issue(loan_due_date=str(date.today()))
        report=self.service.export_monday_report(date(2026,9,7))
        self.assertEqual(report.suffix, '.html')
        doc=report.read_text(encoding='utf-8')
        self.assertIn('2026-08-31 through 2026-09-06',doc)
        self.assertIn('Current Loans',doc)
        self.assertIn('Test Coat',doc)


if __name__=='__main__':unittest.main()
