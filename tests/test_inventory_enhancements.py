from __future__ import annotations

import tempfile
import unittest
import gc
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.services import InventoryError, InventoryService, RANK_CATALOG_VERSION


class InventoryEnhancementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.settings = AppSettings(
            db_path=str(root / "portable" / "inventory.db"),
            backup_interval_ops=1000,
        )
        self.service = InventoryService(self.settings)

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

    def test_rank_catalog_uses_official_wings_cloth_ranks(self) -> None:
        with self.service.database.connect() as connection:
            local_rows = connection.execute(
                """
                SELECT item_no, item_name, size, subcategory, sex
                FROM wings_catalog
                WHERE source = 'A.C.E. Rank Catalog'
                ORDER BY item_no
                """
            ).fetchall()
            official_cloth_rows = connection.execute(
                """
                SELECT item_no, item_name, size, sex
                FROM wings_catalog
                WHERE item_no IN ('867', '868', '869', '870', '871', '872',
                                  '873', '874', '875', '876', '877', '878')
                  AND is_wings = 1
                ORDER BY CAST(item_no AS INTEGER)
                """
            ).fetchall()

        self.assertEqual(len(local_rows), 20)
        self.assertEqual(len({row["item_name"] for row in local_rows}), 4)
        self.assertEqual(len({row["size"] for row in local_rows}), 8)
        self.assertEqual(len({row["subcategory"] for row in local_rows}), 4)

        mens_local_cloth = [row for row in local_rows if row["item_no"].startswith("LOCAL-RANK-SBM-")]
        womens_local_cloth = [row for row in local_rows if row["item_no"].startswith("LOCAL-RANK-SBW-")]
        self.assertEqual(len(mens_local_cloth), 2)
        self.assertEqual(len(womens_local_cloth), 2)
        self.assertTrue(all(row["sex"] == "M" for row in mens_local_cloth))
        self.assertTrue(all(row["sex"] == "F" for row in womens_local_cloth))
        self.assertTrue(all("Cloth Blues" in row["item_name"] for row in mens_local_cloth + womens_local_cloth))

        self.assertEqual(len(official_cloth_rows), 12)
        self.assertEqual({row["sex"] for row in official_cloth_rows}, {"F", "M"})
        self.assertTrue(all("CLOTH" in row["item_name"] for row in official_cloth_rows))
        self.assertFalse(
            any("Soft Blues" in row["item_name"] for row in local_rows + official_cloth_rows)
        )

    def test_legacy_soft_blues_inventory_migrates_to_official_wings_item(self) -> None:
        with self.service.database.connect() as connection:
            connection.execute("DELETE FROM ace_feature_flags WHERE feature_key = ?", (RANK_CATALOG_VERSION,))
            connection.execute(
                """
                INSERT INTO wings_catalog(
                    item_no, item_name, size, category, subcategory, sex,
                    stock_number, uom, writeoffs, source, is_wings
                ) VALUES (
                    'LOCAL-RANK-SBM-C2LT', 'Men''s Soft Blues Rank', 'C/2d Lt',
                    'Insignia', 'Men''s Soft Blues Ranks', 'M', '', 'EA', '',
                    'A.C.E. Rank Catalog', 0
                )
                """
            )
            connection.execute(
                """
                INSERT INTO items(
                    barcode_id, wings_item_no, item_name, category, variant, item_type,
                    status, notes, total_quantity, available_quantity, created_at, updated_at
                ) VALUES (
                    'A0000001', 'LOCAL-RANK-SBM-C2LT', 'Men''s Soft Blues Rank',
                    'Insignia', 'C/2D LT', 'Men''s Soft Blues Ranks', 'Available',
                    'Counted stock', 5, 5, '2026-08-18T00:00:00', '2026-08-18T00:00:00'
                )
                """
            )
            connection.commit()

        self.service.checkout_item(
            barcode_id="A0000001",
            cadet_name="Tester, A, Cadet",
            cadet_email="tester@example.com",
            quantity=2,
            approved_by={"role": "CADRE", "display_name": "CADRE", "admin_id": None},
        )

        self.service = InventoryService(self.settings)

        with self.service.database.connect() as connection:
            item = connection.execute(
                "SELECT * FROM items WHERE barcode_id = 'A0000001'"
            ).fetchone()
            open_transactions = connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE barcode_id = 'A0000001' AND return_time IS NULL"
            ).fetchone()[0]
            local_catalog_row = connection.execute(
                "SELECT 1 FROM wings_catalog WHERE item_no = 'LOCAL-RANK-SBM-C2LT'"
            ).fetchone()

        self.assertEqual(item["wings_item_no"], "878")
        self.assertEqual(item["item_name"], "INSIGNIA,RANK,OFFICER MALE CLOTH")
        self.assertEqual(item["variant"], "C/2ND LT")
        self.assertEqual(item["item_type"], "INSIGNIA,RANK,OFFICER MALE CLOTH")
        self.assertEqual(item["total_quantity"], 5)
        self.assertEqual(item["available_quantity"], 3)
        self.assertIn("Counted stock", item["notes"])
        self.assertIn("official WINGS item 878", item["notes"])
        self.assertEqual(open_transactions, 2)
        self.assertIsNone(local_catalog_row)

        export_row = next(
            row for row in self.service.list_wings_export_rows() if row["Item No"] == "0000000878"
        )
        self.assertEqual(export_row["Qty Issued"], 2)
        self.assertEqual(export_row["Qty Available"], 3)
        self.assertEqual(export_row["Total in Inventory"], 5)

    def test_official_cloth_rank_with_blank_subcategory_can_generate_inventory(self) -> None:
        created = self.service.save_generated_barcode(
            category="ignored",
            variant="ignored",
            item_type="ignored",
            item_name="ignored",
            wings_item_no="871",
            units_per_barcode=4,
        )

        self.assertEqual(created["wings_item_no"], "871")
        self.assertEqual(created["item_name"], "INSIGNIA,RANK,OFFICER FEMALE CLOTH")
        self.assertEqual(created["variant"], "C/1ST LT")
        self.assertEqual(created["item_type"], "INSIGNIA,RANK,OFFICER FEMALE CLOTH")

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
