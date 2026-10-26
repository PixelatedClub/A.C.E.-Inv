from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.services import InventoryError, InventoryService


class AcquiredItemsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.service = InventoryService(
            AppSettings(
                db_path=str(root / "portable" / "inventory.db"),
                backup_interval_ops=1000,
            )
        )
        self.admin = {"role": "CADRE", "display_name": "CADRE", "admin_id": None}

    def tearDown(self) -> None:
        self.service = None  # type: ignore[assignment]
        gc.collect()
        self.temporary_directory.cleanup()

    def _checkout_pt_gear(
        self,
        *,
        total_quantity: int,
        checkout_quantity: int,
        cadet_name: str = "Buyer, A, Cadet",
        cadet_email: str = "buyer@example.com",
    ) -> tuple[str, int, list[int]]:
        item = self.service.save_generated_barcode(
            category="PTG",
            variant="M",
            item_type="Shirts",
            item_name="PT Shirt",
            units_per_barcode=total_quantity,
        )
        barcode = str(item["barcode_id"])
        self.service.checkout_item(
            barcode_id=barcode,
            cadet_name=cadet_name,
            cadet_email=cadet_email,
            quantity=checkout_quantity,
            approved_by=self.admin,
            condition_notes="Initial issue",
        )
        cadet = next(row for row in self.service.list_cadets() if row["email"] == cadet_email)
        cadet_id = int(cadet["cadet_id"])
        transaction_ids = [
            int(row["transaction_id"])
            for row in self.service.get_cadet_details(cadet_id)["current_items"]
        ]
        return barcode, cadet_id, transaction_ids

    def test_purchased_items_leave_inventory_and_remain_in_cadet_history(self) -> None:
        barcode, cadet_id, transaction_ids = self._checkout_pt_gear(
            total_quantity=4,
            checkout_quantity=3,
        )

        processed = self.service.acquire_checked_out_items(
            cadet_id=cadet_id,
            transaction_ids=transaction_ids[:2],
            disposition="Purchased",
            approved_by=self.admin,
            notes="Cadet paid for non-returnable PT gear.",
        )

        self.assertEqual(len(processed), 2)
        item = self.service.get_item(barcode)
        self.assertIsNotNone(item)
        self.assertEqual(item["total_quantity"], 2)
        self.assertEqual(item["available_quantity"], 1)
        self.assertIn("Purchased", item["notes"])

        details = self.service.get_cadet_details(cadet_id)
        self.assertEqual(len(details["current_items"]), 1)
        self.assertEqual(details["acquired_items"], 2)
        purchased_rows = [row for row in details["history"] if row["disposition"] == "Purchased"]
        self.assertEqual(len(purchased_rows), 2)
        self.assertTrue(all(row["closed_time"] for row in purchased_rows))
        self.assertTrue(all(row["closed_by_role"] == "CADRE" for row in purchased_rows))

        checked_columns, checked_rows = self.service.get_report("Checked Out Items")
        self.assertIn("barcode_id", checked_columns)
        self.assertEqual(len(checked_rows), 1)

        report_columns, report_rows = self.service.get_report("Acquired / Purchased Items")
        self.assertIn("disposition", report_columns)
        self.assertEqual(len(report_rows), 2)
        self.assertTrue(all(row["cadet_email"] == "buyer@example.com" for row in report_rows))
        self.assertTrue(all(row["disposition"] == "Purchased" for row in report_rows))

        saved_cadet = next(row for row in self.service.list_cadets() if row["cadet_id"] == cadet_id)
        self.assertEqual(saved_cadet["open_items"], 1)
        self.assertEqual(saved_cadet["acquired_items"], 2)
        self.assertEqual(self.service.dashboard_summary()["checked_out_units"], 1)

    def test_permanent_issue_can_remove_last_unit_and_barcode_can_be_restocked(self) -> None:
        barcode, cadet_id, transaction_ids = self._checkout_pt_gear(
            total_quantity=1,
            checkout_quantity=1,
        )

        self.service.acquire_checked_out_items(
            cadet_id=cadet_id,
            transaction_ids=transaction_ids,
            disposition="Acquired / Permanent Issue",
            approved_by=self.admin,
            notes="Non-returnable skin-contact item.",
        )

        item = self.service.get_item(barcode)
        self.assertEqual(item["total_quantity"], 0)
        self.assertEqual(item["available_quantity"], 0)
        self.assertEqual(item["status"], "Available")
        self.assertEqual(self.service.get_cadet_details(cadet_id)["current_items"], [])
        self.assertEqual(self.service.get_report("Checked Out Items")[1], [])

        self.service.restock_item(barcode_id=barcode, quantity=1, notes="Replacement stock")
        restocked = self.service.get_item(barcode)
        self.assertEqual(restocked["total_quantity"], 1)
        self.assertEqual(restocked["available_quantity"], 1)

    def test_acquisition_rejects_checkout_owned_by_another_cadet(self) -> None:
        barcode, _owner_id, transaction_ids = self._checkout_pt_gear(
            total_quantity=2,
            checkout_quantity=1,
        )
        other = self.service.save_cadet(
            cadet_name="Other, B, Cadet",
            cadet_email="other@example.com",
        )

        with self.assertRaisesRegex(InventoryError, "selected cadet"):
            self.service.acquire_checked_out_items(
                cadet_id=int(other["cadet_id"]),
                transaction_ids=transaction_ids,
                disposition="Purchased",
                approved_by=self.admin,
            )

        item = self.service.get_item(barcode)
        self.assertEqual(item["total_quantity"], 2)
        self.assertEqual(item["available_quantity"], 1)

    def test_normal_return_is_identified_as_returned(self) -> None:
        barcode, cadet_id, _transaction_ids = self._checkout_pt_gear(
            total_quantity=1,
            checkout_quantity=1,
        )
        self.service.return_item(
            barcode_id=barcode,
            quantity=1,
            approved_by=self.admin,
        )

        history = self.service.get_cadet_details(cadet_id)["history"]
        self.assertEqual(history[0]["disposition"], "Returned")
        self.assertTrue(history[0]["closed_time"])

    def test_undo_batch_survives_restart_and_preserves_later_restock(self):
        barcode,cadet_id,ids=self._checkout_pt_gear(total_quantity=4,checkout_quantity=3)
        with self.service.database.connect() as c:
            before=[dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY transaction_id')]
        self.service.set_loan_deadline(ids,'2026-12-31','Training loan',self.admin)
        with self.service.database.connect() as c:
            original=[dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY transaction_id')]
        self.service.acquire_checked_out_items(cadet_id=cadet_id,transaction_ids=ids[:2],
            disposition='Purchased',approved_by=self.admin,notes='Mistaken purchase')
        self.service.restock_item(barcode_id=barcode,quantity=2,notes='Later shipment')
        self.service=InventoryService(self.service.settings)
        action=self.service.latest_acquisition(cadet_id)
        self.assertEqual(action['transaction_ids'],sorted(ids[:2]))
        result=self.service.undo_latest_acquisition(cadet_id=cadet_id,approved_by=self.admin,
            expected_transaction_ids=action['transaction_ids'])
        self.assertEqual(result['units'],2)
        item=self.service.get_item(barcode)
        self.assertEqual((item['total_quantity'],item['available_quantity']),(6,3))
        with self.service.database.connect() as c:
            self.assertEqual([dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY transaction_id')],original)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM loan_events WHERE action='Acquisition undone'").fetchone()[0],2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM acquisition_actions WHERE undone_at<>''").fetchone()[0],1)
        self.assertEqual(self.service.get_report('Acquired / Purchased Items')[1],[])
        report=self.service.get_weekly_activity_report_data()
        self.assertEqual(report['summary']['recovered_units'],2)
        with self.assertRaises(InventoryError):
            self.service.undo_latest_acquisition(cadet_id=cadet_id,approved_by=self.admin)

    def test_undo_rejects_changed_batch_without_partial_stock_restoration(self):
        barcode,cadet_id,ids=self._checkout_pt_gear(total_quantity=2,checkout_quantity=2)
        self.service.acquire_checked_out_items(cadet_id=cadet_id,transaction_ids=ids,
            disposition='Acquired / Permanent Issue',approved_by=self.admin)
        with self.service.database.connect() as c:
            c.execute('UPDATE transactions SET condition_notes=? WHERE transaction_id=?',('Later correction',ids[0]));c.commit()
        with self.assertRaisesRegex(InventoryError,'changed'):
            self.service.undo_latest_acquisition(cadet_id=cadet_id,approved_by=self.admin)
        self.assertEqual(self.service.get_item(barcode)['total_quantity'],0)
        self.assertEqual(len(self.service.get_report('Acquired / Purchased Items')[1]),2)

    def test_legacy_acquisition_uses_original_backup(self):
        barcode,cadet_id,ids=self._checkout_pt_gear(total_quantity=2,checkout_quantity=1)
        original=self.service.get_cadet_details(cadet_id)['current_items']
        self.service.acquire_checked_out_items(cadet_id=cadet_id,transaction_ids=ids,
            disposition='Purchased',approved_by=self.admin)
        with self.service.database.connect() as c:
            c.execute('DELETE FROM acquisition_actions');c.commit()
        self.service.undo_latest_acquisition(cadet_id=cadet_id,approved_by=self.admin)
        self.assertEqual((self.service.get_item(barcode)['total_quantity'],self.service.get_item(barcode)['available_quantity']),(2,1))
        self.assertEqual(self.service.get_cadet_details(cadet_id)['current_items'],original)

    def test_two_batches_in_same_second_undo_in_action_order(self):
        from unittest.mock import patch
        barcode,cadet_id,ids=self._checkout_pt_gear(total_quantity=2,checkout_quantity=2)
        with patch('inventory_app.services.utc_now',return_value='2026-10-05T10:00:00-05:00'):
            for transaction in (max(ids),min(ids)):
                self.service.acquire_checked_out_items(cadet_id=cadet_id,transaction_ids=[transaction],
                    disposition='Purchased',approved_by=self.admin)
        self.assertEqual(self.service.latest_acquisition(cadet_id)['transaction_ids'],[min(ids)])
        self.service.undo_latest_acquisition(cadet_id=cadet_id,approved_by=self.admin)
        self.assertEqual(self.service.latest_acquisition(cadet_id)['transaction_ids'],[max(ids)])


if __name__ == "__main__":
    unittest.main()
