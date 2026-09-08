from __future__ import annotations

import unittest
from types import SimpleNamespace
from types import MethodType
from unittest.mock import Mock

from inventory_app.ui import InventoryApp


class _Value:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class GeneratorUiActionTests(unittest.TestCase):
    def test_quick_find_payload_and_selection_replace_previous_item_type(self) -> None:
        service = Mock()
        service.list_wings_catalog.return_value = [
            {
                "item_no": "0000001234",
                "item_name": "SHIRT, MENS",
                "size": "15.5",
                "category": "SHIRTS",
                "subcategory": "SHORT SLEEVE",
                "sex": "M",
                "stock_number": "",
            }
        ]
        app = SimpleNamespace(service=service)

        results = InventoryApp._quick_find_matches(app, "mens shirt")

        self.assertEqual(len(results), 1)
        label, payload = results[0]
        self.assertIn("SHIRT, MENS", label)
        self.assertEqual(payload[-1], "SHORT SLEEVE")

        variables = {
            "generator_quick_find_var": _Value(),
            "generator_wings_item_no_var": _Value(),
            "generator_category_var": _Value(),
            "generator_item_name_var": _Value(),
            "generator_item_type_var": _Value("STALE SUBCATEGORY"),
            "generator_selected_item_var": _Value(),
            "generator_size_label_var": _Value(),
            "generator_variant_var": _Value(),
        }
        result_list = SimpleNamespace(curselection=Mock(return_value=()))
        apply_app = SimpleNamespace(
            **variables,
            quick_find_result_map={label: payload},
            generator_quick_find_results=result_list,
            generator_size_combo={},
            _set_status=Mock(),
        )

        InventoryApp._apply_quick_find_result(apply_app)

        self.assertEqual(apply_app.generator_item_type_var.get(), "SHORT SLEEVE")
        self.assertEqual(apply_app.generator_wings_item_no_var.get(), "0000001234")

    def test_enter_rebuilds_results_before_applying_selection(self) -> None:
        class _Listbox:
            def __init__(self) -> None:
                self.items = []
                self.selected = ()

            def delete(self, _start, _end) -> None:
                self.items.clear()
                self.selected = ()

            def insert(self, _end, value) -> None:
                self.items.append(value)

            def selection_set(self, index) -> None:
                self.selected = (index,)

            def activate(self, _index) -> None:
                return

            def curselection(self):
                return self.selected

            def get(self, index):
                return self.items[index]

        stale_payload = ("OLD", "Old item", "Old item", "OLD", "1", "OLD TYPE")
        fresh_payload = ("SHIRTS", "New item", "New item", "M", "2", "FRESH TYPE")
        result_list = _Listbox()
        app = SimpleNamespace(
            generator_quick_find_var=_Value("new search"),
            generator_wings_item_no_var=_Value(),
            generator_category_var=_Value(),
            generator_item_name_var=_Value(),
            generator_item_type_var=_Value("OLD TYPE"),
            generator_selected_item_var=_Value(),
            generator_size_label_var=_Value(),
            generator_variant_var=_Value(),
            quick_find_result_map={"Old result": stale_payload},
            generator_quick_find_results=result_list,
            generator_size_combo={},
            _quick_find_matches=Mock(return_value=[("New result", fresh_payload)]),
            _set_status=Mock(),
        )
        app._apply_quick_find_result = MethodType(InventoryApp._apply_quick_find_result, app)

        result = InventoryApp._search_and_apply_quick_find_result(app)

        self.assertEqual(result, "break")
        app._quick_find_matches.assert_called_once_with("new search")
        self.assertEqual(app.generator_item_name_var.get(), "New item")
        self.assertEqual(app.generator_item_type_var.get(), "FRESH TYPE")


if __name__ == "__main__":
    unittest.main()
