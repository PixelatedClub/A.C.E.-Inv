import gc
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from inventory_app import config
from inventory_app.usb_portable import (MARKER,atomic_json,new_marker,validate_package,locate_package,rebase_intake)
from inventory_app.usb_setup import configure_computer,launch_registered,validate_backup_location,create_shortcut,machine_settings


class UsbSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.drive=self.base/'drive-one';self.root=self.drive/'ACE';self.root.mkdir(parents=True)
        self.data=self.root/'portable_data';self.data.mkdir()
        (self.root/'A.C.E.exe').write_bytes(b'fixture-application')
        atomic_json(self.root/'app_settings.json',dict(db_path='portable_data/inventory.db'))
        with closing(sqlite3.connect(self.data/'inventory.db')) as c:
            for table in ('items','cadets','transactions'):
                c.execute('CREATE TABLE '+table+'(id INTEGER PRIMARY KEY,value TEXT)');c.execute('INSERT INTO '+table+' VALUES(1,?)',(table,))
            c.commit()
        self.marker=new_marker();atomic_json(self.root/MARKER,self.marker)
        self.reg=dict(package_id=self.marker['package_id'],relative_folder='ACE',volume_serial='',last_root=str(self.root),backup_folder=str(self.base/'backup'),cic_enabled=False)
        self.registry=self.base/'registry.json';self.device=self.base/'device.json'
        atomic_json(self.registry,dict(schema='ace.usb.registry.v1',packages={self.marker['package_id']:self.reg}))
    def tearDown(self):
        gc.collect();self.temp.cleanup()
    def test_health_check_is_read_only(self):
        before=(self.data/'inventory.db').read_bytes()
        self.assertEqual(validate_package(self.root)['database'],self.data/'inventory.db')
        self.assertEqual(before,(self.data/'inventory.db').read_bytes())
    def test_missing_database_does_not_create_empty_inventory(self):
        (self.data/'inventory.db').unlink()
        with self.assertRaisesRegex(ValueError,'missing'):validate_package(self.root)
        self.assertFalse((self.data/'inventory.db').exists())
    def test_wrong_database_settings_and_corruption_block(self):
        atomic_json(self.root/'app_settings.json',dict(db_path=str(self.base/'laptop.db')))
        with self.assertRaises(ValueError):validate_package(self.root)
        atomic_json(self.root/'app_settings.json',dict(db_path='portable_data/inventory.db'))
        (self.data/'inventory.db').write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):validate_package(self.root)
    def test_letter_change_uses_package_identity(self):
        drive2=self.base/'drive-two';drive2.mkdir();moved=drive2/'ACE'
        shutil.copytree(self.root,moved)
        self.assertEqual(locate_package(self.reg,[drive2]),moved)
    def test_missing_wrong_or_duplicate_packages_never_launch(self):
        start=Mock()
        with self.assertRaisesRegex(ValueError,'not found'):
            launch_registered(self.marker['package_id'],registry_path=self.registry,device_path=self.device,roots=[],start=start)
        start.assert_not_called();self.assertFalse(self.device.exists())
        with self.assertRaises(ValueError):locate_package(dict(self.reg,package_id=new_marker()['package_id']),[self.drive])
        drive2=self.base/'drive-two';shutil.copytree(self.root,drive2/'ACE')
        with self.assertRaisesRegex(ValueError,'More than one'):locate_package(self.reg,[self.drive,drive2])
    def test_volume_identity_is_checked(self):
        with patch('inventory_app.usb_portable.volume_serial',return_value='WRONG'):
            with self.assertRaises(ValueError):locate_package(dict(self.reg,volume_serial='EXPECTED'),[self.drive])
    def test_launcher_rebases_device_paths_preserves_preferences(self):
        atomic_json(self.device,dict(alternate_icons_enabled=True,unrelated='keep'))
        start=Mock()
        launch_registered(self.marker['package_id'],registry_path=self.registry,device_path=self.device,roots=[self.drive],start=start)
        start.assert_called_once_with([str(self.root/'A.C.E.exe'),'--usb-package',self.marker['package_id']],cwd=str(self.root))
        saved=json.loads(self.device.read_text());self.assertEqual(saved['unrelated'],'keep')
        self.assertEqual(saved['cic_microsoft']['database_path'],str(self.data/'inventory.db'))
        secret=saved['cic_microsoft']['secret']
        launch_registered(self.marker['package_id'],registry_path=self.registry,device_path=self.device,roots=[self.drive],start=start)
        self.assertEqual(json.loads(self.device.read_text())['cic_microsoft']['secret'],secret)
    def test_same_package_cic_rebases_but_other_database_is_rejected(self):
        profile=self.data/'cic_microsoft_profile.json';profile.write_text('{}')
        stored=dict(package_id=self.marker['package_id'],database_path='Z:/ACE/portable_data/inventory.db',profile_path='Z:/ACE/portable_data/cic_microsoft_profile.json')
        result=rebase_intake(stored,self.root,self.data/'inventory.db')
        self.assertEqual(result['profile_path'],str(profile))
        with self.assertRaises(ValueError):rebase_intake(dict(stored,package_id='different'),self.root,self.data/'inventory.db')
    def test_setup_creates_verified_backup_and_no_inventory_edits(self):
        source=self.base/'Set Up A.C.E.exe';source.write_bytes(b'fixture-setup')
        before=(self.data/'inventory.db').read_bytes()
        with patch('inventory_app.usb_setup.validate_backup_location'),patch('inventory_app.usb_setup.volume_serial',return_value='TEST'),patch('inventory_app.usb_setup.create_shortcut',return_value=self.base/'ACE USB.lnk') as shortcut:
            result=configure_computer(self.root,self.base/'backup',launcher_source=source,
                registry_path=self.registry,launcher_path=self.base/'installed/launcher.exe',device_path=self.device,desktop=self.base)
        self.assertEqual(before,(self.data/'inventory.db').read_bytes());shortcut.assert_called_once()
        with zipfile.ZipFile(result['backup']) as archive:
            self.assertEqual(archive.namelist(),['inventory.db']);self.assertIsNone(archive.testzip())
        self.assertEqual((self.base/'installed/launcher.exe').read_bytes(),source.read_bytes())
    def test_backup_on_usb_is_rejected(self):
        with self.assertRaises(ValueError):validate_backup_location(self.root,self.root/'backups')
    def test_config_guard_precedes_creation_or_fallback(self):
        from main import startup_settings
        with patch.object(config,'BASE_DIR',self.root),patch.object(config,'CONFIG_PATH',self.root/'app_settings.json'):
            (self.data/'inventory.db').unlink()
            with self.assertRaises(ValueError):config.load_settings()
            self.assertFalse((self.data/'inventory.db').exists())
        with patch('main.BASE_DIR',self.root),patch('main.load_settings') as load:
            with self.assertRaises(ValueError):startup_settings(['--usb-package','wrong-package'])
            load.assert_not_called()
    def test_setup_window_builds_without_installing(self):
        from inventory_app.usb_setup import build_window
        with patch('inventory_app.usb_setup.default_backup',return_value=self.base/'backup'):
            window=build_window(self.root);window.withdraw();window.update();window.destroy()
    def test_setup_blocks_while_application_is_running(self):
        guard=Mock();guard.__enter__=Mock(return_value=Mock(is_primary=False));guard.__exit__=Mock(return_value=False)
        with patch('inventory_app.single_instance.SingleInstanceGuard.acquire',return_value=guard),patch('inventory_app.usb_setup._configure_computer') as install:
            with self.assertRaisesRegex(ValueError,'close'):configure_computer(self.root,self.base/'backup')
            install.assert_not_called()
    def test_unrelated_shortcut_is_preserved(self):
        original=self.base/'ACE USB.lnk';original.write_bytes(b'unrelated shortcut')
        recovery=self.base/'recovery';recovery.mkdir()
        with patch('inventory_app.usb_setup.shortcut_details',return_value=dict(target='C:/other-program.exe')),patch('inventory_app.usb_setup.powershell'):
            result=create_shortcut(self.base,self.base/'launcher.exe',self.reg,recovery)
        self.assertNotEqual(result,original);self.assertEqual(original.read_bytes(),b'unrelated shortcut')
    def test_first_setup_preserves_existing_intake_receipt_key(self):
        old={'cic_microsoft':{'database_path':str(self.data/'inventory.db'),'secret':'existing-local-receipt-key'}}
        saved=machine_settings(old,self.reg,self.root)
        self.assertEqual(saved['cic_microsoft']['secret'],'existing-local-receipt-key')
    def test_another_usb_shortcut_is_preserved(self):
        original=self.base/'ACE USB.lnk';original.write_bytes(b'another USB shortcut')
        recovery=self.base/'recovery';recovery.mkdir();launcher=self.base/'launcher.exe'
        with patch('inventory_app.usb_setup.shortcut_details',return_value=dict(target=str(launcher),arguments='--launch other-package')),patch('inventory_app.usb_setup.powershell'):
            result=create_shortcut(self.base,launcher,self.reg,recovery)
        self.assertNotEqual(result,original);self.assertEqual(original.read_bytes(),b'another USB shortcut')
    def test_equivalent_windows_launcher_paths_update_same_shortcut(self):
        original=self.base/'ACE USB.lnk';original.write_bytes(b'ACE shortcut')
        recovery=self.base/'recovery';recovery.mkdir();(self.base/'nested').mkdir()
        launcher=self.base/'nested/../launcher.exe';launcher.write_bytes(b'fixture launcher')
        with patch('inventory_app.usb_setup.shortcut_details',return_value=dict(target=str(launcher.resolve()),arguments='--launch '+self.reg['package_id'])),patch('inventory_app.usb_setup.powershell'):
            result=create_shortcut(self.base,launcher,self.reg,recovery)
        self.assertEqual(result,original);self.assertEqual((recovery/'ACE USB.lnk').read_bytes(),b'ACE shortcut')


if __name__=='__main__':unittest.main()
