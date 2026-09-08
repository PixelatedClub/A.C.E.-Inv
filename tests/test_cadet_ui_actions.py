from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from inventory_app.ui import InventoryApp


class _Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _run_action(action, *, success_message, on_success):
    result = action()
    on_success(result)


class CadetUiActionTests(unittest.TestCase):
    def _app(self) -> SimpleNamespace:
        service = Mock()
        service.save_cadet.return_value = {"cadet_id": 25}
        service.update_cadet.return_value = {"cadet_id": 1}
        return SimpleNamespace(
            selected_cadet_id=1,
            cadet_cache={
                1: {
                    "cadet_id": 1,
                    "full_name": "Dawkins, C, Roman",
                    "email": "rdc0053@auburn.edu",
                }
            },
            cadet_form_email_var=_Value("lzj0066@auburn.edu"),
            cadet_search_var=_Value("Dawkins"),
            cadet_tree=SimpleNamespace(
                get_children=Mock(return_value=("25",)),
                selection_set=Mock(),
                see=Mock(),
            ),
            service=service,
            _compose_cadet_form_name=Mock(return_value="Johnson, A, Luke"),
            _run_action=_run_action,
            _show_error=Mock(),
            refresh_cadets=Mock(),
            refresh_cadet_fitting_index=Mock(),
            _load_cadet_details=Mock(),
        )

    def test_save_new_cadet_never_updates_selected_record(self) -> None:
        app = self._app()

        InventoryApp._save_cadet(app)

        app.service.save_cadet.assert_called_once_with(
            cadet_name="Johnson, A, Luke",
            cadet_email="lzj0066@auburn.edu",
        )
        app.service.update_cadet.assert_not_called()
        self.assertEqual(app.selected_cadet_id, 25)
        self.assertEqual(app.cadet_search_var.get(), "")
        app.cadet_tree.selection_set.assert_called_once_with("25")

    def test_update_requires_a_selected_cadet(self) -> None:
        app = self._app()
        app.selected_cadet_id = None

        InventoryApp._update_selected_cadet(app)

        app._show_error.assert_called_once()
        app.service.update_cadet.assert_not_called()

    @patch("inventory_app.ui.messagebox.askyesno", return_value=True)
    def test_update_selected_cadet_uses_guarded_update(self, confirm: Mock) -> None:
        app = self._app()

        InventoryApp._update_selected_cadet(app)

        confirm.assert_called_once()
        app.service.update_cadet.assert_called_once_with(
            cadet_id=1,
            cadet_name="Johnson, A, Luke",
            cadet_email="lzj0066@auburn.edu",
        )
        app.service.save_cadet.assert_not_called()


if __name__ == "__main__":
    unittest.main()
