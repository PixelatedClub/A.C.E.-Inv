from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from inventory_app.ui import InventoryApp


class _IconChoiceHarness:
    def __init__(self, alternate_icons_enabled: bool) -> None:
        self.alternate_icons_enabled = alternate_icons_enabled

    @staticmethod
    def _window_icon_path(_key: str) -> Path:
        return Path("available.ico")


class AlternateIconTests(unittest.TestCase):
    def test_normal_mode_uses_one_in_four_thousand_rare_odds(self) -> None:
        harness = _IconChoiceHarness(alternate_icons_enabled=False)
        with patch("inventory_app.ui.random.randrange", return_value=1) as randrange:
            InventoryApp._random_window_icon_key(harness)  # type: ignore[arg-type]
        randrange.assert_called_once_with(4000)

    def test_alternate_mode_uses_one_in_four_rare_odds(self) -> None:
        harness = _IconChoiceHarness(alternate_icons_enabled=True)
        with patch("inventory_app.ui.random.randrange", return_value=1) as randrange:
            InventoryApp._random_window_icon_key(harness)  # type: ignore[arg-type]
        randrange.assert_called_once_with(4)


if __name__ == "__main__":
    unittest.main()
