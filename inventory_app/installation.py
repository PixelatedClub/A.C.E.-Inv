"""Local program installation, first-use data seeding, and one-version rollback."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile

from .usb_portable import atomic_json, read_json, read_marker, validate_package, INSTALL_MARKER, DB_REL

RELEASE='ace_release.json'
CHANNEL='cic-sharepoint'
BACKUPS='program_backups'
MAX_PROGRAM=100*1024*1024


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def version_key(version):
    match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-(cic|beta|alpha)\.(\d+))?',str(version))
    if not match:raise ValueError('The program version is invalid.')
    return (*map(int,match.group(1,2,3)),{'alpha':0,'cic':1,'beta':2,None:3}[match[4]],int(match[5] or 0))


def make_release(version,exe):
    version_key(version)
    return dict(schema='ace.release.v1',channel=CHANNEL,version=version,executable='A.C.E.exe',
                size=Path(exe).stat().st_size,sha256=digest(exe),minimum_setup='1.9.0-cic.6')


def release(root, *, verify=True):
    root=Path(root);data=read_json(root/RELEASE)
    if not data or data.get('schema')!='ace.release.v1' or data.get('channel')!=CHANNEL or data.get('executable')!='A.C.E.exe':
        raise ValueError('This program package has no compatible update manifest.')
    version_key(data.get('version',''));version_key(data.get('minimum_setup','1.9.0-cic.6'))
    if not re.fullmatch(r'[0-9a-f]{64}',str(data.get('sha256',''))) or type(data.get('size')) is not int or not 1<=data['size']<=MAX_PROGRAM:
        raise ValueError('The program update metadata is invalid.')
    if verify:
        exe=root/'A.C.E.exe'
        if not exe.is_file() or exe.stat().st_size!=data['size'] or digest(exe)!=data['sha256']:
            raise ValueError('The program package failed checksum verification. The installed inventory was preserved.')
        with exe.open('rb') as stream:
            if stream.read(2)!=b'MZ':raise ValueError('The update is not a Windows application.')
    return data


def owned_archives(root):
    root=Path(root);marker=read_marker(root)
    if not marker:raise ValueError('The installation identity is missing.')
    found=[]
    for path in (root/BACKUPS).glob('ace_program_*.zip'):
        if path.is_symlink() or not re.fullmatch(r'ace_program_[0-9_]+_[a-zA-Z0-9.-]+\.zip',path.name):continue
        try:
            with zipfile.ZipFile(path) as archive:
                info=json.loads(archive.read('backup_info.json'))
                if info.get('schema')!='ace.program.rollback.v1' or info.get('package_id')!=marker['package_id']:continue
                version_key(info['version']);datetime.fromisoformat(info['created'])
                found.append((info['created'],path,info))
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):continue
    return sorted(found,key=lambda value:(value[0],value[1].name),reverse=True)


def cleanup_versions(root):
    removed=[];archives=owned_archives(root)
    for _,path,_ in archives[1:]:
        # Only recognized archives inside this installation's dedicated folder.
        if path.resolve().parent!=(Path(root)/BACKUPS).resolve():raise ValueError('Unsafe program-backup location.')
        size=path.stat().st_size;path.unlink();removed.append(dict(name=path.name,bytes=size))
    return dict(removed=removed,kept=archives[0][1].name if archives else None)


def archive_program(root,helper=None):
    root=Path(root);current=release(root);marker=read_marker(root)
    folder=root/BACKUPS;folder.mkdir(exist_ok=True)
    now=datetime.now(timezone.utc);path=folder/('ace_program_'+now.strftime('%Y%m%d_%H%M%S_%f')+'_'+current['version']+'.zip')
    info=dict(schema='ace.program.rollback.v1',package_id=marker['package_id'],version=current['version'],created=now.isoformat())
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(root/'A.C.E.exe','A.C.E.exe');archive.write(root/RELEASE,RELEASE)
        if helper and Path(helper).is_file():archive.write(helper,'Set Up A.C.E.exe')
        archive.writestr('backup_info.json',json.dumps(info))
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:raise ValueError('The previous-version archive failed verification.')
    return path


def recover_program(root):
    root=Path(root);journal=root/'program_update_pending.json'
    data=read_json(journal)
    if not data:return
    marker=read_marker(root)
    if data.get('schema')!='ace.update.pending.v1' or data.get('package_id')!=marker['package_id']:
        raise ValueError('An incomplete update needs manual review.')
    backup=(root/BACKUPS/str(data.get('backup',''))).resolve()
    if backup.parent!=(root/BACKUPS).resolve() or not backup.is_file():raise ValueError('The update recovery archive is missing.')
    exe=root/'A.C.E.exe';actual=digest(exe) if exe.is_file() else ''
    if actual==data['new']['sha256']:atomic_json(root/RELEASE,data['new'])
    elif actual==data['old']['sha256']:atomic_json(root/RELEASE,data['old'])
    else:
        with zipfile.ZipFile(backup) as archive:
            if archive.getinfo('A.C.E.exe').file_size>MAX_PROGRAM:raise ValueError('Invalid program recovery archive.')
            raw=archive.read('A.C.E.exe')
        if hashlib.sha256(raw).hexdigest()!=data['old']['sha256']:raise ValueError('Program recovery checksum failed.')
        staged=root/'.ace-recover.exe';staged.write_bytes(raw);staged.replace(exe);atomic_json(root/RELEASE,data['old'])
    journal.unlink();release(root)


def update_program(source,root,*,backup_folder=None,helper=None):
    source=Path(source);root=Path(root);recover_program(root)
    incoming=release(source);current=release(root)
    from .config import APP_VERSION
    if version_key(incoming['minimum_setup'])>version_key(APP_VERSION):raise ValueError('This release needs a newer setup utility.')
    if version_key(incoming['version'])<=version_key(current['version']):
        return dict(updated=False,version=current['version'],reason='Installed program is current or newer.')
    if backup_folder:
        from .usb_setup import database_backup
        database_backup(root/DB_REL,backup_folder)
    previous=archive_program(root,helper)
    staged=root/('.ace-update-'+uuid.uuid4().hex+'.exe')
    try:
        shutil.copy2(source/'A.C.E.exe',staged)
        if digest(staged)!=incoming['sha256']:raise ValueError('The staged update failed verification.')
        atomic_json(root/'program_update_pending.json',dict(schema='ace.update.pending.v1',package_id=read_marker(root)['package_id'],
                    old=current,new=incoming,backup=previous.name))
        staged.replace(root/'A.C.E.exe');atomic_json(root/RELEASE,incoming)
        (root/'program_update_pending.json').unlink()
    except Exception:
        recover_program(root)
        if not (root/'program_update_pending.json').exists() and digest(root/'A.C.E.exe')==current['sha256']:
            previous.unlink(missing_ok=True)
        raise
    finally:
        if staged.exists():staged.unlink()
    cleanup=cleanup_versions(root)
    return dict(updated=True,version=incoming['version'],previous=str(previous),cleanup=cleanup)


def install_local(source,target,package_id,backup_folder,*,helper=None):
    source=Path(source).resolve();target=Path(target).resolve();uuid.UUID(package_id)
    if target==source or target.is_relative_to(source):raise ValueError('Choose a computer installation folder outside the USB package.')
    incoming=release(source)
    from .config import APP_VERSION
    if version_key(incoming['minimum_setup'])>version_key(APP_VERSION):raise ValueError('This release needs a newer setup utility.')
    if target.exists():
        marker=read_marker(target)
        if not marker or marker['schema']!='ace.install.v1' or marker['package_id']!=package_id:
            raise ValueError('The computer folder contains another installation. Existing files were preserved.')
        recover_program(target);validate_package(target)
        result=update_program(source,target,backup_folder=backup_folder,helper=helper)
        return dict(result,root=str(target),seeded=False)
    validate_package(source,require_marker=False)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ace-install-',dir=target.parent) as temporary:
        temporary=Path(temporary).resolve()
        if not temporary.is_relative_to(target.parent):raise ValueError('Unsafe installation staging path.')
        stage=temporary/'package';stage.mkdir();(stage/'portable_data').mkdir()
        with closing(sqlite3.connect((source/DB_REL).as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(stage/DB_REL)) as dst:src.backup(dst)
        for path in (source/'portable_data').iterdir():
            if path.name in ('inventory.db','inventory.db-wal','inventory.db-shm','backups'):continue
            destination=stage/'portable_data'/path.name
            if path.is_symlink():raise ValueError('The seed package contains an unsupported file link.')
            if path.is_dir():
                if any(p.is_symlink() for p in path.rglob('*')):raise ValueError('Unsupported link in seed assets.')
                shutil.copytree(path,destination)
            else:shutil.copy2(path,destination)
        shutil.copy2(source/'A.C.E.exe',stage/'A.C.E.exe');shutil.copy2(source/'app_settings.json',stage/'app_settings.json')
        atomic_json(stage/INSTALL_MARKER,dict(schema='ace.install.v1',package_id=package_id,database=DB_REL,executable='A.C.E.exe'))
        atomic_json(stage/RELEASE,incoming)
        archives=owned_archives(source) if read_marker(source) else []
        if archives:
            (stage/BACKUPS).mkdir();shutil.copy2(archives[0][1],stage/BACKUPS/archives[0][1].name)
        validate_package(stage);release(stage)
        from .usb_setup import database_backup
        database_backup(stage/DB_REL,backup_folder)
        stage.replace(target)
    return dict(updated=True,seeded=True,root=str(target),version=incoming['version'])
