from __future__ import annotations

import gc
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path

from inventory_app.config import AppSettings
from inventory_app.services import InventoryError, InventoryService


class WeeklyReportsAndFittingTests(unittest.TestCase):
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

    def _create_checked_out_item(self, suffix: str) -> int:
        item = self.service.save_generated_barcode(
            category="Test Gear",
            variant=f"Size {suffix}",
            item_type="Weekly Report Test",
            item_name=f"Weekly Item {suffix}",
            units_per_barcode=1,
        )
        self.service.checkout_item(
            barcode_id=str(item["barcode_id"]),
            cadet_name="Weekly, A, Cadet",
            cadet_email="weekly@example.com",
            quantity=1,
            approved_by={"role": "CADRE", "display_name": "CADRE", "admin_id": None},
        )
        with self.service.database.connect() as connection:
            row = connection.execute(
                "SELECT MAX(transaction_id) AS transaction_id FROM transactions"
            ).fetchone()
        return int(row["transaction_id"])

    def test_reports_filter_by_inclusive_date_range(self) -> None:
        checkout_in_range = self._create_checked_out_item("A")
        closed_in_range = self._create_checked_out_item("B")
        old_open_checkout = self._create_checked_out_item("C")

        with self.service.database.connect() as connection:
            connection.execute(
                "UPDATE transactions SET checkout_time = ? WHERE transaction_id = ?",
                ("2026-08-18T09:00:00-05:00", checkout_in_range),
            )
            connection.execute(
                """
                UPDATE transactions
                SET checkout_time = ?, return_time = ?, disposition = 'Returned'
                WHERE transaction_id = ?
                """,
                (
                    "2026-08-10T09:00:00-05:00",
                    "2026-08-19T15:00:00-05:00",
                    closed_in_range,
                ),
            )
            connection.execute(
                "UPDATE transactions SET checkout_time = ? WHERE transaction_id = ?",
                ("2026-08-01T09:00:00-05:00", old_open_checkout),
            )
            connection.commit()

        _, history = self.service.get_report(
            "Transaction History",
            start_date="2026-08-17",
            end_date="2026-08-23",
        )
        self.assertEqual(
            {int(row["transaction_id"]) for row in history},
            {checkout_in_range, closed_in_range},
        )

        _, checked_out = self.service.get_report(
            "Checked Out Items",
            start_date="2026-08-17",
            end_date="2026-08-23",
        )
        self.assertEqual(len(checked_out), 1)
        self.assertEqual(checked_out[0]["checkout_time"], "2026-08-18T09:00:00-05:00")

    def test_report_date_validation_is_clear(self) -> None:
        with self.assertRaisesRegex(InventoryError, "YYYY-MM-DD"):
            self.service.get_report("Transaction History", start_date="08/17/2026")
        with self.assertRaisesRegex(InventoryError, "before start"):
            self.service.get_report(
                "Transaction History",
                start_date="2026-08-24",
                end_date="2026-08-17",
            )

    def test_cadet_fitting_sizes_can_be_saved_updated_and_deleted(self) -> None:
        cadet = self.service.save_cadet(
            cadet_name="Fitting, A, Cadet",
            cadet_email="fitting@example.com",
        )
        saved = self.service.save_cadet_size_entry(
            cadet_id=int(cadet["cadet_id"]),
            size_label="Blues Trousers",
            size_value="32R",
            category="Pants/Skirt",
            catalog_item_no="1234",
            notes="Verified during fitting.",
        )
        self.assertEqual(saved["size_value"], "32R")
        self.assertEqual(saved["category"], "Pants/Skirt")
        self.assertEqual(saved["catalog_item_no"], "1234")

        updated = self.service.save_cadet_size_entry(
            cadet_id=int(cadet["cadet_id"]),
            size_entry_id=int(saved["size_entry_id"]),
            size_label="Blues Trousers",
            size_value="33R",
            category="Pants/Skirt",
            catalog_item_no="1234",
            notes="Adjusted after try-on.",
        )
        self.assertEqual(updated["size_value"], "33R")
        details = self.service.get_cadet_details(int(cadet["cadet_id"]))
        self.assertEqual(len(details["size_entries"]), 1)
        self.assertEqual(details["size_entries"][0]["notes"], "Adjusted after try-on.")

        self.service.delete_cadet_size_entry(
            cadet_id=int(cadet["cadet_id"]),
            size_entry_id=int(saved["size_entry_id"]),
        )
        self.assertEqual(self.service.list_cadet_size_entries(int(cadet["cadet_id"])), [])

    def test_fitting_catalog_filters_by_category_and_shows_current_availability(self) -> None:
        created = self.service.save_generated_barcode(
            category="ignored",
            variant="ignored",
            item_type="ignored",
            item_name="ignored",
            wings_item_no="871",
            units_per_barcode=4,
        )
        self.assertEqual(created["available_quantity"], 4)

        categories = self.service.list_cadet_fitting_categories()
        self.assertIn("Insignia", categories)
        options = self.service.list_cadet_fitting_options(
            category="Insignia",
            search="871 first lt female",
        )
        matching = [row for row in options if row["item_no_key"] == "871"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["available_quantity"], 4)
        self.assertEqual(matching[0]["total_quantity"], 4)
        self.assertEqual(matching[0]["size"], "C/1ST LT")
        self.assertIn("FEMALE", matching[0]["fitting_label"])

    def test_inventory_changes_report_tracks_additions_edits_and_deletions(self) -> None:
        barcode = self.service.create_manual_item(
            barcode_id="AUDIT-0001",
            item_name="Audit Test Cap",
            category="Accessories",
            variant="7 1/4",
            item_type="Headwear",
            quantity=2,
        )
        self.service.restock_item(barcode_id=barcode, quantity=3)
        self.service.update_item(
            barcode_id=barcode,
            item_name="Audit Test Patrol Cap",
            category="Accessories",
            variant="7 1/4",
            item_type="Headwear",
            total_quantity=5,
        )

        columns, rows = self.service.get_report("Inventory Changes")
        self.assertIn("quantity_change", columns)
        matching = [row for row in rows if row["barcode_id"] == barcode]
        self.assertEqual(
            {row["action"] for row in matching},
            {"New Item Added", "Quantity Added", "Item Details Edited"},
        )
        self.assertEqual(sum(int(row["quantity_change"]) for row in matching), 5)
        summary = self.service.summarize_report("Inventory Changes", matching)
        self.assertIn("5 unit(s) added", summary)

        self.service.delete_item(barcode_id=barcode)
        _, rows_after_delete = self.service.get_report("Inventory Changes")
        deleted = [
            row
            for row in rows_after_delete
            if row["barcode_id"] == barcode and row["action"] == "Item Deleted"
        ]
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]["quantity_change"], -5)

    def test_readable_report_spreadsheet_has_summary_and_friendly_headers(self) -> None:
        self.service.create_manual_item(
            barcode_id="REPORT-0001",
            item_name="Readable Report Item",
            category="Test",
            variant="Medium",
            item_type="Test Gear",
            quantity=4,
        )
        columns, rows = self.service.get_report("Inventory Changes")
        export_path = self.settings.database_path.parent / "readable_inventory_changes.xlsx"
        self.service.export_report_spreadsheet(
            export_path,
            report_name="Inventory Changes",
            columns=columns,
            rows=rows,
            start_date="2026-08-24",
            end_date="2026-08-24",
        )

        self.assertTrue(export_path.exists())
        with zipfile.ZipFile(export_path) as workbook:
            workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
            detail_xml = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
        self.assertIn('name="Summary"', workbook_xml)
        self.assertIn('name="Inventory Changes"', workbook_xml)
        self.assertIn("Date &amp; Time", detail_xml)
        self.assertIn("Qty Change", detail_xml)
        self.assertIn("WINGS / Local Item #", detail_xml)

    def test_weekly_activity_report_combines_narratives_metrics_and_detail_tabs(self) -> None:
        barcode = self.service.create_manual_item(
            barcode_id="WEEKLY-0001",
            item_name="Weekly Combined Report Item",
            category="Test Gear",
            variant="Large",
            item_type="Uniform",
            quantity=3,
        )
        cadet = self.service.save_cadet(
            cadet_name="Report, A, Cadet",
            cadet_email="report-cadet@example.com",
        )
        self.service.save_cadet_size_entry(
            cadet_id=int(cadet["cadet_id"]),
            size_label="Blues Service Coat",
            size_value="40R",
            category="Other",
            catalog_item_no="3189",
        )
        self.service.checkout_item(
            barcode_id=barcode,
            cadet_name="Report, A, Cadet",
            cadet_email="report-cadet@example.com",
            quantity=1,
            approved_by={"role": "CADRE", "display_name": "CADRE", "admin_id": None},
        )
        self.service.return_item(
            barcode_id=barcode,
            quantity=1,
            approved_by={"role": "CADRE", "display_name": "CADRE", "admin_id": None},
        )

        report_end = date.today() + timedelta(days=1)
        report_start = report_end - timedelta(days=6)
        before_counts = self._operational_table_counts()
        report = self.service.get_weekly_activity_report_data(
            start_date=report_start.isoformat(),
            end_date=report_end.isoformat(),
            bluf="BLUF test narrative",
            major_activities="MAs test narrative",
            coa_validation="COA validation test narrative",
        )

        self.assertEqual(report["summary"]["routine_units_added"], 3)
        self.assertEqual(report["summary"]["checkout_transactions"], 1)
        self.assertEqual(report["summary"]["closed_transactions"], 1)
        self.assertEqual(report["summary"]["fitting_entries"], 1)
        self.assertEqual(report["summary"]["cadets_fitted"], 1)
        self.assertEqual(report["summary"]["new_cadets"], 1)
        self.assertEqual(
            [sheet["sheet_name"] for sheet in report["sheets"]],
            [
                "Weekly Summary",
                "Inventory Changes",
                "New Catalog Items",
                "Transactions",
                "Fittings",
                "New Cadet Records",
                "Data Quality",
            ],
        )
        fitting_sheet = report["sheets"][4]
        self.assertEqual(fitting_sheet["rows"][0]["Report Category"], "Blues Service Coats")

        export_path = self.service.export_weekly_activity_spreadsheet(
            start_date=report_start.isoformat(),
            end_date=report_end.isoformat(),
            bluf="BLUF test narrative",
            major_activities="MAs test narrative",
            coa_validation="COA validation test narrative",
            open_after=False,
        )
        self.assertTrue(export_path.exists())
        with zipfile.ZipFile(export_path) as workbook:
            workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
            summary_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        for sheet_name in (
            "Weekly Summary",
            "Inventory Changes",
            "New Catalog Items",
            "Transactions",
            "Fittings",
            "New Cadet Records",
            "Data Quality",
        ):
            self.assertIn(f'name="{sheet_name}"', workbook_xml)
        self.assertIn("BLUF test narrative", summary_xml)
        self.assertIn("MAs test narrative", summary_xml)
        self.assertIn("COA validation test narrative", summary_xml)
        self.assertEqual(self._operational_table_counts(), before_counts)

    def _operational_table_counts(self) -> dict[str, int]:
        tables = ("items", "inventory_changes", "cadets", "cadet_size_entries", "transactions")
        with self.service.database.connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }

    def test_every_inventory_row_receives_official_or_local_item_number(self) -> None:
        barcode = self.service.create_manual_item(
            barcode_id="CUSTOM-LOCAL-1",
            item_name="Det Polo",
            category="DETACHMENT",
            variant="M",
            item_type="POLO",
            quantity=2,
        )
        with self.service.database.connect() as connection:
            item = connection.execute(
                "SELECT wings_item_no FROM items WHERE barcode_id = ?",
                (barcode,),
            ).fetchone()
        self.assertTrue(str(item["wings_item_no"]).startswith("LOCAL-AUTO-"))
        self.assertEqual(self.service.inventory_item_number_audit()["missing_rows"], 0)
        self.assertEqual(self.service.list_wings_export_rows(), [])
        complete_rows = self.service.list_complete_inventory_export_rows()
        self.assertEqual(len(complete_rows), 1)
        self.assertTrue(str(complete_rows[0]["Item No"]).startswith("LOCAL-AUTO-"))


if __name__ == "__main__":
    unittest.main()
