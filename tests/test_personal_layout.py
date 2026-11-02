import copy,gc,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from inventory_app.config import AppSettings
from inventory_app.ui import InventoryApp
from inventory_app.appearance import apply_preferences,identity,DEFAULTS,open_preferences
from inventory_app.layout import ScrollablePanel

class PersonalLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        with patch.object(InventoryApp,'_begin_startup_sequence',lambda self:None):
            self.app=InventoryApp(AppSettings(db_path=str(Path(self.temp.name)/'test.db')))
        self.app.attributes('-alpha',0);self.app.geometry('1000x640');self.app.deiconify();self.app.update()
        self.saved={}
        self.read=patch('inventory_app.appearance.load_device_settings',side_effect=lambda:copy.deepcopy(self.saved));self.read.start()
    def tearDown(self):
        self.read.stop()
        for callback in self.app.tk.call('after','info'):self.app.after_cancel(callback)
        self.app.destroy();self.app.service=None;self.app=None;gc.collect();self.temp.cleanup()
    def login(self,number):
        self.app._set_current_admin(dict(admin_id=number,role='ADMIN CADET',display_name='User '+str(number)))
        self.app.update()
    def test_theme_applies_only_to_authenticated_owner_and_resets_on_switch(self):
        a=self.app
        self.assertIsNone(identity(a));original=a.cget('background')
        self.login(3);key=identity(a)
        self.saved={'user_appearance':{key:dict(DEFAULTS,background='#202020',accent='#55aaff',lists='#181818')}}
        self.app.current_admin=None;apply_preferences(a)
        self.assertEqual(a.cget('background'),original)
        self.login(3);self.assertEqual(a.cget('background'),'#202020')
        self.assertEqual(a.style.lookup('TLabel','foreground'),'#ffffff')
        self.login(4);self.assertEqual(a.cget('background'),original)
        self.login(3);self.assertEqual(a.cget('background'),'#202020')
    def test_vertical_panels_and_scrolling_forms_keep_checkout_action_accessible(self):
        a=self.app;self.login(3)
        self.saved={'user_appearance':{identity(a):dict(DEFAULTS,layout='vertical')}}
        apply_preferences(a);a.notebook.select(a.items_tab);a.update()
        self.assertEqual(str(a.items_split.cget('orient')),'vertical')
        before=a.items_split.sash_coord(0)[1];a.items_split.sash_place(0,0,before+20);a.update()
        self.assertGreater(a.items_split.sash_coord(0)[1],before)
        a.notebook.select(a.checkout_tab);a.update()
        def descendants(parent):
            for child in parent.winfo_children():yield child;yield from descendants(child)
        submit=next(w for w in descendants(a.checkout_tab) if w.winfo_class()=='TButton' and w.cget('text')=='Check Out Queued Items')
        self.assertLessEqual(submit.winfo_rooty()+submit.winfo_height(),a.winfo_rooty()+a.winfo_height())
        a.notebook.select(a.settings_tab);a.update()
        panel=next(w for w in a.settings_tab.winfo_children() if isinstance(w,ScrollablePanel))
        self.assertGreater(panel.body.winfo_reqheight(),panel.canvas.winfo_height())
        panel.canvas.yview_moveto(1);a.update();self.assertGreater(panel.canvas.yview()[0],0)
    def test_loan_reminders_do_not_open_global_popups(self):
        self.login(3)
        with patch.object(self.app,'_show_info') as info,patch.object(self.app,'refresh_loans') as refresh:
            self.app._check_loan_reminders();refresh.assert_called_once();info.assert_not_called()
