from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.services import InventoryService
from inventory_app.wings_catalog import WINGS_CATALOG
from inventory_app.wings_catalog_official_import import WINGS_OFFICIAL_IMPORT_ADDITIONS


class WingsCatalogTests(unittest.TestCase):
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

    def test_complete_official_catalog_has_unique_item_numbers(self) -> None:
        rows = [
            row
            for row in (*WINGS_CATALOG, *WINGS_OFFICIAL_IMPORT_ADDITIONS)
            if str(row["item_no"]).isdigit()
        ]
        item_numbers = [str(row["item_no"]) for row in rows]

        self.assertEqual(len(rows), 500)
        self.assertEqual(len(item_numbers), len(set(item_numbers)))
        self.assertTrue({"106", "150", "461", "4718", "5095"}.issubset(item_numbers))

    def test_complete_official_catalog_is_seeded_into_a_clean_database(self) -> None:
        self.assertEqual(self.service.count_wings_catalog_items(), 500)
        with self.service.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT item_no, source, is_wings
                FROM wings_catalog
                WHERE item_no IN ('106', '150', '461', '4718', '5095')
                ORDER BY CAST(item_no AS INTEGER)
                """
            ).fetchall()

        self.assertEqual([row["item_no"] for row in rows], ["106", "150", "461", "4718", "5095"])
        self.assertTrue(all(row["is_wings"] == 1 for row in rows))
        self.assertTrue(all("Official Import" in row["source"] for row in rows))

    def test_september_additions_are_available_without_adding_inventory(self) -> None:
        expected = {'985': '36L', '987': '36S', '991': '40L', '994': '42L',
                    '1002': '46S', '4559': '14 REGULAR', '4560': '14 SHORT'}
        for number, size in expected.items():
            row = self.service.get_wings_catalog_item(number)
            self.assertEqual(row['size'], size)
            self.assertEqual(row['is_wings'], 1)
            self.assertIn('15 Sep 26', row['source'])
        with self.service.database.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM items').fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
