"""Install locally from a USB and launch with optional verified program updates."""
from contextlib import closing
from datetime import datetime
import base64
import ctypes
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

from .config import DEVICE_SETTINGS_DIR, DEVICE_SETTINGS_PATH, load_device_settings
from .usb_portable import (MARKER, atomic_json, new_marker, read_json, read_marker,
                           validate_package, volume_serial, locate_package)

REGISTRY=DEVICE_SETTINGS_DIR/'usb_registry.json'
LEGACY_LAUNCHER=DEVICE_SETTINGS_DIR/'USB Launcher'/'ACE USB Launcher.exe'
LAUNCHER=(DEVICE_SETTINGS_DIR/'Launcher'/'ACE Launcher.exe').resolve()
INSTALLS=(DEVICE_SETTINGS_DIR/'Installed').resolve()


def known_folder(identifier, fallback):
    if os.name=='nt':
        result=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,identifier,None,0,result)==0:
            return Path(result.value)
    return Path(fallback)


def desktop_folder():return known_folder(0x10,Path.home()/'Desktop')


def default_backup():
    old=load_device_settings().get('protected_backup_path','')
    return Path(old) if old else known_folder(5,Path.home()/'Documents')/'A.C.E. Backups'


def powershell(script):
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                          capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=30)
    if result.returncode:raise OSError('Windows could not create the A.C.E. shortcut. Existing files were retained.')
    return result.stdout.strip()


def quote(value):return "'"+str(value).replace("'","''")+"'"


def shortcut_details(path):
    result=powershell('$s=New-Object -ComObject WScript.Shell\n$l=$s.CreateShortcut('+quote(path)+')\n'+
                      '[PSCustomObject]@{target=$l.TargetPath;arguments=$l.Arguments} | ConvertTo-Json -Compress')
    return json.loads(result)


def create_shortcut(desktop, launcher, package, recovery):
    title='ACE Inventory' if package.get('mode')=='installed' else 'ACE USB'
    path=Path(desktop)/(title+'.lnk')
    if path.exists():
        old=shortcut_details(path)
        launcher_target=str(Path(launcher).resolve()).casefold()
        expected={launcher_target,str((Path(package['last_root'])/'A.C.E.exe').resolve()).casefold()}
        old_target=str(Path(old.get('target','')).resolve()).casefold()
        another_package=old_target==launcher_target and old.get('arguments','').strip()!='--launch '+package['package_id']
        if old_target not in expected or another_package:
            path=Path(desktop)/(title+' - '+package['package_id'][:8]+'.lnk')
            if path.exists():raise FileExistsError('A shortcut with this name already exists. Existing shortcuts were retained.')
        else:shutil.copy2(path,Path(recovery)/path.name)
    script='$s=New-Object -ComObject WScript.Shell\n$l=$s.CreateShortcut('+quote(path)+')\n'
    script+='$l.TargetPath='+quote(launcher)+'\n$l.Arguments='+quote('--launch '+package['package_id'])+'\n'
    script+='$l.WorkingDirectory='+quote(Path(launcher).parent)+'\n$l.Description='+quote('Open A.C.E. inventory installed on this computer' if package.get('mode')=='installed' else 'Find this A.C.E. USB and open its inventory')+'\n'
    script+='$l.IconLocation='+quote(str(launcher)+',0')+'\n$l.Save()'
    powershell(script)
    if package.get('mode')=='installed':
        legacy=Path(desktop)/'ACE USB.lnk'
        if legacy.exists():
            old=shortcut_details(legacy)
            owned=str(Path(old.get('target','')).resolve()).casefold()==str(LEGACY_LAUNCHER.resolve()).casefold()
            if owned and old.get('arguments','').strip()=='--launch '+package['package_id']:
                shutil.copy2(legacy,Path(recovery)/legacy.name);legacy.unlink()
    return path


def registry_data(path=REGISTRY):
    data=read_json(path,{'schema':'ace.usb.registry.v1','packages':{}})
    if data.get('schema')!='ace.usb.registry.v1' or not isinstance(data.get('packages'),dict):
        raise ValueError('The saved USB registrations need repair. Existing settings were retained.')
    return data


def machine_settings(device, registration, root):
    root=Path(root).resolve();data=dict(device)
    data['protected_backup_path']=registration['backup_folder'];data['backup_setup_completed']=True
    previous=device.get('cic_microsoft',{})
    same_inventory=previous.get('package_id')==registration['package_id'] or (
        previous.get('database_path') and Path(previous['database_path']).resolve()==root/'portable_data/inventory.db')
    data['cic_microsoft']={
        'enabled':registration.get('cic_enabled',False),
        'package_id':registration['package_id'],'database_path':str(root/'portable_data/inventory.db'),
        'profile_path':str(root/'portable_data/cic_microsoft_profile.json'),
        'inbox_path':registration.get('inbox_folder',''),
        'secret':previous.get('secret') if same_inventory and previous.get('secret') else secrets.token_urlsafe(32)}
    return data


def database_backup(database, folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    handle,name=tempfile.mkstemp(prefix='.ace_usb_',suffix='.db',dir=folder);os.close(handle)
    snapshot=Path(name)
    try:
        with closing(sqlite3.connect(Path(database).as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('The backup database failed verification.')
        backup=folder/('inventory_usb_setup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip')
        with zipfile.ZipFile(backup,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:archive.write(snapshot,'inventory.db')
        with zipfile.ZipFile(backup) as archive:
            if archive.testzip() is not None:raise ValueError('The backup archive failed verification.')
        return backup
    finally:snapshot.unlink(missing_ok=True)


def validate_backup_location(root, backup_folder):
    if backup_folder.is_relative_to(root) or (os.name=='nt' and backup_folder.anchor.casefold()==root.anchor.casefold()):
        raise ValueError('Choose a backup folder on the computer or another drive, separate from this USB.')


def configure_computer(*args,**kwargs):
    from .single_instance import SingleInstanceGuard
    with SingleInstanceGuard.acquire(r'Local\TeamShapes.ACE.InventorySystem') as guard:
        if not guard.is_primary:raise ValueError('Save your work and close A.C.E. before running setup.')
        return _configure_computer(*args,**kwargs)


def _configure_computer(root,backup_folder,*,install_locally=True,**kwargs):
    if install_locally:return _configure_local_computer(root,backup_folder,**kwargs)
    return _configure_usb_computer(root,backup_folder,**kwargs)


def _configure_usb_computer(root,backup_folder,*,cic_enabled=False,inbox_folder='',launcher_source=None,
                       registry_path=REGISTRY,launcher_path=LAUNCHER,device_path=DEVICE_SETTINGS_PATH,desktop=None):
    check=validate_package(root,require_marker=False);root=check['root'];backup_folder=Path(backup_folder).expanduser().resolve()
    if check['free_bytes']<16*1024*1024:raise ValueError('The USB needs at least 16 MB of free space before setup.')
    validate_backup_location(root,backup_folder)
    if cic_enabled:
        from .cic_sharepoint import load_profile
        load_profile(root/'portable_data/cic_microsoft_profile.json')
        inbox=Path(inbox_folder).expanduser().resolve()
        if not inbox.is_dir() or inbox.is_relative_to(root):raise ValueError('Select this computer\'s existing OneDrive-synced CIC intake folder.')
        inbox_folder=str(inbox)
    if launcher_source is None and not getattr(sys,'frozen',False):
        raise ValueError('Run Set Up A.C.E.exe from the USB to set up this computer.')
    source=Path(launcher_source or sys.executable).resolve()
    if source.suffix.casefold()!='.exe' or not source.is_file():raise ValueError('Run Set Up A.C.E.exe from the USB to set up this computer.')
    registry=registry_data(registry_path);device=read_json(device_path,{})
    marker=check['marker'] or new_marker()
    registration=dict(package_id=marker['package_id'],relative_folder=str(root.relative_to(Path(root.anchor))),
                      volume_serial=volume_serial(root),last_root=str(root),backup_folder=str(backup_folder),
                      cic_enabled=bool(cic_enabled),inbox_folder=str(inbox_folder))
    recovery=Path(launcher_path).parent/'recovery'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    recovery.mkdir(parents=True)
    for old in (Path(device_path),Path(registry_path)):
        if old.exists():shutil.copy2(old,recovery/old.name)
    backup=database_backup(check['database'],backup_folder)
    launcher_path=Path(launcher_path);launcher_path.parent.mkdir(parents=True,exist_ok=True)
    if source!=launcher_path.resolve():
        if launcher_path.exists():shutil.copy2(launcher_path,recovery/launcher_path.name)
        staged=launcher_path.with_suffix('.new.exe');shutil.copy2(source,staged);os.replace(staged,launcher_path)
    if check['marker'] is None:atomic_json(root/MARKER,marker)
    shortcut=create_shortcut(desktop or desktop_folder(),launcher_path,registration,recovery)
    registry['packages'][marker['package_id']]=registration
    atomic_json(registry_path,registry)
    atomic_json(device_path,machine_settings(device,registration,root))
    return dict(package_id=marker['package_id'],shortcut=str(shortcut),backup=str(backup),root=str(root),recovery=str(recovery))


def _source_update(registration):
    """A connected USB supplies program updates only; its database is not read."""
    from .usb_portable import drive_roots
    relative=Path(registration.get('relative_folder',''))
    if relative.is_absolute() or '..' in relative.parts:return None
    matches=[]
    for drive in drive_roots():
        path=drive/relative
        try:
            marker=read_marker(path)
            if marker and marker['package_id']==registration['package_id'] and (not registration.get('volume_serial') or volume_serial(path)==registration['volume_serial']):matches.append(path)
        except (OSError,ValueError):continue
    return matches[0] if len(matches)==1 else None


def refresh_program(registration,root,*,force_online=False):
    from .installation import release,update_program,recover_program,cleanup_versions,version_key
    from .program_updates import GitHubUpdates,existing_token,discard_download
    root=Path(root);recover_program(root);validate_package(root)
    results=[];source=_source_update(registration)
    if source:
        try:results.append(update_program(source,root,backup_folder=registration['backup_folder'],helper=LAUNCHER))
        except Exception:results.append({'status':'The USB update could not be verified; the installed program was retained.'})
    status=read_json(root/'update_status.json',{})
    now=datetime.now().astimezone()
    try:due=(now-datetime.fromisoformat(status['checked_at'])).total_seconds()>6*3600
    except (KeyError,ValueError,TypeError):due=True
    if registration.get('online_updates') and (force_online or due):
        downloaded=None
        try:
            downloaded=GitHubUpdates(existing_token()).fetch_newer(release(root)['version'],root/'update_cache')
            if downloaded:
                results.append(update_program(downloaded,root,backup_folder=registration['backup_folder'],helper=LAUNCHER))
                if source:
                    try:update_program(downloaded,source,helper=source/'Set Up A.C.E.exe')
                    except Exception:pass
            status=dict(checked_at=now.isoformat(),status='Current' if not downloaded else 'Updated',version=release(root)['version'])
        except Exception:
            status=dict(checked_at=now.isoformat(),status='GitHub unavailable; the installed program remains usable.',version=release(root)['version'])
        finally:
            if downloaded:discard_download(downloaded)
        atomic_json(root/'update_status.json',status)
    cleanup=cleanup_versions(root)
    return dict(version=release(root)['version'],updates=results,cleanup=cleanup,online_status=status.get('status','Not checked'))


def _configure_local_computer(root,backup_folder,*,cic_enabled=False,inbox_folder='',online_updates=False,
        launcher_source=None,registry_path=REGISTRY,launcher_path=LAUNCHER,device_path=DEVICE_SETTINGS_PATH,
        desktop=None,install_base=INSTALLS):
    from .installation import install_local,release,archive_program,cleanup_versions,digest,version_key
    from .config import APP_VERSION
    root=Path(root).resolve();release(root)
    marker=read_marker(root) or new_marker();package_id=marker['package_id']
    target=Path(install_base).resolve()/package_id;backup_folder=Path(backup_folder).expanduser().resolve()
    validate_backup_location(root,backup_folder)
    if backup_folder.is_relative_to(target):raise ValueError('Choose a backup folder outside the managed program installation.')
    if cic_enabled:
        from .cic_sharepoint import load_profile
        profile=(target if target.exists() else root)/'portable_data/cic_microsoft_profile.json'
        load_profile(profile)
        inbox=Path(inbox_folder).expanduser().resolve()
        if not inbox.is_dir() or inbox.is_relative_to(root):raise ValueError('Choose this computer\'s synchronized CIC inbox.')
        inbox_folder=str(inbox)
    if launcher_source is None and not getattr(sys,'frozen',False):raise ValueError('Run Set Up A.C.E.exe from the USB.')
    source=Path(launcher_source or sys.executable).resolve()
    if not source.is_file() or source.suffix.casefold()!='.exe':raise ValueError('The setup application is missing.')
    registry=registry_data(registry_path);device=read_json(device_path,{})
    old_registration=registry['packages'].get(package_id,{})
    result=install_local(root,target,package_id,backup_folder,helper=launcher_path)
    registration=dict(package_id=package_id,mode='installed',install_root=str(target),
        relative_folder=str(root.relative_to(Path(root.anchor))),volume_serial=volume_serial(root),last_root=str(root),
        backup_folder=str(backup_folder),cic_enabled=bool(cic_enabled),inbox_folder=str(inbox_folder),
        online_updates=bool(online_updates),setup_version=APP_VERSION)
    recovery=target/'setup_recovery'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');recovery.mkdir(parents=True)
    for old in (Path(device_path),Path(registry_path)):
        if old.exists():shutil.copy2(old,recovery/old.name)
    launcher_path=Path(launcher_path);launcher_path.parent.mkdir(parents=True,exist_ok=True)
    installed_setup=read_json(Path(launcher_path).parent/'setup_version.json',{})
    setup_is_newer=version_key(installed_setup.get('version','0.0.0'))<=version_key(APP_VERSION)
    if source!=launcher_path.resolve() and setup_is_newer and (not launcher_path.exists() or digest(source)!=digest(launcher_path)):
        if launcher_path.exists() and not result.get('previous'):archive_program(target,launcher_path)
        staged=launcher_path.with_suffix('.new.exe');shutil.copy2(source,staged);staged.replace(launcher_path)
        atomic_json(launcher_path.parent/'setup_version.json',dict(version=APP_VERSION,sha256=digest(launcher_path)))
    registration['setup_version']=APP_VERSION if setup_is_newer else installed_setup['version']
    if read_marker(root) is None:atomic_json(root/MARKER,marker)
    shortcut=create_shortcut(desktop or desktop_folder(),launcher_path,registration,recovery)
    registry['packages'][package_id]=registration;atomic_json(registry_path,registry)
    atomic_json(device_path,machine_settings(device,registration,target))
    update=refresh_program(registration,target,force_online=True)
    cleanup_versions(root);cleanup_versions(target)
    return dict(result,package_id=package_id,shortcut=str(shortcut),recovery=str(recovery),update=update,root=str(target))


def launch_registered(package_id,*,registry_path=REGISTRY,device_path=DEVICE_SETTINGS_PATH,roots=None,start=None):
    registry=registry_data(registry_path)
    registration=registry['packages'].get(package_id)
    if not registration:raise ValueError('This USB has not been set up on this computer. Run Set Up A.C.E.exe from the USB.')
    if registration.get('package_id')!=package_id:raise ValueError('The USB registration is inconsistent. Run setup again.')
    if registration.get('mode')=='installed':
        from .installation import recover_program,release
        from .single_instance import SingleInstanceGuard
        root=Path(registration['install_root']);marker=read_marker(root)
        if not marker or marker['schema']!='ace.install.v1' or marker['package_id']!=package_id:raise ValueError('The computer installation is missing. Run setup again; no other inventory was opened.')
        with SingleInstanceGuard.acquire(r'Local\TeamShapes.ACE.InventorySystem') as guard:
            if not guard.is_primary:raise ValueError('A.C.E. is already running. Close the current copy before opening this inventory.')
            recover_program(root);validate_package(root);release(root)
            refresh_program(registration,root)
            atomic_json(device_path,machine_settings(read_json(device_path,{}),registration,root))
        (start or subprocess.Popen)([str(root/'A.C.E.exe'),'--installed-package',package_id],cwd=str(root))
        return root
    root=locate_package(registration,roots)
    atomic_json(device_path,machine_settings(read_json(device_path,{}),registration,root))
    (start or subprocess.Popen)([str(root/'A.C.E.exe'),'--usb-package',package_id],cwd=str(root))
    return root


def build_window(root, executable=None):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    window=tk.Tk();window.title('Install or Update A.C.E.');window.geometry('800x500');window.minsize(720,460)
    frame=ttk.Frame(window,padding=22);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
    ttk.Label(frame,text='Install A.C.E. on this computer',font=('Segoe UI',16,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,12))
    ttk.Label(frame,text='Install or update the program, then remove the USB. Your inventory stays on this computer. One previous program version is retained.',wraplength=730).grid(row=1,column=0,columnspan=3,sticky='w',pady=(0,14))
    package=tk.StringVar(value=str(root));backup=tk.StringVar(value=str(default_backup()))
    old=load_device_settings().get('cic_microsoft',{})
    cic=tk.BooleanVar(value=bool(old.get('enabled') and Path(old.get('inbox_path','')).is_dir()))
    try:
        identity=read_marker(root)
        preference=registry_data()['packages'].get(identity['package_id'],{}) if identity else {}
    except (OSError,ValueError):preference={}
    online=tk.BooleanVar(value=preference.get('online_updates',True))
    inbox=tk.StringVar(value=old.get('inbox_path',''));status=tk.StringVar(value='Choose the A.C.E. package folder on your USB, then install or update.')
    for row,label,var in [(2,'A.C.E. USB folder',package),(3,'Computer backup folder',backup),(5,'Synced CIC inbox',inbox)]:
        ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',padx=(0,10),pady=7)
        ttk.Entry(frame,textvariable=var).grid(row=row,column=1,sticky='ew',pady=7)
        ttk.Button(frame,text='Browse',command=lambda v=var:v.set(filedialog.askdirectory(parent=window) or v.get())).grid(row=row,column=2,padx=(8,0))
    ttk.Checkbutton(frame,text='Receive Microsoft CIC cards on this computer',variable=cic).grid(row=4,column=0,columnspan=3,sticky='w',pady=(12,2))
    ttk.Checkbutton(frame,text='Check GitHub for newer CIC versions using this computer’s existing sign-in',variable=online).grid(row=6,column=0,columnspan=3,sticky='w',pady=6)
    ttk.Label(frame,textvariable=status,wraplength=730,justify='left').grid(row=7,column=0,columnspan=3,sticky='w',pady=16)
    result={}
    def check():
        try:
            health=validate_package(package.get(),require_marker=False)
            status.set(f"Inventory health passed. USB free space: {health['free_bytes']//(1024*1024)} MB.")
        except Exception as error:messagebox.showerror('USB needs attention',str(error),parent=window)
    def setup():
        try:
            status.set('Installing or updating A.C.E. Please keep the USB connected until setup finishes.');window.update_idletasks()
            result.update(configure_computer(package.get(),backup.get(),cic_enabled=cic.get(),inbox_folder=inbox.get(),online_updates=online.get(),launcher_source=executable))
            status.set('Ready. Use ACE Inventory on your desktop. You can remove the USB. Installed version: '+result['update']['version']);open_button.configure(state='normal')
        except Exception as error:messagebox.showerror('Setup needs attention',str(error),parent=window)
    def open_app():
        try:launch_registered(result['package_id']);window.destroy()
        except Exception as error:messagebox.showerror('Cannot open A.C.E.',str(error),parent=window)
    def cleanup():
        from .installation import cleanup_versions
        from .single_instance import SingleInstanceGuard
        try:
            marker=read_marker(package.get())
            if not marker:raise ValueError('Choose a configured A.C.E. package first.')
            registration=registry_data()['packages'].get(marker['package_id'],{})
            targets=[Path(package.get())]
            if registration.get('mode')=='installed':targets.append(Path(registration['install_root']))
            with SingleInstanceGuard.acquire(r'Local\TeamShapes.ACE.InventorySystem') as guard:
                if not guard.is_primary:raise ValueError('Close A.C.E. before cleaning up program versions.')
                removed=sum(len(cleanup_versions(target)['removed']) for target in targets)
            status.set(f'Cleanup complete. Removed {removed} older program backup(s); one previous version is retained per installation.')
        except Exception as error:messagebox.showerror('Cleanup needs attention',str(error),parent=window)
    buttons=ttk.Frame(frame);buttons.grid(row=8,column=0,columnspan=3,sticky='e')
    ttk.Button(buttons,text='Check USB',command=check).pack(side='left',padx=4)
    ttk.Button(buttons,text='Install / Update',command=setup).pack(side='left',padx=4)
    ttk.Button(buttons,text='Clean Up Old Versions',command=cleanup).pack(side='left',padx=4)
    open_button=ttk.Button(buttons,text='Open A.C.E.',state='disabled',command=open_app);open_button.pack(side='left',padx=4)
    return window


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--launch');parser.add_argument('--diagnose',type=Path);parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if args.diagnose:
        try:
            checked=validate_package(args.diagnose,require_marker=False)
            result=dict(passed=True,root=str(checked['root']),free_bytes=checked['free_bytes'])
        except Exception as error:result=dict(passed=False,error=str(error))
        if args.report:atomic_json(args.report,result)
        return
    if args.launch:
        try:launch_registered(args.launch)
        except Exception as error:
            import tkinter as tk
            from tkinter import messagebox
            window=tk.Tk();window.withdraw()
            try:messagebox.showerror('A.C.E. USB',str(error),parent=window)
            finally:window.destroy()
        return
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    build_window(root).mainloop()
