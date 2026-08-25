from __future__ import annotations

import gc
import sqlite3
import tempfile
import unittest
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.database import utc_now
from inventory_app.services import InventoryError, InventoryService


class DuplicatePreventionTests(unittest.TestCase):
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

    def _save_item(
        self,
        *,
        variant: str = "7-1/4",
        item_name: str = "Duplicate Test Patrol Cap",
        quantity: int = 2,
    ) -> dict[str, object]:
        return self.service.save_generated_barcode(
            category="Accessories",
            variant=variant,
            item_type="Headwear",
            item_name=item_name,
            units_per_barcode=quantity,
        )

    def test_generated_identical_item_reuses_and_restocks_existing_barcode(self) -> None:
        first = self._save_item(quantity=2)
        second = self.service.save_generated_barcode(
            category=" accessories ",
            variant=" 7-1/4 ",
            item_type=" headwear ",
            item_name="duplicate test patrol cap",
            units_per_barcode=3,
        )

        self.assertEqual(second["barcode_id"], first["barcode_id"])
        self.assertEqual(second["action"], "restocked")
        self.assertEqual(second["total_quantity"], 5)
        with self.service.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        self.assertEqual(count, 1)

    def test_manual_identical_item_is_rejected_with_existing_barcode(self) -> None:
        first = self._save_item()

        with self.assertRaisesRegex(InventoryError, str(first["barcode_id"])):
            self.service.create_manual_item(
                barcode_id="MANUAL-0002",
                item_name="DUPLICATE TEST PATROL CAP",
                category="ACCESSORIES",
                variant="7-1/4",
                item_type="HEADWEAR",
                quantity=1,
            )

    def test_distinct_wings_item_numbers_remain_separate(self) -> None:
        for item_no in ("900001", "900002"):
            self.service.add_wings_catalog_item(
                item_no=item_no,
                item_name="Catalog Test Shirt",
                size="Medium",
                category="Test Gear",
                subcategory="Shirts",
                sex="",
                stock_number="",
                uom="EA",
                source="Duplicate prevention regression test",
            )

        first = self.service.save_generated_barcode(
            category="ignored",
            variant="ignored",
            item_type="ignored",
            item_name="ignored",
            wings_item_no="900001",
            units_per_barcode=1,
        )
        second = self.service.save_generated_barcode(
            category="ignored",
            variant="ignored",
            item_type="ignored",
            item_name="ignored",
            wings_item_no="900002",
            units_per_barcode=1,
        )

        self.assertNotEqual(first["barcode_id"], second["barcode_id"])
        self.assertEqual(first["wings_item_no"], "900001")
        self.assertEqual(second["wings_item_no"], "900002")

    def test_edit_cannot_make_two_barcodes_identical(self) -> None:
        first = self._save_item(variant="SMALL", item_name="Duplicate Edit Item")
        second = self._save_item(variant="LARGE", item_name="Duplicate Edit Item")

        with self.assertRaisesRegex(InventoryError, str(first["barcode_id"])):
            self.service.update_item(
                barcode_id=str(second["barcode_id"]),
                item_name="Duplicate Edit Item",
                category="Accessories",
                variant="Small",
                item_type="Headwear",
                total_quantity=2,
            )

    def test_lowest_available_barcode_skips_reserved_aliases(self) -> None:
        first = self._save_item(variant="FIRST", item_name="First Alias Test Item")
        self.assertEqual(first["barcode_id"], "A0000001")
        with self.service.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO barcode_aliases(alias_barcode_id, canonical_barcode_id, created_at, reason)
                VALUES ('A0000002', 'A0000001', ?, 'Regression test')
                """,
                (utc_now(),),
            )
            connection.commit()

        preview = self.service.preview_generated_barcode(
            category="Accessories",
            variant="THIRD",
            item_type="Headwear",
            item_name="Third Alias Test Item",
        )
        self.assertEqual(preview["barcode_id"], "A0000003")

    def test_database_rejects_alias_redirect_for_active_barcode(self) -> None:
        first = self._save_item(variant="FIRST", item_name="First Active Item")
        second = self._save_item(variant="SECOND", item_name="Second Active Item")

        with self.assertRaisesRegex(sqlite3.IntegrityError, "active inventory barcode"):
            with self.service.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO barcode_aliases(alias_barcode_id, canonical_barcode_id, created_at, reason)
                    VALUES (?, ?, ?, 'Invalid redirect test')
                    """,
                    (second["barcode_id"], first["barcode_id"], utc_now()),
                )

    def test_same_cadet_name_and_email_reuses_one_record(self) -> None:
        first = self.service.save_cadet(
            cadet_name="Example, A, Cadet",
            cadet_email="cadet@example.com",
        )
        second = self.service.save_cadet(
            cadet_name=" example, a, cadet ",
            cadet_email=" CADET@EXAMPLE.COM ",
        )

        self.assertEqual(second["cadet_id"], first["cadet_id"])
        with self.service.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM cadets").fetchone()[0]
        self.assertEqual(count, 1)

    def test_database_rejects_case_only_duplicate_cadet_email(self) -> None:
        self.service.save_cadet(
            cadet_name="Example, A, Cadet",
            cadet_email="cadet@example.com",
        )

        with self.assertRaises(sqlite3.IntegrityError):
            with self.service.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO cadets(full_name, email, created_at, updated_at)
                    VALUES ('Other, B, Cadet', 'CADET@EXAMPLE.COM', ?, ?)
                    """,
                    (utc_now(), utc_now()),
                )


if __name__ == "__main__":
    unittest.main()
