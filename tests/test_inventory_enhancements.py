from __future__ import annotations

import tempfile
import unittest
import gc
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.services import InventoryError, InventoryService


class InventoryEnhancementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.service = InventoryService(
            AppSettings(
                db_path=str(root / "portable" / "inventory.db"),
                backup_interval_ops=1000,
            )
        )

    def tearDown(self) -> None:
        self.service = None  # type: ignore[assignment]
        gc.collect()
        self.temporary_directory.cleanup()

    def _save_item(self, *, variant: str, item_name: str, quantity: int = 2) -> dict[str, object]:
        return self.service.save_generated_barcode(
            category="Insignia",
            variant=variant,
            item_type="Test Rank",
            item_name=item_name,
            units_per_barcode=quantity,
        )

    def test_rank_catalog_contains_all_three_styles_and_eight_ranks(self) -> None:
        with self.service.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT item_name, size, subcategory
                FROM wings_catalog
                WHERE source = 'A.C.E. Rank Catalog'
                ORDER BY item_no
                """
            ).fetchall()

        self.assertEqual(len(rows), 24)
        self.assertEqual(len({row["item_name"] for row in rows}), 3)
        self.assertEqual(len({row["size"] for row in rows}), 8)
        self.assertEqual(len({row["subcategory"] for row in rows}), 3)

    def test_new_barcode_reuses_lowest_available_number(self) -> None:
        first = self._save_item(variant="First", item_name="First Test Item")
        second = self._save_item(variant="Second", item_name="Second Test Item")
        self.assertEqual(first["barcode_id"], "A0000001")
        self.assertEqual(second["barcode_id"], "A0000002")

        self.service.delete_item(barcode_id="A0000001")
        preview = self.service.preview_generated_barcode(
            category="Insignia",
            variant="Third",
            item_type="Test Rank",
            item_name="Third Test Item",
        )
        self.assertEqual(preview["barcode_id"], "A0000001")

    def test_existing_barcode_can_be_edited_to_total_twelve(self) -> None:
        record = self._save_item(variant="Captain", item_name="Hard Blues Rank")
        updated = self.service.update_item(
            barcode_id=str(record["barcode_id"]),
            item_name="Hard Blues Rank",
            category="Insignia",
            variant="C/Capt",
            item_type="Hard Blues Ranks",
            total_quantity=12,
            notes="Updated without creating a replacement barcode.",
        )

        self.assertEqual(updated["total_quantity"], 12)
        self.assertEqual(updated["available_quantity"], 12)
        self.assertEqual(updated["barcode_id"], record["barcode_id"])

    def test_total_cannot_be_reduced_below_units_checked_out(self) -> None:
        record = self._save_item(variant="OCP", item_name="OCP Rank Patch", quantity=3)
        self.service.checkout_item(
            barcode_id=str(record["barcode_id"]),
            cadet_name="User, A, Tester",
            cadet_email="tester@example.com",
            quantity=2,
            approved_by={"role": "CADRE", "display_name": "CADRE", "admin_id": None},
        )

        with self.assertRaisesRegex(InventoryError, "currently checked out"):
            self.service.update_item(
                barcode_id=str(record["barcode_id"]),
                item_name="OCP Rank Patch",
                category="Insignia",
                variant="OCP",
                item_type="OCP Rank Patches",
                total_quantity=1,
            )

    def test_custom_item_autofill_includes_values_already_in_use(self) -> None:
        self.service.create_manual_item(
            barcode_id="CUSTOM-0001",
            item_name="Custom Ceremonial Item",
            category="Ceremonial Gear",
            variant="Standard",
            item_type="Honor Guard Accessories",
            quantity=1,
        )

        categories = {
            value.casefold() for value in self.service.list_catalog_field_values("category")
        }
        subcategories = {
            value.casefold()
            for value in self.service.list_catalog_field_values("subcategory")
        }
        self.assertIn("ceremonial gear", categories)
        self.assertIn("honor guard accessories", subcategories)


if __name__ == "__main__":
    unittest.main()
