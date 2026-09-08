from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


APP_TITLE = "A.C.E."
APP_VERSION = "1.7.2"
PRODUCT_NAME = "A.C.E. Inventory System"
PUBLISHER_BRAND = "Team Shapes"
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

PORTABLE_DATA_DIR = BASE_DIR / "portable_data"
DEFAULT_DB_PATH = PORTABLE_DATA_DIR / "inventory.db"
CONFIG_PATH = BASE_DIR / "app_settings.json"
BUNDLED_PORTABLE_DATA_DIR = BUNDLE_DIR / "portable_data"
BUNDLED_CONFIG_PATH = BUNDLE_DIR / "app_settings.json"
DEVICE_SETTINGS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "A.C.E."
DEVICE_SETTINGS_PATH = DEVICE_SETTINGS_DIR / "device_settings.json"
DEFAULT_ORG_NAME = "A.C.E."
DEFAULT_BACKUP_INTERVAL_OPS = 10
DEFAULT_OVERDUE_DAYS = 30


@dataclass(slots=True)
class AppSettings:
    org_name: str = DEFAULT_ORG_NAME
    db_path: str = str(DEFAULT_DB_PATH)
    backup_interval_ops: int = DEFAULT_BACKUP_INTERVAL_OPS
    overdue_days: int = DEFAULT_OVERDUE_DAYS
    protected_backup_path: str = ""

    @property
    def database_path(self) -> Path:
        raw_path = Path(self.db_path).expanduser()
        if not raw_path.is_absolute():
            raw_path = BASE_DIR / raw_path
        return raw_path.resolve()

    @property
    def label_dir(self) -> Path:
        return self.database_path.parent / "labels"

    @property
    def backup_dir(self) -> Path:
        return self.database_path.parent / "backups"

    @property
    def protected_backup_dir(self) -> Path | None:
        cleaned_path = self.protected_backup_path.strip()
        if not cleaned_path:
            return None
        raw_path = Path(cleaned_path).expanduser()
        if not raw_path.is_absolute():
            raw_path = BASE_DIR / raw_path
        return raw_path.resolve()


def ensure_app_directories(settings: AppSettings) -> None:
    PORTABLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.label_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)


def bootstrap_bundled_files() -> None:
    if BUNDLED_CONFIG_PATH != CONFIG_PATH and BUNDLED_CONFIG_PATH.exists() and not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BUNDLED_CONFIG_PATH, CONFIG_PATH)

    if BUNDLED_PORTABLE_DATA_DIR != PORTABLE_DATA_DIR and BUNDLED_PORTABLE_DATA_DIR.exists() and not PORTABLE_DATA_DIR.exists():
        shutil.copytree(BUNDLED_PORTABLE_DATA_DIR, PORTABLE_DATA_DIR, dirs_exist_ok=True)


def load_settings() -> AppSettings:
    bootstrap_bundled_files()
    if not CONFIG_PATH.exists():
        device_settings = load_device_settings()
        settings = AppSettings(
            protected_backup_path=str(device_settings.get("protected_backup_path", "") or "")
        )
        ensure_app_directories(settings)
        save_settings(settings)
        return settings

    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    requested_db_path = raw.get("db_path", str(DEFAULT_DB_PATH))
    if getattr(sys, "frozen", False):
        requested_path = Path(requested_db_path).expanduser()
        if not requested_path.exists():
            requested_db_path = str(DEFAULT_DB_PATH)
    device_settings = load_device_settings()
    settings = AppSettings(
        org_name=raw.get("org_name", DEFAULT_ORG_NAME),
        db_path=requested_db_path,
        backup_interval_ops=max(1, int(raw.get("backup_interval_ops", DEFAULT_BACKUP_INTERVAL_OPS))),
        overdue_days=max(1, int(raw.get("overdue_days", DEFAULT_OVERDUE_DAYS))),
        protected_backup_path=str(device_settings.get("protected_backup_path", "") or ""),
    )
    ensure_app_directories(settings)
    return settings


def save_settings(settings: AppSettings) -> None:
    ensure_app_directories(settings)
    portable_settings = asdict(settings)
    # The protected folder belongs to a specific Windows device. Keeping it
    # out of the portable settings prevents one computer's path from being
    # treated as valid when the A.C.E. USB moves to another computer.
    portable_settings["protected_backup_path"] = ""
    CONFIG_PATH.write_text(json.dumps(portable_settings, indent=2), encoding="utf-8")


def load_device_settings() -> dict[str, object]:
    if not DEVICE_SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(DEVICE_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def device_backup_setup_completed() -> bool:
    return bool(load_device_settings().get("backup_setup_completed", False))


def save_device_backup_settings(*, protected_backup_path: str, setup_completed: bool) -> bool:
    payload = load_device_settings()
    payload.update(
        {
            "backup_setup_completed": bool(setup_completed),
            "protected_backup_path": protected_backup_path.strip(),
        }
    )
    return _save_device_settings(payload)


def alternate_icons_enabled() -> bool:
    return bool(load_device_settings().get("alternate_icons_enabled", False))


def save_alternate_icons_enabled(enabled: bool) -> bool:
    payload = load_device_settings()
    payload["alternate_icons_enabled"] = bool(enabled)
    return _save_device_settings(payload)


def _save_device_settings(payload: dict[str, object]) -> bool:
    try:
        DEVICE_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        DEVICE_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return False
    return True
