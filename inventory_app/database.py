from __future__ import annotations

import hashlib
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from .config import AppSettings, ensure_app_directories
from .defaults import (
    DEFAULT_CATEGORIES,
    DEFAULT_ITEM_NAMES,
    DEFAULT_ITEM_TYPES,
    DEFAULT_VARIANTS,
    ITEM_NAME_ALIASES,
    ITEM_TYPE_ALIASES,
)
from .wings_catalog import WINGS_CATALOG


# Compatibility constants are intentionally empty in the clean deployment.
EASTER_EGG_ADMINS = []
EASTER_EGG_CADETS = []
EASTER_EGG_OUTFIT_HISTORY = []
BACKUP_RETENTION_COUNT = 10


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
    barcode_id TEXT PRIMARY KEY,
    wings_item_no TEXT,
    item_name TEXT NOT NULL,
    category TEXT NOT NULL,
    variant TEXT NOT NULL,
    item_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Available', 'Checked Out', 'Retired', 'Lost')),
    notes TEXT DEFAULT '',
    total_quantity INTEGER NOT NULL DEFAULT 1 CHECK (total_quantity >= 0),
    available_quantity INTEGER NOT NULL DEFAULT 1 CHECK (available_quantity >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wings_catalog (
    item_no TEXT PRIMARY KEY,
    item_name TEXT NOT NULL,
    size TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    subcategory TEXT NOT NULL DEFAULT '',
    sex TEXT NOT NULL DEFAULT '',
    stock_number TEXT NOT NULL DEFAULT '',
    uom TEXT NOT NULL DEFAULT '',
    writeoffs TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'WINGS',
    is_wings INTEGER NOT NULL DEFAULT 1 CHECK (is_wings IN (0, 1))
);

CREATE TABLE IF NOT EXISTS cadets (
    cadet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode_id TEXT NOT NULL,
    cadet_id INTEGER,
    cadet_name TEXT NOT NULL,
    cadet_email TEXT NOT NULL,
    checkout_time TEXT NOT NULL,
    approved_by_admin_id INTEGER,
    approved_by_name TEXT DEFAULT '',
    approved_by_role TEXT DEFAULT '',
    approved_at TEXT,
    return_time TEXT,
    return_approved_by_admin_id INTEGER,
    return_approved_by_name TEXT DEFAULT '',
    return_approved_by_role TEXT DEFAULT '',
    return_approved_at TEXT,
    condition_notes TEXT DEFAULT '',
    FOREIGN KEY (barcode_id) REFERENCES items (barcode_id),
    FOREIGN KEY (cadet_id) REFERENCES cadets (cadet_id),
    FOREIGN KEY (approved_by_admin_id) REFERENCES admin_codes (admin_id),
    FOREIGN KEY (return_approved_by_admin_id) REFERENCES admin_codes (admin_id)
);

CREATE TABLE IF NOT EXISTS admin_codes (
    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'ADMIN CADET',
    code_hash TEXT NOT NULL UNIQUE,
    code_value TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS barcode_sequences (
    prefix TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS catalog_values (
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, value)
);

CREATE TABLE IF NOT EXISTS custom_index_items (
    index_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    uniform_system TEXT NOT NULL,
    configuration TEXT NOT NULL DEFAULT 'Standard',
    size_system TEXT NOT NULL DEFAULT 'Apparel Size',
    search_aliases TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hidden_index_items (
    item_no TEXT PRIMARY KEY,
    hidden_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_wings_catalog_name ON wings_catalog(item_name);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_cadets_full_name ON cadets(full_name);
CREATE INDEX IF NOT EXISTS idx_admin_codes_active ON admin_codes(is_active);
CREATE INDEX IF NOT EXISTS idx_transactions_barcode_open ON transactions(barcode_id, return_time);
CREATE INDEX IF NOT EXISTS idx_transactions_cadet_email ON transactions(cadet_email);
CREATE INDEX IF NOT EXISTS idx_transactions_checkout ON transactions(checkout_time);
CREATE INDEX IF NOT EXISTS idx_transactions_return ON transactions(return_time);
CREATE INDEX IF NOT EXISTS idx_custom_index_system ON custom_index_items(uniform_system);
"""


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class InventoryDatabase:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._write_counter = 0
        self.last_protected_backup_path: Path | None = None
        self.last_protected_backup_error: str | None = None
        ensure_app_directories(self.settings)
        self.initialize()

    @property
    def db_path(self) -> Path:
        return self.settings.database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        ensure_app_directories(self.settings)
        connection = self.connect()
        try:
            connection.executescript(SCHEMA_SQL)
            self._migrate_schema(connection)
            self._seed_catalog(connection)
            connection.commit()
        finally:
            connection.close()
        self.create_backup(reason="launch")

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        item_columns = {row["name"] for row in connection.execute("PRAGMA table_info(items)").fetchall()}
        if "wings_item_no" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN wings_item_no TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_items_wings_item_no ON items(wings_item_no)")

        wings_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(wings_catalog)").fetchall()
        }
        if "source" not in wings_columns:
            connection.execute("ALTER TABLE wings_catalog ADD COLUMN source TEXT NOT NULL DEFAULT 'WINGS'")
        if "is_wings" not in wings_columns:
            connection.execute(
                "ALTER TABLE wings_catalog ADD COLUMN is_wings INTEGER NOT NULL DEFAULT 1"
            )

        cadet_columns = {row["name"] for row in connection.execute("PRAGMA table_info(cadets)").fetchall()}
        if "updated_at" not in cadet_columns:
            connection.execute("ALTER TABLE cadets ADD COLUMN updated_at TEXT")
        connection.execute(
            "UPDATE cadets SET updated_at = COALESCE(updated_at, created_at) WHERE updated_at IS NULL OR updated_at = ''"
        )

        admin_columns = {row["name"] for row in connection.execute("PRAGMA table_info(admin_codes)").fetchall()}
        if "code_value" not in admin_columns:
            connection.execute("ALTER TABLE admin_codes ADD COLUMN code_value TEXT NOT NULL DEFAULT ''")

        transaction_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(transactions)").fetchall()
        }
        if "cadet_id" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN cadet_id INTEGER")
        if "approved_by_admin_id" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN approved_by_admin_id INTEGER")
        if "approved_by_name" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN approved_by_name TEXT DEFAULT ''")
        if "approved_by_role" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN approved_by_role TEXT DEFAULT ''")
        if "approved_at" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN approved_at TEXT")
        if "return_approved_by_admin_id" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN return_approved_by_admin_id INTEGER")
        if "return_approved_by_name" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN return_approved_by_name TEXT DEFAULT ''")
        if "return_approved_by_role" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN return_approved_by_role TEXT DEFAULT ''")
        if "return_approved_at" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN return_approved_at TEXT")

        connection.execute("CREATE INDEX IF NOT EXISTS idx_transactions_cadet_id ON transactions(cadet_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_approved_by_admin_id ON transactions(approved_by_admin_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_return_approved_by_admin_id ON transactions(return_approved_by_admin_id)"
        )

        connection.execute(
            """
            UPDATE transactions
            SET cadet_id = (
                SELECT cadets.cadet_id
                FROM cadets
                WHERE lower(cadets.email) = lower(transactions.cadet_email)
                LIMIT 1
            )
            WHERE cadet_id IS NULL
            """
        )

        # Remove redundant category prefixes from legacy item types. Barcode
        # IDs stay untouched so labels already in use continue to scan.
        for legacy_type, canonical_type in ITEM_TYPE_ALIASES.items():
            connection.execute(
                "UPDATE items SET item_type = ? WHERE upper(item_type) = ?",
                (canonical_type, legacy_type),
            )
            connection.execute(
                "DELETE FROM catalog_values WHERE kind = 'item_type' AND upper(value) = ?",
                (legacy_type,),
            )
        for legacy_name, canonical_name in ITEM_NAME_ALIASES.items():
            connection.execute(
                "UPDATE items SET item_name = ? WHERE lower(item_name) = lower(?)",
                (canonical_name, legacy_name),
            )
            connection.execute(
                "DELETE FROM catalog_values WHERE kind = 'item_name' AND lower(value) = lower(?)",
                (legacy_name,),
            )

    def _seed_catalog(self, connection: sqlite3.Connection) -> None:
        connection.executemany(
            """
            INSERT INTO wings_catalog(
                item_no, item_name, size, category, subcategory, sex,
                stock_number, uom, writeoffs, source, is_wings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_no) DO UPDATE SET
                item_name = excluded.item_name,
                size = excluded.size,
                category = excluded.category,
                subcategory = excluded.subcategory,
                sex = excluded.sex,
                stock_number = excluded.stock_number,
                uom = excluded.uom,
                writeoffs = excluded.writeoffs,
                source = excluded.source,
                is_wings = excluded.is_wings
            """,
            [
                (
                    row["item_no"], row["item_name"], row["size"], row["category"],
                    row["subcategory"], row["sex"], row["stock_number"], row["uom"],
                    row["writeoffs"],
                    "WINGS 26-Feb-26" if str(row["item_no"]).isdigit() else "Local Index",
                    1 if str(row["item_no"]).isdigit() else 0,
                )
                for row in WINGS_CATALOG
            ],
        )
        for order, value in enumerate(DEFAULT_CATEGORIES, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO catalog_values(kind, value, sort_order) VALUES (?, ?, ?)",
                ("category", value, order),
            )
        for order, value in enumerate(DEFAULT_ITEM_TYPES, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO catalog_values(kind, value, sort_order) VALUES (?, ?, ?)",
                ("item_type", value, order),
            )
        for order, value in enumerate(DEFAULT_VARIANTS, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO catalog_values(kind, value, sort_order) VALUES (?, ?, ?)",
                ("variant", value, order),
            )
        for order, value in enumerate(DEFAULT_ITEM_NAMES, start=1):
            connection.execute(
                "INSERT OR IGNORE INTO catalog_values(kind, value, sort_order) VALUES (?, ?, ?)",
                ("item_name", value, order),
            )

    def _seed_easter_egg_identities(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            self._seed_easter_egg_admins(connection)
            self._seed_easter_egg_cadets(connection)
            self._seed_easter_egg_outfit_history(connection)
            self._refresh_autoincrement_sequence(connection, table_name="admin_codes", id_column="admin_id")
            self._refresh_autoincrement_sequence(connection, table_name="cadets", id_column="cadet_id")
            self._refresh_autoincrement_sequence(connection, table_name="transactions", id_column="transaction_id")
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

    def _seed_easter_egg_admins(self, connection: sqlite3.Connection) -> None:
        for seed in EASTER_EGG_ADMINS:
            desired_id = int(seed["admin_id"])
            matching_row = connection.execute(
                """
                SELECT admin_id
                FROM admin_codes
                WHERE lower(code_value) = lower(?)
                LIMIT 1
                """,
                (seed["code_value"],),
            ).fetchone()
            self._ensure_target_id_available(
                connection,
                table_name="admin_codes",
                id_column="admin_id",
                target_id=desired_id,
                keep_id=int(matching_row["admin_id"]) if matching_row is not None else None,
                child_updates=[
                    "UPDATE transactions SET approved_by_admin_id = ? WHERE approved_by_admin_id = ?",
                    "UPDATE transactions SET return_approved_by_admin_id = ? WHERE return_approved_by_admin_id = ?",
                ],
            )
            if matching_row is not None and int(matching_row["admin_id"]) != desired_id:
                self._move_row_id(
                    connection,
                    table_name="admin_codes",
                    id_column="admin_id",
                    old_id=int(matching_row["admin_id"]),
                    new_id=desired_id,
                    child_updates=[
                        "UPDATE transactions SET approved_by_admin_id = ? WHERE approved_by_admin_id = ?",
                        "UPDATE transactions SET return_approved_by_admin_id = ? WHERE return_approved_by_admin_id = ?",
                    ],
                )

            existing_row = connection.execute(
                "SELECT admin_id, created_at FROM admin_codes WHERE admin_id = ?",
                (desired_id,),
            ).fetchone()
            created_at = str(existing_row["created_at"]) if existing_row is not None else utc_now()
            code_hash = hashlib.sha256(str(seed["code_value"]).strip().encode("utf-8")).hexdigest()
            if existing_row is None:
                connection.execute(
                    """
                    INSERT INTO admin_codes(
                        admin_id, display_name, role, code_hash, code_value, created_at, updated_at, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        desired_id,
                        seed["display_name"],
                        seed["role"],
                        code_hash,
                        seed["code_value"],
                        created_at,
                        utc_now(),
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE admin_codes
                    SET display_name = ?, role = ?, code_hash = ?, code_value = ?, updated_at = ?, is_active = 1
                    WHERE admin_id = ?
                    """,
                    (
                        seed["display_name"],
                        seed["role"],
                        code_hash,
                        seed["code_value"],
                        utc_now(),
                        desired_id,
                    ),
                )

    def _seed_easter_egg_cadets(self, connection: sqlite3.Connection) -> None:
        for seed in EASTER_EGG_CADETS:
            desired_id = int(seed["cadet_id"])
            matching_row = connection.execute(
                """
                SELECT cadet_id
                FROM cadets
                WHERE lower(email) = lower(?) OR lower(full_name) = lower(?)
                LIMIT 1
                """,
                (seed["email"], seed["full_name"]),
            ).fetchone()
            self._ensure_target_id_available(
                connection,
                table_name="cadets",
                id_column="cadet_id",
                target_id=desired_id,
                keep_id=int(matching_row["cadet_id"]) if matching_row is not None else None,
                child_updates=[
                    "UPDATE transactions SET cadet_id = ? WHERE cadet_id = ?",
                ],
            )
            if matching_row is not None and int(matching_row["cadet_id"]) != desired_id:
                self._move_row_id(
                    connection,
                    table_name="cadets",
                    id_column="cadet_id",
                    old_id=int(matching_row["cadet_id"]),
                    new_id=desired_id,
                    child_updates=[
                        "UPDATE transactions SET cadet_id = ? WHERE cadet_id = ?",
                    ],
                )

            existing_row = connection.execute(
                "SELECT cadet_id, created_at FROM cadets WHERE cadet_id = ?",
                (desired_id,),
            ).fetchone()
            created_at = str(existing_row["created_at"]) if existing_row is not None else utc_now()
            if existing_row is None:
                connection.execute(
                    """
                    INSERT INTO cadets(cadet_id, full_name, email, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        desired_id,
                        seed["full_name"],
                        seed["email"],
                        created_at,
                        utc_now(),
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE cadets
                    SET full_name = ?, email = ?, updated_at = ?
                    WHERE cadet_id = ?
                    """,
                    (
                        seed["full_name"],
                        seed["email"],
                        utc_now(),
                        desired_id,
                    ),
                )

    def _seed_easter_egg_outfit_history(self, connection: sqlite3.Connection) -> None:
        admin_lookup = {int(seed["admin_id"]): seed for seed in EASTER_EGG_ADMINS}
        cadet_lookup = {int(seed["cadet_id"]): seed for seed in EASTER_EGG_CADETS}

        for entry in EASTER_EGG_OUTFIT_HISTORY:
            cadet_seed = cadet_lookup[int(entry["cadet_id"])]
            admin_seed = admin_lookup[int(entry["admin_id"])]
            desired_transaction_id = int(entry["transaction_id"])
            has_returned = bool(entry["return_time"])
            item_status = "Available" if has_returned else "Checked Out"
            available_quantity = 1 if has_returned else 0
            updated_at = str(entry["return_time"] or entry["checkout_time"])
            return_admin_id = int(entry["admin_id"]) if has_returned else None
            return_admin_name = admin_seed["display_name"] if has_returned else ""
            return_admin_role = admin_seed["role"] if has_returned else ""
            return_approved_at = entry["return_time"] if has_returned else None

            for kind, value in (
                ("category", str(entry["category"])),
                ("variant", str(entry["variant"])),
                ("item_type", str(entry["item_type"])),
                ("item_name", str(entry["item_name"])),
            ):
                connection.execute(
                    "INSERT OR IGNORE INTO catalog_values(kind, value, sort_order) VALUES (?, ?, 999)",
                    (kind, value),
                )

            existing_item = connection.execute(
                "SELECT barcode_id, created_at FROM items WHERE barcode_id = ?",
                (entry["barcode_id"],),
            ).fetchone()
            created_at = str(existing_item["created_at"]) if existing_item is not None else str(entry["checkout_time"])
            if existing_item is None:
                connection.execute(
                    """
                    INSERT INTO items(
                        barcode_id, item_name, category, variant, item_type, status, notes,
                        total_quantity, available_quantity, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        entry["barcode_id"],
                        entry["item_name"],
                        entry["category"],
                        entry["variant"],
                        entry["item_type"],
                        item_status,
                        entry["notes"],
                        available_quantity,
                        created_at,
                        updated_at,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE items
                    SET
                        item_name = ?,
                        category = ?,
                        variant = ?,
                        item_type = ?,
                        status = ?,
                        notes = ?,
                        total_quantity = 1,
                        available_quantity = ?,
                        updated_at = ?
                    WHERE barcode_id = ?
                    """,
                    (
                        entry["item_name"],
                        entry["category"],
                        entry["variant"],
                        entry["item_type"],
                        item_status,
                        entry["notes"],
                        available_quantity,
                        updated_at,
                        entry["barcode_id"],
                    ),
                )

            existing_transaction = connection.execute(
                """
                SELECT transaction_id
                FROM transactions
                WHERE barcode_id = ? AND cadet_id = ?
                ORDER BY transaction_id
                LIMIT 1
                """,
                (entry["barcode_id"], entry["cadet_id"]),
            ).fetchone()
            self._ensure_target_id_available(
                connection,
                table_name="transactions",
                id_column="transaction_id",
                target_id=desired_transaction_id,
                keep_id=int(existing_transaction["transaction_id"]) if existing_transaction is not None else None,
                child_updates=[],
            )
            if existing_transaction is not None and int(existing_transaction["transaction_id"]) != desired_transaction_id:
                self._move_row_id(
                    connection,
                    table_name="transactions",
                    id_column="transaction_id",
                    old_id=int(existing_transaction["transaction_id"]),
                    new_id=desired_transaction_id,
                    child_updates=[],
                )
                existing_transaction = connection.execute(
                    """
                    SELECT transaction_id
                    FROM transactions
                    WHERE transaction_id = ?
                    """,
                    (desired_transaction_id,),
                ).fetchone()
            if existing_transaction is None:
                connection.execute(
                    """
                    INSERT INTO transactions(
                        transaction_id, barcode_id, cadet_id, cadet_name, cadet_email, checkout_time,
                        approved_by_admin_id, approved_by_name, approved_by_role, approved_at,
                        return_time, return_approved_by_admin_id, return_approved_by_name,
                        return_approved_by_role, return_approved_at, condition_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        desired_transaction_id,
                        entry["barcode_id"],
                        entry["cadet_id"],
                        cadet_seed["full_name"],
                        cadet_seed["email"],
                        entry["checkout_time"],
                        entry["admin_id"],
                        admin_seed["display_name"],
                        admin_seed["role"],
                        entry["checkout_time"],
                        entry["return_time"],
                        return_admin_id,
                        return_admin_name,
                        return_admin_role,
                        return_approved_at,
                        entry["notes"],
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE transactions
                    SET
                        cadet_id = ?,
                        cadet_name = ?,
                        cadet_email = ?,
                        checkout_time = ?,
                        approved_by_admin_id = ?,
                        approved_by_name = ?,
                        approved_by_role = ?,
                        approved_at = ?,
                        return_time = ?,
                        return_approved_by_admin_id = ?,
                        return_approved_by_name = ?,
                        return_approved_by_role = ?,
                        return_approved_at = ?,
                        condition_notes = ?
                    WHERE transaction_id = ?
                    """,
                    (
                        entry["cadet_id"],
                        cadet_seed["full_name"],
                        cadet_seed["email"],
                        entry["checkout_time"],
                        entry["admin_id"],
                        admin_seed["display_name"],
                        admin_seed["role"],
                        entry["checkout_time"],
                        entry["return_time"],
                        return_admin_id,
                        return_admin_name,
                        return_admin_role,
                        return_approved_at,
                        entry["notes"],
                        desired_transaction_id,
                    ),
                )

    def _ensure_target_id_available(
        self,
        connection: sqlite3.Connection,
        *,
        table_name: str,
        id_column: str,
        target_id: int,
        keep_id: int | None,
        child_updates: list[str],
    ) -> None:
        occupant = connection.execute(
            f"SELECT {id_column} FROM {table_name} WHERE {id_column} = ?",
            (target_id,),
        ).fetchone()
        if occupant is None:
            return
        occupant_id = int(occupant[id_column])
        if keep_id is not None and occupant_id == keep_id:
            return

        replacement_id = self._next_free_id(connection, table_name=table_name, id_column=id_column)
        self._move_row_id(
            connection,
            table_name=table_name,
            id_column=id_column,
            old_id=occupant_id,
            new_id=replacement_id,
            child_updates=child_updates,
        )

    def _move_row_id(
        self,
        connection: sqlite3.Connection,
        *,
        table_name: str,
        id_column: str,
        old_id: int,
        new_id: int,
        child_updates: list[str],
    ) -> None:
        if old_id == new_id:
            return
        connection.execute(
            f"UPDATE {table_name} SET {id_column} = ? WHERE {id_column} = ?",
            (new_id, old_id),
        )
        for statement in child_updates:
            connection.execute(statement, (new_id, old_id))

    def _next_free_id(self, connection: sqlite3.Connection, *, table_name: str, id_column: str) -> int:
        row = connection.execute(
            f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS next_id FROM {table_name}"
        ).fetchone()
        return int(row["next_id"])

    def _refresh_autoincrement_sequence(
        self,
        connection: sqlite3.Connection,
        *,
        table_name: str,
        id_column: str,
    ) -> None:
        max_row = connection.execute(
            f"SELECT COALESCE(MAX({id_column}), 0) AS max_id FROM {table_name}"
        ).fetchone()
        max_id = int(max_row["max_id"])
        existing = connection.execute(
            "SELECT 1 FROM sqlite_sequence WHERE name = ?",
            (table_name,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                (table_name, max_id),
            )
        else:
            connection.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                (max_id, table_name),
            )

    def record_lookup_value(self, kind: str, value: str, *, connection: sqlite3.Connection | None = None) -> None:
        cleaned = value.strip().upper()
        if not cleaned:
            return

        if connection is None:
            with self.connect() as owned_connection:
                self.record_lookup_value(kind, cleaned, connection=owned_connection)
                owned_connection.commit()
            return

        connection.execute(
            "INSERT OR IGNORE INTO catalog_values(kind, value, sort_order) VALUES (?, ?, 999)",
            (kind, cleaned),
        )

    def create_backup(self, *, reason: str) -> Path:
        ensure_app_directories(self.settings)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self.settings.backup_dir / f"inventory_{reason}_{timestamp}.zip"
        temporary_db_path = self.settings.backup_dir / f".inventory_{reason}_{timestamp}.tmp.db"
        source = sqlite3.connect(self.db_path)
        destination = sqlite3.connect(temporary_db_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

        try:
            with zipfile.ZipFile(
                backup_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                archive.write(temporary_db_path, arcname="inventory.db")
        finally:
            temporary_db_path.unlink(missing_ok=True)

        self._prune_old_backups(self.settings.backup_dir)
        self._copy_to_protected_backup(backup_path)
        return backup_path

    def _copy_to_protected_backup(self, backup_path: Path) -> Path | None:
        self.last_protected_backup_path = None
        self.last_protected_backup_error = None
        protected_dir = self.settings.protected_backup_dir
        if protected_dir is None:
            return None

        try:
            if protected_dir == self.settings.backup_dir.resolve():
                self.last_protected_backup_path = backup_path
                return backup_path
            protected_dir.mkdir(parents=True, exist_ok=True)
            protected_path = protected_dir / backup_path.name
            shutil.copy2(backup_path, protected_path)
            self._prune_old_backups(protected_dir)
            self.last_protected_backup_path = protected_path
            return protected_path
        except OSError as exc:
            # The live USB database must remain usable even when a saved
            # computer, network, or cloud-backed location is unavailable.
            self.last_protected_backup_error = str(exc)
            return None

    def _prune_old_backups(self, backup_dir: Path) -> None:
        candidates = [
            path
            for path in backup_dir.glob("inventory_*")
            if path.is_file() and path.suffix.casefold() in {".db", ".zip"}
        ]
        candidates.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
        for expired_path in candidates[BACKUP_RETENTION_COUNT:]:
            expired_path.unlink(missing_ok=True)

    def note_write(self) -> None:
        self._write_counter += 1
        if self._write_counter >= max(1, self.settings.backup_interval_ops):
            self.create_backup(reason="autosave")
            self._write_counter = 0

    def clone_database(self, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.db_path)
        destination = sqlite3.connect(target_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return target_path

    def swap_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self._write_counter = 0
        ensure_app_directories(self.settings)
        self.initialize()
