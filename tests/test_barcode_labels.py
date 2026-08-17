from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inventory_app.barcode_utils import (
    BARCODE_QUIET_ZONE,
    LABEL_HEIGHT,
    LABEL_WIDTH,
    LETTER_HEIGHT,
    LETTER_WIDTH,
    barcode_bars,
    write_direct_label_pdf,
    write_label_pdf,
)


class BarcodeLabelTests(unittest.TestCase):
    def test_direct_pdf_has_one_exact_two_by_one_inch_page_per_label(self) -> None:
        records = [
            {
                "barcode_id": barcode,
                "item_name": "Scanner Test",
                "category": "Insignia",
                "variant": "C/Col",
                "item_type": "OCP Rank Patches",
                "total_quantity": 1,
            }
            for barcode in ("A0000001", "A0000042", "A0012345", "A9999999")
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "labels.pdf"
            write_direct_label_pdf(path, records, "A.C.E.", title="Scanner Test")
            content = path.read_bytes()

        media_box = f"/MediaBox [0 0 {LABEL_WIDTH:.0f} {LABEL_HEIGHT:.0f}]".encode()
        self.assertEqual(content.count(media_box), 4)
        self.assertIn(b"/Count 4", content)

    def test_code39_narrow_bar_and_quiet_zone_are_suitable_for_203_dpi(self) -> None:
        _, raw_width = barcode_bars("A9999999")
        narrow_bar_points = (LABEL_WIDTH - (2 * BARCODE_QUIET_ZONE)) / raw_width
        narrow_bar_pixels = narrow_bar_points * 203 / 72

        self.assertGreaterEqual(narrow_bar_pixels, 2.0)
        self.assertGreaterEqual(BARCODE_QUIET_ZONE, narrow_bar_points * 10)

    def test_one_thousand_pls892_labels_fill_exactly_twenty_five_letter_pages(self) -> None:
        record = {
            "barcode_id": "A0000001",
            "item_name": "PLS892 Test",
            "category": "Scanner Test",
            "variant": "2 x 1",
            "item_type": "PLS892",
            "total_quantity": 1,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "pls892-1000-labels.pdf"
            write_label_pdf(
                path,
                [dict(record) for _ in range(1000)],
                "A.C.E.",
                title="PLS892 1000 Label Verification",
            )
            content = path.read_bytes()

        media_box = f"/MediaBox [0 0 {LETTER_WIDTH:.0f} {LETTER_HEIGHT:.0f}]".encode()
        self.assertEqual(content.count(media_box), 25)
        self.assertIn(b"/Count 25", content)


if __name__ == "__main__":
    unittest.main()
