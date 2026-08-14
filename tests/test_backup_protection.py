from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from inventory_app import config
from inventory_app.config import AppSettings
from inventory_app.database import InventoryDatabase


class BackupProtectionTests(unittest.TestCase):
    def test_device_choice_is_remembered_only_in_local_device_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            device_dir = root / "device"
            device_file = device_dir / "device_settings.json"
            portable_config = root / "app_settings.json"
            settings = AppSettings(
                db_path=str(root / "portable" / "inventory.db"),
                protected_backup_path=str(root / "computer-backups"),
            )

            with (
                patch.object(config, "DEVICE_SETTINGS_DIR", device_dir),
                patch.object(config, "DEVICE_SETTINGS_PATH", device_file),
                patch.object(config, "CONFIG_PATH", portable_config),
                patch.object(config, "PORTABLE_DATA_DIR", root / "portable"),
            ):
                saved = config.save_device_backup_settings(
                    protected_backup_path=settings.protected_backup_path,
                    setup_completed=True,
                )
                config.save_settings(settings)

                self.assertTrue(saved)
                self.assertTrue(config.device_backup_setup_completed())
                self.assertEqual(
                    config.load_device_settings()["protected_backup_path"],
                    settings.protected_backup_path,
                )
                self.assertIn('"protected_backup_path": ""', portable_config.read_text(encoding="utf-8"))

    def test_compressed_backup_is_copied_to_protected_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(
                db_path=str(root / "portable" / "inventory.db"),
                protected_backup_path=str(root / "protected"),
                backup_interval_ops=5,
            )

            database = InventoryDatabase(settings)
            portable_backup = database.create_backup(reason="test")
            protected_backup = database.last_protected_backup_path

            self.assertTrue(portable_backup.exists())
            self.assertIsNotNone(protected_backup)
            self.assertTrue(protected_backup.exists())
            self.assertEqual(portable_backup.name, protected_backup.name)
            self.assertIsNone(database.last_protected_backup_error)

            with zipfile.ZipFile(portable_backup) as archive:
                self.assertEqual(archive.namelist(), ["inventory.db"])
            with zipfile.ZipFile(protected_backup) as archive:
                self.assertEqual(archive.namelist(), ["inventory.db"])

    def test_unavailable_protected_folder_does_not_block_portable_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            blocking_file = root / "not-a-directory"
            blocking_file.write_text("block directory creation", encoding="utf-8")
            settings = AppSettings(
                db_path=str(root / "portable" / "inventory.db"),
                protected_backup_path=str(blocking_file / "protected"),
                backup_interval_ops=5,
            )

            database = InventoryDatabase(settings)
            portable_backup = database.create_backup(reason="test")

            self.assertTrue(portable_backup.exists())
            self.assertIsNone(database.last_protected_backup_path)
            self.assertTrue(database.last_protected_backup_error)

    def test_empty_protected_setting_keeps_portable_backup_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = AppSettings(
                db_path=str(root / "portable" / "inventory.db"),
                protected_backup_path="",
                backup_interval_ops=5,
            )

            database = InventoryDatabase(settings)
            portable_backup = database.create_backup(reason="test")

            self.assertTrue(portable_backup.exists())
            self.assertIsNone(settings.protected_backup_dir)
            self.assertIsNone(database.last_protected_backup_path)
            self.assertIsNone(database.last_protected_backup_error)


if __name__ == "__main__":
    unittest.main()
