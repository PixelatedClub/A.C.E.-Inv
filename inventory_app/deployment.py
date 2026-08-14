from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image


def ensure_icon_file(source_png: Path | None, destination: Path) -> Path:
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if source_png is None:
        if destination.exists():
            return destination
        raise ValueError("An icon source image is required.")

    source_path = Path(source_png).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Icon source image not found: {source_path}")

    with Image.open(source_path) as image:
        rgba = image.convert("RGBA")
        sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        rgba.save(destination, format="ICO", sizes=sizes)
    return destination


def create_transfer_installer(
    *,
    project_dir: Path,
    database_path: Path,
    icon_path: Path | None,
    app_title: str,
    backup_interval_ops: int,
    overdue_days: int,
) -> Path:
    project_dir = Path(project_dir).resolve()
    main_script = project_dir / "main.py"
    if not main_script.exists():
        raise FileNotFoundError(f"main.py not found in {project_dir}")

    _ensure_pyinstaller()

    safe_name = _safe_name(app_title) or "auburn_afrotc_inventory"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = project_dir / "transfer_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    final_exe_path = export_dir / f"{safe_name}_transfer_{timestamp}.exe"

    with tempfile.TemporaryDirectory(prefix="afrotc_transfer_") as temp_root_raw:
        temp_root = Path(temp_root_raw)
        staging_dir = temp_root / "bundle_seed"
        staging_dir.mkdir(parents=True, exist_ok=True)

        portable_data_dir = staging_dir / "portable_data"
        portable_data_dir.mkdir(parents=True, exist_ok=True)
        _stage_portable_data(database_path=database_path, portable_data_dir=portable_data_dir)

        settings_payload = {
            "org_name": app_title,
            "db_path": "portable_data/inventory.db",
            "backup_interval_ops": int(backup_interval_ops),
            "overdue_days": int(overdue_days),
        }
        (staging_dir / "app_settings.json").write_text(json.dumps(settings_payload, indent=2), encoding="utf-8")

        dist_dir = temp_root / "dist"
        work_dir = temp_root / "work"
        spec_dir = temp_root / "spec"

        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            final_exe_path.stem,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            "--add-data",
            f"{staging_dir / 'app_settings.json'};.",
            "--add-data",
            f"{portable_data_dir};portable_data",
        ]
        if icon_path is not None:
            command.extend(["--icon", str(Path(icon_path).resolve())])
        command.append(str(main_script))

        subprocess.run(command, cwd=project_dir, check=True)
        built_exe = dist_dir / f"{final_exe_path.stem}.exe"
        if not built_exe.exists():
            raise FileNotFoundError("PyInstaller did not produce the expected transfer executable.")
        shutil.copy2(built_exe, final_exe_path)

    return final_exe_path


def _stage_portable_data(*, database_path: Path, portable_data_dir: Path) -> None:
    source_root = database_path.parent
    if source_root.exists():
        for child in source_root.iterdir():
            destination = portable_data_dir / child.name
            if child.is_dir():
                shutil.copytree(child, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(child, destination)

    if not (portable_data_dir / "inventory.db").exists():
        portable_data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database_path, portable_data_dir / "inventory.db")


def _ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)


def _safe_name(value: str) -> str:
    characters = []
    for character in value.lower():
        if character.isalnum():
            characters.append(character)
        elif character in {" ", "-", "_"}:
            characters.append("_")
    name = "".join(characters).strip("_")
    while "__" in name:
        name = name.replace("__", "_")
    return name
