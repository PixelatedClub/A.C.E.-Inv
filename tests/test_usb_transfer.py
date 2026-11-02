from contextlib import closing
import json,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from inventory_app.usb_portable import atomic_json,new_marker,MARKER,INSTALL_MARKER,DB_REL,validate_package
from inventory_app.installation import make_release,release,install_local,digest,owned_archives
from inventory_app.usb_transfer import export_to_usb,transfer_plan,PENDING

class UsbTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.usb=self.base/'usb';self.usb.mkdir();(self.usb/'portable_data').mkdir()
        self.marker=new_marker();atomic_json(self.usb/MARKER,self.marker)
        atomic_json(self.usb/'app_settings.json',dict(db_path=DB_REL,protected_backup_path='private computer path'))
        with closing(sqlite3.connect(self.usb/DB_REL)) as c:
            for table in ('items','cadets','transactions'):
                c.execute('CREATE TABLE '+table+'(id INTEGER PRIMARY KEY,value TEXT)');c.execute('INSERT INTO '+table+' VALUES(1,?)',(table,))
            c.commit()
        self.program(self.usb,'1.9.0-cic.12')
        self.backups=self.base/'backups';self.local=self.base/'installed'
        install_local(self.usb,self.local,self.marker['package_id'],self.backups)
        self.program(self.local,'1.9.0-cic.13')
        with closing(sqlite3.connect(self.local/DB_REL)) as c:c.execute("INSERT INTO transactions VALUES(2,'new saved checkout')");c.commit()
        (self.local/'portable_data/return_drafts.json').write_text('{"notes":"current return draft"}')
        (self.local/'portable_data/checkout_drafts.json').write_text('{"notes":"current checkout draft"}')
        (self.local/'device_settings.json').write_text('{"secret":"do not export"}')
        self.helper=self.base/'setup.exe';self.helper.write_bytes(b'MZnew helper')
        self.reg=dict(package_id=self.marker['package_id'],backup_folder=str(self.backups),volume_serial='')
    def tearDown(self):self.temp.cleanup()
    def program(self,root,version):
        (root/'A.C.E.exe').write_bytes(b'MZfixture-'+version.encode());atomic_json(root/'ace_release.json',make_release(version,root/'A.C.E.exe'))
    def export(self):return export_to_usb(self.local,self.reg,target=self.usb,helper=self.helper)
    def rows(self,root):
        with closing(sqlite3.connect(root/DB_REL)) as c:return c.execute('SELECT * FROM transactions ORDER BY id').fetchall()
    def test_latest_snapshot_and_drafts_export_without_changing_local_or_unrelated_files(self):
        before=digest(self.local/DB_REL);unrelated=self.usb/'personal.txt';unrelated.write_text('preserve')
        result=self.export()
        self.assertEqual(digest(self.local/DB_REL),before);self.assertEqual(self.rows(self.usb),self.rows(self.local))
        self.assertEqual(result['counts']['transactions'],2);self.assertEqual(release(self.usb)['version'],'1.9.0-cic.13')
        self.assertEqual((self.usb/'portable_data/return_drafts.json').read_bytes(),(self.local/'portable_data/return_drafts.json').read_bytes())
        self.assertFalse((self.usb/'device_settings.json').exists());self.assertEqual(unrelated.read_text(),'preserve')
        self.assertNotIn('protected_backup_path',json.loads((self.usb/'app_settings.json').read_text()))
        self.assertEqual(len(owned_archives(self.usb)),1);self.assertFalse((self.usb/PENDING).exists())
        with zipfile.ZipFile(result['backup']) as archive:
            self.assertIsNone(archive.testzip());self.assertNotIn('A.C.E.exe',archive.namelist())
            old=self.base/'old.db';old.write_bytes(archive.read('usb_previous/inventory.db'))
        with closing(sqlite3.connect(old)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)
    def test_live_wal_database_is_exported_as_a_complete_snapshot(self):
        with closing(sqlite3.connect(self.local/DB_REL)) as writer:
            writer.execute('PRAGMA journal_mode=WAL');writer.execute("INSERT INTO transactions VALUES(3,'committed WAL checkout')");writer.commit()
            self.export();self.assertEqual(self.rows(self.usb),self.rows(self.local))
        self.assertFalse(Path(str(self.usb/DB_REL)+'-wal').exists())
    def test_wrong_or_missing_usb_does_not_write(self):
        before=digest(self.usb/DB_REL);wrong=new_marker();atomic_json(self.usb/MARKER,wrong)
        with self.assertRaisesRegex(ValueError,'another'):self.export()
        self.assertEqual(digest(self.usb/DB_REL),before)
        atomic_json(self.usb/MARKER,self.marker)
        atomic_json(self.helper.parent/'setup_version.json',dict(version='1.9.0-cic.12',sha256=digest(self.helper)))
        with self.assertRaisesRegex(ValueError,'latest Set Up'):self.export()
        self.assertEqual(digest(self.usb/DB_REL),before)
        with patch('inventory_app.usb_setup._source_update',return_value=None):
            with self.assertRaisesRegex(ValueError,'not found'):transfer_plan(self.local,self.reg)
    def test_interrupted_export_blocks_installation_and_can_be_retried(self):
        before=digest(self.usb/DB_REL)
        with patch('inventory_app.usb_transfer.durable_copy',side_effect=OSError('USB disconnected')):
            with self.assertRaises(OSError):self.export()
        self.assertEqual(digest(self.usb/DB_REL),before);self.assertTrue((self.usb/PENDING).exists())
        with self.assertRaisesRegex(ValueError,'did not finish'):validate_package(self.usb)
        self.export();validate_package(self.usb);self.assertEqual(self.rows(self.usb),self.rows(self.local))
        self.assertFalse((self.usb/PENDING).exists())
    def test_repeated_data_updates_keep_one_program_backup_and_ten_compact_data_backups(self):
        unrelated=self.backups/'ace_usb_refresh_personal.zip';unrelated.write_bytes(b'unrelated archive')
        for _ in range(12):self.export()
        self.assertEqual(len(owned_archives(self.usb)),1)
        self.assertEqual(len(list(self.backups.glob('ace_usb_refresh_*.zip'))),11)
        self.assertEqual(unrelated.read_bytes(),b'unrelated archive')
