import gc
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.graduation import graduation_dates
from inventory_app.services import InventoryError, InventoryService


ADMIN = {"role": "CADRE"}


class GraduationTests(unittest.TestCase):
    def test_date_validation_and_leap_day(self):
        self.assertEqual(
            graduation_dates("2024-02-29", already_graduated=False, today=date(2024, 1, 1)),
            (date(2024, 2, 29), date(2025, 2, 28)),
        )
        with self.assertRaises(InventoryError):
            graduation_dates("2030-01-01", already_graduated=True, today=date(2029, 1, 1))

    def test_purge_decrements_only_outstanding_units_and_runs_once(self):
        with tempfile.TemporaryDirectory() as folder:
            service = InventoryService(AppSettings(db_path=str(Path(folder) / "inventory.db")))
            item = service.save_generated_barcode(
                category="BLUES", item_type="Coat", item_name="Demo Coat",
                variant="40 R", units_per_barcode=8,
            )
            barcode = item["barcode_id"]
            for name, email, quantity in [("Example, Sam", "sam@example.edu", 3),
                                          ("Example, Jo", "jo@example.edu", 1)]:
                service.checkout_item(barcode_id=barcode, cadet_name=name, cadet_email=email,
                                      quantity=quantity, approved_by=ADMIN)
            with closing(service.database.connect()) as connection, connection:
                rows = connection.execute(
                    "SELECT transaction_id,cadet_id FROM transactions WHERE cadet_email=? ORDER BY transaction_id",
                    ("sam@example.edu",),
                ).fetchall()
                cadet_id = rows[0]["cadet_id"]
                connection.execute("UPDATE transactions SET cadet_id=NULL WHERE transaction_id=?", (rows[2][0],))
                connection.execute(
                    "INSERT INTO loan_events(event_time,transaction_id,action,details,recorded_by) VALUES(?,?,?,?,?)",
                    ("2020-01-01", rows[2][0], "Test loan", "", "CADRE"),
                )
            service.return_cadet_items(cadet_id=cadet_id, transaction_ids=[rows[0][0]], approved_by=ADMIN)
            service.acquire_checked_out_items(cadet_id=cadet_id, transaction_ids=[rows[1][0]],
                                              disposition="Acquired / Permanent Issue", approved_by=ADMIN)
            service.save_graduation(cadet_id=cadet_id, graduation_date="2020-01-01",
                                    already_graduated=True, approved_by=ADMIN)
            self.assertEqual(service.process_due_graduations(today=date(2020, 12, 31)), ([], []))
            before = service.get_item(barcode)
            completed, failures = service.process_due_graduations(today=date(2021, 1, 1))
            self.assertFalse(failures)
            self.assertEqual(completed, [{"cadet_id": cadet_id, "transactions_deleted": 3, "units_acquired": 1}])
            after = service.get_item(barcode)
            self.assertEqual(after["total_quantity"], before["total_quantity"] - 1)
            self.assertEqual(after["available_quantity"], before["available_quantity"])
            self.assertEqual(service.get_cadet_details(cadet_id)["history"], [])
            self.assertEqual(service.process_due_graduations(), ([], []))
            with closing(service.database.connect()) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM transactions").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM loan_events").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT count(*) FROM acquisition_actions").fetchone()[0], 0)
                self.assertFalse(connection.execute("PRAGMA foreign_key_check").fetchone())
            gc.collect()

    def test_cancellation_ends_pending_schedule(self):
        with tempfile.TemporaryDirectory() as folder:
            service = InventoryService(AppSettings(db_path=str(Path(folder) / "inventory.db")))
            cadet = service.save_cadet(cadet_name="Example, Sam", cadet_email="sam@example.edu")
            with self.assertRaises(InventoryError):
                service.save_graduation(cadet_id=cadet["cadet_id"], graduation_date=date.today().isoformat(),
                                        already_graduated=False, approved_by=None)
            service.save_graduation(cadet_id=cadet["cadet_id"],
                                    graduation_date=(date.today() + timedelta(days=2)).isoformat(),
                                    already_graduated=False, approved_by=ADMIN)
            service.cancel_graduation(cadet_id=cadet["cadet_id"], approved_by=ADMIN)
            self.assertIsNone(service.get_graduation(cadet["cadet_id"]))
            gc.collect()
