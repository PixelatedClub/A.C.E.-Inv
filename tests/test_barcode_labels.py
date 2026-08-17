from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inventory_app.barcode_utils import (
    BARCODE_QUIET_ZONE,
    LABEL_HEIGHT,
    LABEL_WIDTH,
    barcode_bars,
    write_direct_label_pdf,
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


if __name__ == "__main__":
    unittest.main()
