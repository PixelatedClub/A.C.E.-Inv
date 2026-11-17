from contextlib import closing
import hashlib,json,sqlite3,tempfile,unittest,uuid,zipfile
from pathlib import Path
from unittest.mock import patch,Mock
import urllib.request

from inventory_app.installation import (make_release,release,install_local,update_program,cleanup_versions,
                                       owned_archives,recover_program,RELEASE)
from inventory_app.usb_portable import atomic_json,new_marker,MARKER
from inventory_app.usb_setup import launch_registered
from inventory_app.program_updates import GitHubUpdates,UpdateUnavailable,SafeRedirect,REPO,DOWNLOAD_ROOT


class LocalInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.usb=self.base/'usb';self.usb.mkdir();(self.usb/'portable_data').mkdir()
        self.marker=new_marker();atomic_json(self.usb/MARKER,self.marker)
        atomic_json(self.usb/'app_settings.json',dict(db_path='portable_data/inventory.db'))
        with closing(sqlite3.connect(self.usb/'portable_data/inventory.db')) as c:
            for table in ('items','cadets','transactions'):
                c.execute('CREATE TABLE '+table+'(id INTEGER PRIMARY KEY,value TEXT)');c.execute('INSERT INTO '+table+' VALUES(1,?)',(table,))
            c.commit()
        self.payload(self.usb,'1.9.0-cic.6');self.root=self.base/'computer'/self.marker['package_id'];self.backup=self.base/'backups'
    def tearDown(self):self.temp.cleanup()
    def payload(self,path,version):
        path.mkdir(parents=True,exist_ok=True);(path/'A.C.E.exe').write_bytes(b'MZfixture-'+version.encode())
        atomic_json(path/RELEASE,make_release(version,path/'A.C.E.exe'));return path
    def install(self):return install_local(self.usb,self.root,self.marker['package_id'],self.backup)
    def dbhash(self):return hashlib.sha256((self.root/'portable_data/inventory.db').read_bytes()).hexdigest()
    def test_first_install_seeds_exact_inventory_and_runs_without_usb(self):
        result=self.install();self.assertTrue(result['seeded'])
        registry=self.base/'registry.json';device=self.base/'device.json'
        reg=dict(package_id=self.marker['package_id'],mode='installed',install_root=str(self.root),relative_folder='gone',backup_folder=str(self.backup),online_updates=False,cic_enabled=False)
        atomic_json(registry,dict(schema='ace.usb.registry.v1',packages={self.marker['package_id']:reg}))
        start=Mock()
        from inventory_app.single_instance import SingleInstanceGuard
        with patch('inventory_app.usb_setup._source_update',return_value=None),patch('inventory_app.single_instance.SingleInstanceGuard.acquire',return_value=SingleInstanceGuard(None,is_primary=True)):
            launched=launch_registered(self.marker['package_id'],registry_path=registry,device_path=device,roots=[],start=start)
        self.assertEqual(launched,self.root)
        start.assert_called_once_with([str(self.root/'A.C.E.exe'),'--installed-package',self.marker['package_id']],cwd=str(self.root))
        self.assertEqual(json.loads(device.read_text())['cic_microsoft']['database_path'],str(self.root/'portable_data/inventory.db'))
    def test_updates_never_reseed_or_downgrade_inventory(self):
        self.install()
        with closing(sqlite3.connect(self.root/'portable_data/inventory.db')) as c:
            c.execute("INSERT INTO transactions VALUES(2,'new local checkout')");c.commit()
        before=self.dbhash();new=self.payload(self.base/'new','1.9.0-cic.7')
        self.assertTrue(install_local(new,self.root,self.marker['package_id'],self.backup)['updated'])
        self.assertEqual(before,self.dbhash())
        old=install_local(self.usb,self.root,self.marker['package_id'],self.backup)
        self.assertFalse(old['updated']);self.assertEqual(release(self.root)['version'],'1.9.0-cic.7');self.assertEqual(before,self.dbhash())
    def test_only_one_previous_program_retained_and_unrelated_files_preserved(self):
        self.install();before=self.dbhash()
        for version in ['1.9.0-cic.7','1.9.0-cic.8','1.9.0-cic.9']:
            update_program(self.payload(self.base/version,version),self.root,backup_folder=self.backup)
        archives=owned_archives(self.root);self.assertEqual(len(archives),1)
        self.assertEqual(archives[0][2]['version'],'1.9.0-cic.8')
        unrelated=self.root/'program_backups'/'personal.zip';unrelated.write_bytes(b'preserve')
        cleanup_versions(self.root);self.assertEqual(unrelated.read_bytes(),b'preserve');self.assertEqual(before,self.dbhash())
        with zipfile.ZipFile(archives[0][1]) as z:
            self.assertNotIn('inventory.db',z.namelist());self.assertEqual(json.loads(z.read(RELEASE))['version'],'1.9.0-cic.8')
    def test_missing_local_database_cannot_be_replaced_by_old_usb_seed(self):
        self.install();(self.root/'portable_data/inventory.db').unlink()
        with self.assertRaisesRegex(ValueError,'missing'):self.install()
        self.assertFalse((self.root/'portable_data/inventory.db').exists())
    def test_tampered_program_and_unsupported_setup_block_before_install(self):
        self.install();before=self.dbhash();exe=(self.root/'A.C.E.exe').read_bytes()
        new=self.payload(self.base/'new','1.9.0-cic.7');(new/'A.C.E.exe').write_bytes(b'MZwrong')
        with self.assertRaises(ValueError):update_program(new,self.root)
        self.assertEqual((self.root/'A.C.E.exe').read_bytes(),exe);self.assertEqual(self.dbhash(),before)
        self.payload(new,'1.9.0-cic.7')
        manifest=release(new);manifest['minimum_setup']='1.9.0-cic.99';atomic_json(new/RELEASE,manifest)
        with self.assertRaisesRegex(ValueError,'newer setup'):update_program(new,self.root)
        with self.assertRaisesRegex(ValueError,'newer setup'):install_local(new,self.base/'new-install',self.marker['package_id'],self.backup)
        self.assertFalse((self.base/'new-install').exists());self.assertEqual(self.dbhash(),before)
    def test_interrupted_update_recovers_without_touching_data(self):
        self.install();before=self.dbhash();new=self.payload(self.base/'new','1.9.0-cic.7')
        from inventory_app.installation import archive_program
        previous=archive_program(self.root);old=release(self.root);incoming=release(new)
        atomic_json(self.root/'program_update_pending.json',dict(schema='ace.update.pending.v1',package_id=self.marker['package_id'],backup=previous.name,old=old,new=incoming))
        (self.root/'A.C.E.exe').write_bytes((new/'A.C.E.exe').read_bytes())
        recover_program(self.root);self.assertEqual(release(self.root)['version'],incoming['version']);self.assertEqual(before,self.dbhash())


class OnlineUpdateTests(unittest.TestCase):
    def test_private_release_download_verifies_manifest_and_asset_hashes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);exe=root/'binary';exe.write_bytes(b'MZprogram7')
            manifest=make_release('1.9.0-cic.7',exe);raw=json.dumps(manifest).encode();binary=exe.read_bytes()
            assets=[dict(id=1,name=RELEASE,size=len(raw),digest='sha256:'+hashlib.sha256(raw).hexdigest()),dict(id=2,name='A.C.E.exe',size=len(binary),digest='sha256:'+hashlib.sha256(binary).hexdigest())]
            listing=json.dumps([dict(tag_name='v1.9.0-cic.7',draft=False,assets=assets)]).encode()
            replies={REPO+'/releases?per_page=100':listing,REPO+'/releases/assets/1':raw,REPO+'/releases/assets/2':binary}
            client=GitHubUpdates('fixture-private-token')
            with patch.object(client,'get',side_effect=lambda url,*a,**k:replies[url]):
                found=client.fetch_newer('1.9.0-cic.6',root/'cache')
            self.assertEqual(release(found)['version'],'1.9.0-cic.7')
            self.assertNotIn(b'fixture-private-token',(found/RELEASE).read_bytes())
            replies[REPO+'/releases/assets/2']=b'MZtampered'
            with patch.object(client,'get',side_effect=lambda url,*a,**k:replies[url]):
                with self.assertRaises(UpdateUnavailable):client.fetch_newer('1.9.0-cic.6',root/'badcache')
            public = GitHubUpdates()
            public_replies = {
                REPO+'/releases?per_page=100': listing,
                DOWNLOAD_ROOT+'v1.9.0-cic.7/'+RELEASE: raw,
                DOWNLOAD_ROOT+'v1.9.0-cic.7/A.C.E.exe': binary,
            }
            with patch.object(public,'get',side_effect=lambda url,*a,**k:public_replies[url]):
                found = public.fetch_newer('1.9.0-cic.6',root/'public-cache')
            self.assertEqual(release(found)['version'],'1.9.0-cic.7')
    def test_redirect_does_not_forward_github_token(self):
        handler=SafeRedirect();request=urllib.request.Request(REPO+'/releases/assets/1',headers={'Authorization':'Bearer fixture-token'})
        result=handler.redirect_request(request,None,302,'redirect',{},'https://release-assets.githubusercontent.com/file')
        self.assertFalse(result.has_header('Authorization'))
        with self.assertRaises(UpdateUnavailable):handler.redirect_request(request,None,302,'redirect',{},'https://untrusted.example/file')


if __name__=='__main__':unittest.main()
