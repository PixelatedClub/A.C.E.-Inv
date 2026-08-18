from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.services import InventoryError, InventoryService


class CadetReturnTests(unittest.TestCase):
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
        item = self.service.save_generated_barcode(
            category="PTG",
            variant="M",
            item_type="Shirts",
            item_name="PT Shirt",
            units_per_barcode=4,
        )
        self.barcode = str(item["barcode_id"])
        self.service.checkout_item(
            barcode_id=self.barcode,
            cadet_name="Alpha, A, Cadet",
            cadet_email="alpha@example.com",
            quantity=2,
            approved_by=self.admin,
            condition_notes="Issued to Alpha",
        )
        self.service.checkout_item(
            barcode_id=self.barcode,
            cadet_name="Bravo, B, Cadet",
            cadet_email="bravo@example.com",
            quantity=1,
            approved_by=self.admin,
            condition_notes="Issued to Bravo",
        )
        cadets = {row["email"]: row for row in self.service.list_cadets()}
        self.alpha_id = int(cadets["alpha@example.com"]["cadet_id"])
        self.bravo_id = int(cadets["bravo@example.com"]["cadet_id"])

    def tearDown(self) -> None:
        self.service = None  # type: ignore[assignment]
        gc.collect()
        self.temporary_directory.cleanup()

    def _current_transaction_ids(self, cadet_id: int) -> list[int]:
        return [
            int(row["transaction_id"])
            for row in self.service.get_cadet_details(cadet_id)["current_items"]
        ]

    def test_return_closes_only_selected_units_for_named_cadet(self) -> None:
        alpha_transactions = self._current_transaction_ids(self.alpha_id)

        returned = self.service.return_cadet_items(
            cadet_id=self.alpha_id,
            transaction_ids=alpha_transactions[:1],
            approved_by=self.admin,
            condition_notes="Washed and inspected",
        )

        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0]["cadet_id"], self.alpha_id)
        self.assertEqual(returned[0]["disposition"], "Returned")
        self.assertEqual(len(self.service.get_cadet_details(self.alpha_id)["current_items"]), 1)
        self.assertEqual(len(self.service.get_cadet_details(self.bravo_id)["current_items"]), 1)
        item = self.service.get_item(self.barcode)
        self.assertEqual(item["total_quantity"], 4)
        self.assertEqual(item["available_quantity"], 2)

        alpha_history = self.service.get_cadet_details(self.alpha_id)["history"]
        returned_history = [row for row in alpha_history if row["disposition"] == "Returned"]
        self.assertEqual(len(returned_history), 1)
        self.assertIn("Washed and inspected", returned_history[0]["condition_notes"])
        self.assertEqual(returned_history[0]["closed_by_role"], "CADRE")

        report_columns, report_rows = self.service.get_report("Transaction History")
        self.assertIn("disposition", report_columns)
        report_row = next(
            row for row in report_rows if row["transaction_id"] == returned[0]["transaction_id"]
        )
        self.assertEqual(report_row["disposition"], "Returned")
        self.assertEqual(report_row["cadet_email"], "alpha@example.com")
        self.assertEqual(report_row["closed_by_role"], "CADRE")

    def test_shared_barcode_cannot_return_another_cadets_checkout(self) -> None:
        bravo_transaction = self._current_transaction_ids(self.bravo_id)[0]

        with self.assertRaisesRegex(InventoryError, "selected cadet"):
            self.service.return_cadet_items(
                cadet_id=self.alpha_id,
                transaction_ids=[bravo_transaction],
                approved_by=self.admin,
            )

        self.assertEqual(len(self.service.get_cadet_details(self.alpha_id)["current_items"]), 2)
        self.assertEqual(len(self.service.get_cadet_details(self.bravo_id)["current_items"]), 1)
        self.assertEqual(self.service.get_item(self.barcode)["available_quantity"], 1)

    def test_mixed_owner_return_is_rejected_atomically(self) -> None:
        alpha_transaction = self._current_transaction_ids(self.alpha_id)[0]
        bravo_transaction = self._current_transaction_ids(self.bravo_id)[0]

        with self.assertRaisesRegex(InventoryError, "selected cadet"):
            self.service.return_cadet_items(
                cadet_id=self.alpha_id,
                transaction_ids=[alpha_transaction, bravo_transaction],
                approved_by=self.admin,
            )

        self.assertEqual(len(self.service.get_cadet_details(self.alpha_id)["current_items"]), 2)
        self.assertEqual(len(self.service.get_cadet_details(self.bravo_id)["current_items"]), 1)
        self.assertEqual(self.service.get_item(self.barcode)["available_quantity"], 1)

    def test_return_requires_at_least_one_selected_checkout(self) -> None:
        with self.assertRaisesRegex(InventoryError, "Select at least one"):
            self.service.return_cadet_items(
                cadet_id=self.alpha_id,
                transaction_ids=[],
                approved_by=self.admin,
            )


if __name__ == "__main__":
    unittest.main()
