import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from inventory_app.shortcuts import queue_selected
from inventory_app.ui import InventoryApp


class Var:
    def __init__(self, value=''): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class CheckoutShortcutsTests(unittest.TestCase):
    def app(self, available=2, status='Available'):
        app = SimpleNamespace(
            checkout_scan_var=Var('unfinished scan'), checkout_qty_var=Var('7'),
            checkout_queue={}, checkout_summary_var=Var(),
            service=Mock(), _show_error=Mock(), _focus_checkout_scan=Mock(),
            _update_checkout_queue_tree=Mock(), notebook=Mock(), checkout_notebook=Mock(),
            checkout_tab='checkout', standard_checkout_tab='standard')
        app.service.get_barcode_context.side_effect = lambda barcode: dict(
            barcode_id=barcode, item_name='Cap', category='OCP', variant='7',
            item_type='Cap', available_quantity=available, status=status)
        app._queue_checkout_barcode=lambda: InventoryApp._queue_checkout_barcode(app)
        return app

    def test_stages_one_per_selection_preserving_input_and_without_writes(self):
        app=self.app(); tree=Mock(); tree.selection.return_value=('A0000001','A0000002')
        self.assertEqual(queue_selected(app, tree), 'break')
        self.assertEqual([row['quantity'] for row in app.checkout_queue.values()], [1,1])
        self.assertEqual(app.checkout_scan_var.get(), 'unfinished scan')
        self.assertEqual(app.checkout_qty_var.get(), '7')
        self.assertEqual([call[0] for call in app.service.mock_calls],
                         ['get_barcode_context','get_barcode_context'])

    def test_repeated_add_stops_at_available(self):
        app=self.app(1); tree=Mock(); tree.selection.return_value=('A0000001',)
        queue_selected(app, tree); queue_selected(app, tree)
        self.assertEqual(app.checkout_queue['A0000001']['quantity'], 1)
        app._show_error.assert_called_once()

    def test_rejects_unavailable_lost_retired(self):
        for available,status in [(0,'Available'),(2,'Lost'),(2,'Retired')]:
            with self.subTest(status=status):
                app=self.app(available,status); tree=Mock(); tree.selection.return_value=('A0000001',)
                queue_selected(app, tree)
                self.assertEqual(app.checkout_queue, {})
                app._show_error.assert_called_once()

    def test_empty_selection_does_not_navigate(self):
        app=self.app(); tree=Mock(); tree.selection.return_value=()
        queue_selected(app, tree)
        app.notebook.select.assert_not_called()
