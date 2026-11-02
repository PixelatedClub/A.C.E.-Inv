"""Portable-package identity and read-only validation. Never creates a database."""
from contextlib import closing
import ctypes
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid

MARKER = 'ace_usb.json'
INSTALL_MARKER = 'ace_install.json'
SCHEMA = 'ace.usb.v1'
DB_REL = 'portable_data/inventory.db'


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    handle,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if Path(name).exists():Path(name).unlink()


def read_json(path, default=None):
    path=Path(path)
    if not path.exists():return default
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict):raise ValueError('Expected a settings object: '+path.name)
    return data


def read_marker(root):
    root=Path(root)
    data=read_json(root/MARKER)
    if data is not None and (root/INSTALL_MARKER).exists():raise ValueError('The package has conflicting installation identities.')
    if data is None:data=read_json(root/INSTALL_MARKER)
    if data is None:return None
    if data.get('schema') not in (SCHEMA,'ace.install.v1') or data.get('database')!=DB_REL or data.get('executable')!='A.C.E.exe':
        raise ValueError('This USB has an unsupported A.C.E. package marker.')
    try:uuid.UUID(data.get('package_id',''))
    except (ValueError,AttributeError,TypeError):raise ValueError('The A.C.E. USB identity is invalid.') from None
    return data


def new_marker():
    return dict(schema=SCHEMA,package_id=str(uuid.uuid4()),database=DB_REL,executable='A.C.E.exe')


def has_marker(root):return (Path(root)/MARKER).exists() or (Path(root)/INSTALL_MARKER).exists()


def package_database(root):
    root=Path(root).resolve()
    path=(root/DB_REL).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('The inventory database is missing. Restore its verified backup. No empty inventory was created.')
    return path


def validate_package(root, *, require_marker=True, check_database=True):
    raw=Path(root)
    if raw.is_symlink():raise ValueError('Choose the actual A.C.E. USB folder.')
    root=raw.resolve();marker=read_marker(root)
    if require_marker and marker is None:raise ValueError('This folder has not been set up as an A.C.E. USB.')
    if not (root/'A.C.E.exe').is_file():raise ValueError('A.C.E.exe is missing from the USB folder.')
    config=read_json(root/'app_settings.json')
    if config is None:raise ValueError('The USB application settings are missing.')
    configured=Path(str(config.get('db_path','')))
    if configured.is_absolute() or '..' in configured.parts or configured.as_posix().casefold()!=DB_REL:
        raise ValueError('USB settings must use portable_data/inventory.db beside A.C.E.exe. Run setup on the correct package.')
    db=package_database(root)
    if check_database:
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)) as connection:
            if connection.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('The USB database failed its health check. Restore a verified backup before continuing.')
            names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'items','cadets','transactions'}<=names:raise ValueError('The selected file is not an A.C.E. inventory database.')
            if connection.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('The USB database has broken record references. Restore or repair it before continuing.')
    return {'root':root,'database':db,'marker':marker,'free_bytes':shutil.disk_usage(root).free}


def volume_serial(root):
    if os.name!='nt':return ''
    serial=ctypes.c_uint32();volume=ctypes.create_unicode_buffer(261);fs=ctypes.create_unicode_buffer(261)
    ok=ctypes.windll.kernel32.GetVolumeInformationW(str(Path(root).anchor),volume,261,ctypes.byref(serial),None,None,fs,261)
    if not ok:raise OSError('Windows could not read the USB volume identity.')
    return f'{serial.value:08X}'


def drive_roots():
    if os.name!='nt':return []
    mask=ctypes.windll.kernel32.GetLogicalDrives()
    return [Path(chr(65+i)+':/') for i in range(26) if mask&(1<<i)]


def locate_package(registration, roots=None):
    relative=Path(registration['relative_folder'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('The saved USB folder is invalid. Run setup again.')
    matches=[]
    for drive in (drive_roots() if roots is None else roots):
        candidate=Path(drive)/relative
        try:
            marker=read_marker(candidate)
            if not marker or marker['package_id']!=registration['package_id']:continue
            expected=registration.get('volume_serial','')
            if expected and volume_serial(candidate)!=expected:continue
            matches.append(candidate.resolve())
        except (OSError,ValueError,json.JSONDecodeError):continue
    matches=list(dict.fromkeys(matches))
    if not matches:raise ValueError('A.C.E. USB not found. Plug in the flash drive and try this shortcut again. The laptop inventory was not opened.')
    if len(matches)!=1:raise ValueError('More than one copy of this A.C.E. USB is connected. Disconnect the extra copy before opening inventory.')
    validate_package(matches[0])
    return matches[0]


def rebase_intake(settings, root, database):
    """Move only paths for the same registered package, never a different database."""
    marker=read_marker(root)
    if not marker or settings.get('package_id')!=marker['package_id']:
        if settings.get('database_path') and Path(settings['database_path']).resolve()!=Path(database).resolve():
            raise ValueError('This intake belongs to another database. Reconfigure it for the current inventory.')
        return dict(settings)
    profile=(Path(root)/'portable_data/cic_microsoft_profile.json').resolve()
    if not profile.is_file():raise ValueError('The USB CIC form profile is missing. Configure Microsoft Intake again.')
    return dict(settings,database_path=str(Path(database).resolve()),profile_path=str(profile))
