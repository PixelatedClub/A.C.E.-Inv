from tests.test_checkout_drafts_and_index import CheckoutDraftTests
from unittest.mock import patch
from inventory_app.services import InventoryError
from inventory_app.ui import InventoryApp
from inventory_app.local_uniforms import standard_local

class NamesAndTabsTests(CheckoutDraftTests):
    def test_tab_number_reused_after_close(self):
        a=self.app
        second=a._new_checkout_draft();third=a._new_checkout_draft();a.update()
        a.checkout_notebook.select(second);a.update();a._close_checkout_draft();a.update()
        new=a._new_checkout_draft();a.update()
        self.assertEqual(a.checkout_notebook.tab(new,'text'),'Checkout 2')
        self.assertEqual(a.checkout_drafts[str(third)]['number'],3)
    def test_checkout_without_initial_and_saved_initial_preserved(self):
        a=self.app
        a.service.create_manual_item(barcode_id='A0000001',item_name='Cap',category='OCP',variant='7',item_type='Cap',quantity=3)
        a.checkout_last_name_var.set('Smith');a.checkout_first_name_var.set('Jane');a.checkout_email_var.set('jane@example.com')
        self.queue('A0000001',1)
        with patch.object(a,'_show_error') as error,patch.object(a,'_show_info'):
            a._submit_checkout();error.assert_not_called()
        cadet=next(r for r in a.service.list_cadets() if r['email']=='jane@example.com')
        self.assertEqual(cadet['full_name'],'Smith, Jane')
        self.assertEqual(InventoryApp._split_name(cadet['full_name']),('Smith','','Jane'))
        a.service.save_cadet(cadet_name='Smith, A, Jane',cadet_email='jane@example.com')
        a.service.checkout_item(barcode_id='A0000001',cadet_name='Smith, Jane',cadet_email='jane@example.com',quantity=1,approved_by=a.current_admin)
        self.assertEqual(next(r for r in a.service.list_cadets() if r['email']=='jane@example.com')['full_name'],'Smith, A, Jane')
        with self.assertRaises(InventoryError):a.service.save_cadet(cadet_name='Smith',cadet_email='bad@example.com')
    def test_unknown_width_is_not_assumed_regular(self):
        row=dict(item_name='bots',item_type='BOOTS',category='OCP',variant='12.5',sex='M')
        result=standard_local(row)
        self.assertEqual(result['item_name'],"OCP Boots, Men's")
        self.assertEqual(result['variant'],'12.5 (width unspecified)')
