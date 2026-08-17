from __future__ import annotations

import unittest

from inventory_app.barcode_utils import extract_scanned_barcode


class ScannerInputTests(unittest.TestCase):
    def test_timestamp_noise_is_removed(self) -> None:
        self.assertEqual(
            extract_scanned_barcode("2026/08/18 06:53:48 A0000001 2026/08/18 06:53:48"),
            "A0000001",
        )

    def test_exact_and_code39_wrapped_barcodes_are_accepted(self) -> None:
        self.assertEqual(extract_scanned_barcode("A0000137"), "A0000137")
        self.assertEqual(extract_scanned_barcode("*a0000137*\r\n"), "A0000137")

    def test_wings_barcode_is_extracted_from_noise(self) -> None:
        self.assertEqual(
            extract_scanned_barcode("SCAN 06:53:48 W00003FZ OK"),
            "W00003FZ",
        )

    def test_duplicate_copy_of_same_barcode_is_not_ambiguous(self) -> None:
        self.assertEqual(
            extract_scanned_barcode("A0000001 A0000001"),
            "A0000001",
        )

    def test_missing_or_conflicting_barcode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "did not contain"):
            extract_scanned_barcode("2026/08/18 06:53:48")
        with self.assertRaisesRegex(ValueError, "multiple different"):
            extract_scanned_barcode("A0000001 A0000002")


if __name__ == "__main__":
    unittest.main()
