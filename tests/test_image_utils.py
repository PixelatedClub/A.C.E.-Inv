from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from inventory_app.image_utils import (
    PNG_SIGNATURE,
    read_gif_frame_durations,
    read_png_dimensions,
    scaled_dimensions,
    write_png_icon,
)
from inventory_app.ui import InventoryApp


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LocalImageUtilitiesTests(unittest.TestCase):
    def test_bundled_startup_gif_durations_match_expected_animation(self) -> None:
        path = PROJECT_ROOT / "portable_data" / "startup_assets" / "startup_animation.gif"
        durations = read_gif_frame_durations(path)
        self.assertEqual(len(durations), 31)
        self.assertEqual(sum(durations), 2700)
        self.assertEqual(durations[:3], [100, 100, 100])

    def test_startup_animation_composites_optimized_gif_frames(self) -> None:
        path = PROJECT_ROOT / "portable_data" / "startup_assets" / "startup_animation.gif"
        root = tk.Tk()
        root.withdraw()
        try:
            frames, durations = InventoryApp._load_startup_animation(root, path)
            self.assertEqual(len(frames), len(durations))
            self.assertEqual(len(frames), 31)
            self.assertTrue(all(frame.width() == 960 for frame in frames))
            self.assertTrue(all(frame.height() == 540 for frame in frames))

            # Frame 5 is stored as a partial GIF update. The red heart lies
            # outside that update and must still be present in the completed frame.
            self.assertFalse(frames[5].transparency_get(680, 50))
            self.assertEqual(frames[5].get(680, 50), (230, 72, 46))
        finally:
            root.destroy()

    def test_png_dimensions_and_proportional_display_scaling(self) -> None:
        path = PROJECT_ROOT / "portable_data" / "window_icon.png"
        image_bytes = path.read_bytes()
        width, height = read_png_dimensions(image_bytes)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        scaled_width, scaled_height = scaled_dimensions(width, height, max_width=32, max_height=32)
        self.assertLessEqual(scaled_width, 32)
        self.assertLessEqual(scaled_height, 32)
        self.assertAlmostEqual(width / height, scaled_width / scaled_height, places=1)

    def test_png_can_be_wrapped_as_a_windows_icon_without_pillow(self) -> None:
        source = PROJECT_ROOT / "portable_data" / "window_icon.png"
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "app_icon.ico"
            write_png_icon(source, destination)
            icon_bytes = destination.read_bytes()

        self.assertEqual(icon_bytes[:6], b"\x00\x00\x01\x00\x01\x00")
        self.assertEqual(icon_bytes[22:30], PNG_SIGNATURE)


if __name__ == "__main__":
    unittest.main()
