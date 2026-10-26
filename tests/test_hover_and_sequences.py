import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from inventory_app.hover import install_hover, HOVER_TAG
from inventory_app.shortcuts import DirectShortcuts


class InteractionTests(unittest.TestCase):
    def test_hover_preserves_selection_and_status_tags(self):
        tree=Mock();callbacks={};rows={'a':('overdue',),'b':()}
        tree.bind.side_effect=lambda event,fn,**kw:callbacks.update({event:fn})
        tree.exists.side_effect=lambda row:row in rows
        def item(row,option=None,**kw):
            if 'tags' in kw:rows[row]=kw['tags']
            return rows[row]
        tree.item.side_effect=item
        tree.identify_region.return_value='cell';tree.identify_row.return_value='a'
        install_hover(tree)
        callbacks['<Motion>'](SimpleNamespace(x=1,y=1))
        self.assertIn(HOVER_TAG,rows['a']);self.assertIn('overdue',rows['a'])
        tree.identify_row.return_value='b'
        callbacks['<Motion>'](SimpleNamespace(x=1,y=2))
        self.assertEqual(rows['a'],('overdue',))
        callbacks['<Leave>']()
        self.assertEqual(rows['b'],())
        tree.selection_set.assert_not_called();tree.focus.assert_not_called()

    def test_direct_ctrl_letters_and_modal_guard(self):
        app=Mock();app.grab_current.return_value=None;action=Mock()
        sequence=DirectShortcuts(app,{'g':action})
        key=lambda name,state=0:sequence.key(SimpleNamespace(keysym=name,state=state))
        self.assertIsNone(key('g'))
        self.assertIsNone(key('k',4))
        self.assertEqual(key('g',4),'break');action.assert_called_once()
        with patch('inventory_app.shortcuts.sys.platform','win32'):
            self.assertEqual(key('g',12),'break')
            self.assertIsNone(key('g',4|0x20000))
            self.assertIsNone(key('g',4|0x10))
        self.assertEqual(action.call_count,2)
        self.assertEqual(key('G',5),'break');self.assertEqual(action.call_count,3)
        app.grab_current.return_value=object()
        self.assertIsNone(key('g',4));self.assertEqual(action.call_count,3)
