"""Explicit computer-to-USB snapshots. Never merges into the working database."""
from contextlib import closing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from .usb_portable import DB_REL,atomic_json,read_json,read_marker,validate_package,volume_serial
from .installation import release,version_key,digest,archive_program,cleanup_versions

PENDING='ace_usb_transfer_pending.json'
DATA_FILES=('checkout_drafts.json','return_drafts.json','cic_microsoft_profile.json','app_icon.ico','window_icon.png')
DATA_FOLDERS=('startup_assets','suit_icons','labels','exports')

def snapshot(database,destination):
    with closing(sqlite3.connect(Path(database).as_uri()+'?mode=ro',uri=True,timeout=10)) as source,closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        target.execute('PRAGMA journal_mode=DELETE')
        if target.execute('PRAGMA quick_check').fetchone()[0]!='ok' or target.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('The inventory snapshot failed its health check.')

def summary(database):
    with closing(sqlite3.connect(Path(database).as_uri()+'?mode=ro',uri=True)) as connection:
        return {name:connection.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('items','cadets','transactions')}

def transfer_plan(source,registration,*,target=None):
    source=Path(source).resolve();checked=validate_package(source);marker=checked['marker']
    if marker['schema']!='ace.install.v1' or marker['package_id']!=registration['package_id']:
        raise ValueError('Open the installed A.C.E. inventory before updating its USB copy.')
    if target is None:
        from .usb_setup import _source_update
        target=_source_update(registration)
    if target is None:raise ValueError('The registered A.C.E. USB was not found. Connect it and try again.')
    target=Path(target).resolve()
    if target==source or target.is_relative_to(source) or source.is_relative_to(target):raise ValueError('Choose the separate registered USB package.')
    usb=validate_package(target,allow_pending_transfer=True)
    if usb['marker']['schema']!='ace.usb.v1' or usb['marker']['package_id']!=marker['package_id']:
        raise ValueError('This USB belongs to another A.C.E. inventory. It was not changed.')
    if registration.get('volume_serial') and volume_serial(target)!=registration['volume_serial']:
        raise ValueError('This is not the registered USB volume. No files were changed.')
    backup=Path(registration['backup_folder']).expanduser().resolve()
    if backup.is_relative_to(target):raise ValueError('Choose a computer backup folder outside the USB.')
    return dict(source=source,target=target,backup=backup,package_id=marker['package_id'],computer=summary(checked['database']),usb=summary(usb['database']),version=release(source)['version'],unfinished=(target/PENDING).exists())

def durable_copy(source,destination):
    source=Path(source);destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name('.ace-usb-copy-'+uuid.uuid4().hex+'.tmp')
    try:
        with source.open('rb') as src,temporary.open('xb') as dst:
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        if digest(source)!=digest(temporary):raise ValueError('USB write verification failed: '+destination.name)
        temporary.replace(destination)
        if digest(source)!=digest(destination):raise ValueError('USB read-back verification failed: '+destination.name)
    finally:temporary.unlink(missing_ok=True)

def safe_destination(root,relative):
    destination=(root/relative).resolve()
    if not destination.is_relative_to(root):raise ValueError('An unsafe USB file location was found. Existing files were preserved.')
    return destination

def data_backup(plan,stage):
    folder=plan['backup'];folder.mkdir(parents=True,exist_ok=True)
    created=datetime.now(timezone.utc);path=folder/('ace_usb_refresh_'+created.strftime('%Y%m%d_%H%M%S_%f')+'.zip')
    old=stage/'usb_previous.db';snapshot(plan['target']/DB_REL,old)
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        archive.write(stage/DB_REL,'computer/inventory.db');archive.write(old,'usb_previous/inventory.db')
        for prefix,root in [('computer',plan['source']),('usb_previous',plan['target'])]:
            for name in DATA_FILES[:3]:
                file=root/'portable_data'/name
                if file.is_file():archive.write(file,prefix+'/'+name)
            archive.write(root/'app_settings.json',prefix+'/app_settings.json')
        archive.writestr('backup_info.json',json.dumps(dict(schema='ace.usb.data-backup.v1',package_id=plan['package_id'],created=created.isoformat())))
    with path.open('r+b') as stream:stream.flush();os.fsync(stream.fileno())
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:raise ValueError('The pre-transfer backup failed verification.')
    return path

def prune_data_backups(plan):
    owned=[]
    for path in plan['backup'].glob('ace_usb_refresh_*.zip'):
        if path.is_symlink():continue
        try:
            with zipfile.ZipFile(path) as archive:info=json.loads(archive.read('backup_info.json'))
            if info.get('schema')=='ace.usb.data-backup.v1' and info.get('package_id')==plan['package_id']:
                owned.append((info['created'],path))
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):continue
    for _,path in sorted(owned,reverse=True)[10:]:
        if path.resolve().parent==plan['backup']:path.unlink()

def export_to_usb(source,registration,*,target=None,helper=None):
    plan=transfer_plan(source,registration,target=target);source=plan['source'];target=plan['target']
    incoming=release(source)
    try:current=release(target)
    except ValueError:current=None
    metadata=release(target,verify=False)
    copy_program=version_key(incoming['version'])>=version_key(metadata['version'])
    if current is None and not copy_program:
        raise ValueError('The USB has a damaged newer program. Restore that release before refreshing its data.')
    def check_target():
        marker=read_marker(target)
        if not marker or marker['package_id']!=plan['package_id'] or (registration.get('volume_serial') and volume_serial(target)!=registration['volume_serial']):
            raise ValueError('The registered USB was disconnected or replaced. No further files were written.')
    with tempfile.TemporaryDirectory(prefix='ace-usb-export-') as temp:
        stage=Path(temp).resolve()
        if stage.is_relative_to(target):raise ValueError('The snapshot must be prepared on the computer.')
        (stage/'portable_data').mkdir();snapshot(source/DB_REL,stage/DB_REL)
        files=[Path(DB_REL)]
        for name in DATA_FILES:
            file=source/'portable_data'/name
            if file.is_file():files.append(Path('portable_data')/name)
        for name in DATA_FOLDERS:
            folder=source/'portable_data'/name
            if folder.is_dir():files.extend(file.relative_to(source) for file in folder.rglob('*') if file.is_file())
        for relative in files[1:]:
            original=source/relative
            if original.is_symlink() or not original.resolve().is_relative_to(source):raise ValueError('Unsupported file link in A.C.E. data.')
            destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,destination)
        settings=read_json(source/'app_settings.json');settings['db_path']=DB_REL;settings.pop('protected_backup_path',None)
        atomic_json(stage/'app_settings.json',settings);files.append(Path('app_settings.json'))
        counts=summary(stage/DB_REL)
        (stage/'READ ME.txt').write_text(
            f"A.C.E. USB inventory snapshot\n{counts['items']} item records, {counts['cadets']} cadets, {counts['transactions']} transactions.\n\n"
            'On a new computer, run Set Up A.C.E.exe, then Install / Update. Use ACE Inventory on the desktop and remove the USB.\n\n'
            'After working on the installed copy, use Settings > Update USB Copy to refresh this flash drive. Wait for verification, then safely eject it.\n\n'
            'Each computer has its own working inventory. Program updates do not merge inventory between computers.\n',encoding='utf-8')
        files.append(Path('READ ME.txt'))
        if copy_program:
            shutil.copy2(source/'A.C.E.exe',stage/'A.C.E.exe');atomic_json(stage/'ace_release.json',incoming)
            files.extend([Path('A.C.E.exe'),Path('ace_release.json')])
            if not helper or not Path(helper).is_file():raise ValueError('The current A.C.E. setup utility is missing. Run the latest Set Up A.C.E. first.')
            setup=read_json(Path(helper).parent/'setup_version.json',{})
            if setup and (version_key(setup['version'])<version_key(incoming['minimum_setup']) or setup.get('sha256')!=digest(helper)):
                raise ValueError('Run the latest Set Up A.C.E. before refreshing the USB copy.')
            shutil.copy2(helper,stage/'Set Up A.C.E.exe');files.append(Path('Set Up A.C.E.exe'))
        size=sum((stage/file).stat().st_size for file in files)
        if shutil.disk_usage(target).free<size+32*1024*1024:raise ValueError('The USB does not have enough free space for a verified transfer.')
        backup=data_backup(plan,stage)
        # Recheck identity immediately before writing; a different drive is never used.
        transfer_plan(source,registration,target=target)
        for relative in files:safe_destination(target,relative)
        atomic_json(target/PENDING,dict(schema='ace.usb.transfer.v1',package_id=plan['package_id'],backup=str(backup)))
        if copy_program and current and current['sha256']!=incoming['sha256']:
            archive_program(target,target/'Set Up A.C.E.exe')
        # Publish data and assets first, then replace the complete SQLite snapshot last.
        # Install the pending-aware setup utility before changing other package files.
        for relative in sorted(files,key=lambda path:0 if path==Path('Set Up A.C.E.exe') else 1):
            if relative!=Path(DB_REL):
                check_target();durable_copy(stage/relative,safe_destination(target,relative))
        check_target()
        with closing(sqlite3.connect((target/DB_REL).as_uri()+'?mode=rw',uri=True,timeout=5)) as connection:
            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            if connection.execute('PRAGMA journal_mode=DELETE').fetchone()[0].lower()!='delete':
                raise ValueError('The USB database is busy. Close other programs using it and retry.')
        durable_copy(stage/DB_REL,target/DB_REL)
        validate_package(target,allow_pending_transfer=True);release(target)
        if digest(stage/DB_REL)!=digest(target/DB_REL):raise ValueError('The USB database verification failed.')
        manifest=dict(schema='ace.usb.snapshot.v1',created=datetime.now(timezone.utc).isoformat(),package_id=plan['package_id'],version=release(target)['version'],files=[dict(path=str(file),bytes=(stage/file).stat().st_size,sha256=digest(stage/file)) for file in files])
        atomic_json(target/'USB_copy_manifest.json',manifest)
        (target/PENDING).unlink()
        cleanup_versions(target);prune_data_backups(plan)
        return dict(target=str(target),backup=str(backup),counts=summary(target/DB_REL),version=release(target)['version'],files=len(files))
