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
from .wings_catalog_official_import import WINGS_OFFICIAL_IMPORT_ADDITIONS
from .catalog_inventory import COUNT_SCHEMA
from .cic import CIC_SCHEMA


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

CREATE TABLE IF NOT EXISTS item_metadata (
    barcode_id TEXT PRIMARY KEY REFERENCES items(barcode_id) ON DELETE CASCADE,
    tags_json TEXT NOT NULL DEFAULT '[]',
    family TEXT NOT NULL DEFAULT '',
    season TEXT NOT NULL DEFAULT 'Unclassified',
    image_png TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS barcode_aliases (
    alias_barcode_id TEXT PRIMARY KEY,
    canonical_barcode_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (canonical_barcode_id) REFERENCES items (barcode_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventory_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time TEXT NOT NULL,
    action TEXT NOT NULL,
    barcode_id TEXT NOT NULL,
    wings_item_no TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    variant TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT '',
    quantity_change INTEGER NOT NULL DEFAULT 0,
    total_before INTEGER NOT NULL DEFAULT 0,
    total_after INTEGER NOT NULL DEFAULT 0,
    available_before INTEGER NOT NULL DEFAULT 0,
    available_after INTEGER NOT NULL DEFAULT 0,
    details TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'Admin code 3 - Williams'
);

CREATE TABLE IF NOT EXISTS cadets (
    cadet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cadet_size_entries (
    size_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cadet_id INTEGER NOT NULL,
    size_label TEXT NOT NULL COLLATE NOCASE,
    size_value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    catalog_item_no TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(cadet_id, size_label),
    FOREIGN KEY (cadet_id) REFERENCES cadets (cadet_id) ON DELETE CASCADE
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
    disposition TEXT NOT NULL DEFAULT '',
    condition_notes TEXT DEFAULT '',
    FOREIGN KEY (barcode_id) REFERENCES items (barcode_id),
    FOREIGN KEY (cadet_id) REFERENCES cadets (cadet_id),
    FOREIGN KEY (approved_by_admin_id) REFERENCES admin_codes (admin_id),
    FOREIGN KEY (return_approved_by_admin_id) REFERENCES admin_codes (admin_id)
);

CREATE TABLE IF NOT EXISTS acquisition_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cadet_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    item_notes_json TEXT NOT NULL,
    undone_at TEXT NOT NULL DEFAULT '',
    undone_by TEXT NOT NULL DEFAULT ''
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

CREATE TABLE IF NOT EXISTS ace_feature_flags (
    feature_key TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_barcode_aliases_canonical ON barcode_aliases(canonical_barcode_id);
CREATE INDEX IF NOT EXISTS idx_wings_catalog_name ON wings_catalog(item_name);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_cadets_full_name ON cadets(full_name);
CREATE INDEX IF NOT EXISTS idx_cadet_size_entries_cadet ON cadet_size_entries(cadet_id);
CREATE INDEX IF NOT EXISTS idx_admin_codes_active ON admin_codes(is_active);
CREATE INDEX IF NOT EXISTS idx_transactions_barcode_open ON transactions(barcode_id, return_time);
CREATE INDEX IF NOT EXISTS idx_transactions_cadet_email ON transactions(cadet_email);
CREATE INDEX IF NOT EXISTS idx_transactions_checkout ON transactions(checkout_time);
CREATE INDEX IF NOT EXISTS idx_transactions_return ON transactions(return_time);
CREATE INDEX IF NOT EXISTS idx_custom_index_system ON custom_index_items(uniform_system);
CREATE INDEX IF NOT EXISTS idx_inventory_changes_event_time ON inventory_changes(event_time);
CREATE INDEX IF NOT EXISTS idx_inventory_changes_barcode ON inventory_changes(barcode_id);

CREATE TRIGGER IF NOT EXISTS trg_items_reject_identical_insert
BEFORE INSERT ON items
WHEN EXISTS (
    SELECT 1
    FROM items existing
    WHERE lower(trim(COALESCE(existing.wings_item_no, ''))) = lower(trim(COALESCE(NEW.wings_item_no, '')))
      AND lower(trim(existing.item_name)) = lower(trim(NEW.item_name))
      AND lower(trim(existing.category)) = lower(trim(NEW.category))
      AND lower(trim(existing.variant)) = lower(trim(NEW.variant))
      AND lower(trim(existing.item_type)) = lower(trim(NEW.item_type))
)
BEGIN
    SELECT RAISE(ABORT, 'An identical inventory item already has a barcode.');
END;

CREATE TRIGGER IF NOT EXISTS trg_items_reject_reserved_alias_insert
BEFORE INSERT ON items
WHEN EXISTS (
    SELECT 1
    FROM barcode_aliases aliases
    WHERE aliases.alias_barcode_id = NEW.barcode_id COLLATE NOCASE
)
BEGIN
    SELECT RAISE(ABORT, 'That barcode is reserved by an existing barcode alias.');
END;

CREATE TRIGGER IF NOT EXISTS trg_aliases_reject_active_item_insert
BEFORE INSERT ON barcode_aliases
WHEN EXISTS (
    SELECT 1
    FROM items
    WHERE items.barcode_id = NEW.alias_barcode_id COLLATE NOCASE
)
BEGIN
    SELECT RAISE(ABORT, 'An active inventory barcode cannot also be a barcode alias.');
END;

CREATE TRIGGER IF NOT EXISTS trg_aliases_reject_active_item_update
BEFORE UPDATE OF alias_barcode_id ON barcode_aliases
WHEN EXISTS (
    SELECT 1
    FROM items
    WHERE items.barcode_id = NEW.alias_barcode_id COLLATE NOCASE
)
BEGIN
    SELECT RAISE(ABORT, 'An active inventory barcode cannot also be a barcode alias.');
END;

CREATE TRIGGER IF NOT EXISTS trg_items_inventory_change_insert
AFTER INSERT ON items
BEGIN
    INSERT INTO inventory_changes(
        event_time, action, barcode_id, wings_item_no, item_name, category,
        variant, item_type, quantity_change, total_before, total_after,
        available_before, available_after, details, source
    ) VALUES (
        strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'),
        'New Item Added', NEW.barcode_id, COALESCE(NEW.wings_item_no, ''),
        NEW.item_name, NEW.category, NEW.variant, NEW.item_type,
        NEW.total_quantity, 0, NEW.total_quantity, 0, NEW.available_quantity,
        'A new inventory barcode was created.', 'Admin code 3 - Williams'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_items_inventory_change_update
AFTER UPDATE ON items
WHEN OLD.total_quantity <> NEW.total_quantity
  OR OLD.item_name <> NEW.item_name
  OR OLD.category <> NEW.category
  OR OLD.variant <> NEW.variant
  OR OLD.item_type <> NEW.item_type
  OR COALESCE(OLD.wings_item_no, '') <> COALESCE(NEW.wings_item_no, '')
  OR (
      OLD.status <> NEW.status
      AND (
          OLD.status IN ('Lost', 'Retired')
          OR NEW.status IN ('Lost', 'Retired')
      )
  )
BEGIN
    INSERT INTO inventory_changes(
        event_time, action, barcode_id, wings_item_no, item_name, category,
        variant, item_type, quantity_change, total_before, total_after,
        available_before, available_after, details, source
    ) VALUES (
        strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'),
        CASE
            WHEN NEW.total_quantity > OLD.total_quantity THEN 'Quantity Added'
            WHEN NEW.total_quantity < OLD.total_quantity THEN 'Quantity Removed'
            WHEN OLD.status <> NEW.status THEN 'Status Changed'
            ELSE 'Item Details Edited'
        END,
        NEW.barcode_id, COALESCE(NEW.wings_item_no, ''), NEW.item_name,
        NEW.category, NEW.variant, NEW.item_type,
        NEW.total_quantity - OLD.total_quantity,
        OLD.total_quantity, NEW.total_quantity,
        OLD.available_quantity, NEW.available_quantity,
        CASE
            WHEN NEW.total_quantity <> OLD.total_quantity
                THEN 'The inventory total was changed.'
            WHEN OLD.status <> NEW.status
                THEN 'Status changed from ' || OLD.status || ' to ' || NEW.status || '.'
            ELSE 'The item description or catalog mapping was changed.'
        END,
        'Admin code 3 - Williams'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_items_inventory_change_delete
AFTER DELETE ON items
BEGIN
    INSERT INTO inventory_changes(
        event_time, action, barcode_id, wings_item_no, item_name, category,
        variant, item_type, quantity_change, total_before, total_after,
        available_before, available_after, details, source
    ) VALUES (
        strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'),
        'Item Deleted', OLD.barcode_id, COALESCE(OLD.wings_item_no, ''),
        OLD.item_name, OLD.category, OLD.variant, OLD.item_type,
        -OLD.total_quantity, OLD.total_quantity, 0,
        OLD.available_quantity, 0,
        'The inventory barcode was permanently deleted.', 'Admin code 3 - Williams'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_inventory_changes_reassign_automatic
AFTER INSERT ON inventory_changes
WHEN NEW.source = 'Automatic audit'
BEGIN
    UPDATE inventory_changes
    SET source = 'Admin code 3 - Williams'
    WHERE change_id = NEW.change_id;
END;
"""


SCHEMA_SQL += COUNT_SCHEMA

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
            connection.executescript(CIC_SCHEMA)
            from .cic_sharepoint import REMOTE_SCHEMA
            connection.executescript(REMOTE_SCHEMA)
            for table,column,definition in [('cic_cards','assessment_json',"TEXT NOT NULL DEFAULT '{}'"),('cic_lines','group_key',"TEXT NOT NULL DEFAULT ''"),('cic_cards','intake_issues_json',"TEXT NOT NULL DEFAULT '[]'")]:
                if column not in {r['name'] for r in connection.execute('PRAGMA table_info('+table+')')}:
                    connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
            self._migrate_schema(connection)
            self._seed_catalog(connection)
            connection.commit()
        finally:
            connection.close()
        self.create_backup(reason="launch")

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        transaction_columns = {row['name'] for row in connection.execute('PRAGMA table_info(transactions)')}
        for column in ('loan_due_date', 'loan_purpose'):
            if column not in transaction_columns:
                connection.execute(f"ALTER TABLE transactions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        connection.execute('''CREATE TABLE IF NOT EXISTS loan_events (
            event_id INTEGER PRIMARY KEY, event_time TEXT NOT NULL,
            transaction_id INTEGER, action TEXT NOT NULL, details TEXT NOT NULL,
            recorded_by TEXT NOT NULL)''')
        connection.execute(
            """
            UPDATE inventory_changes
            SET source = 'Admin code 3 - Williams'
            WHERE source = 'Automatic audit'
            """
        )
        audit_trigger_names = (
            "trg_items_inventory_change_insert",
            "trg_items_inventory_change_update",
            "trg_items_inventory_change_delete",
        )
        audit_triggers = connection.execute(
            f"""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'trigger'
              AND name IN ({', '.join('?' for _ in audit_trigger_names)})
            """,
            audit_trigger_names,
        ).fetchall()
        for trigger in audit_triggers:
            trigger_sql = str(trigger["sql"] or "")
            if "Automatic audit" not in trigger_sql:
                continue
            trigger_name = str(trigger["name"])
            connection.execute(f'DROP TRIGGER "{trigger_name}"')
            connection.execute(
                trigger_sql.replace("Automatic audit", "Admin code 3 - Williams")
            )

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

        size_entry_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cadet_size_entries)").fetchall()
        }
        if "category" not in size_entry_columns:
            connection.execute(
                "ALTER TABLE cadet_size_entries ADD COLUMN category TEXT NOT NULL DEFAULT ''"
            )
        if "catalog_item_no" not in size_entry_columns:
            connection.execute(
                "ALTER TABLE cadet_size_entries ADD COLUMN catalog_item_no TEXT NOT NULL DEFAULT ''"
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
        if "disposition" not in transaction_columns:
            connection.execute("ALTER TABLE transactions ADD COLUMN disposition TEXT NOT NULL DEFAULT ''")

        self._merge_duplicate_cadets(connection)
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_cadets_normalized_email "
            "ON cadets(lower(trim(email)))"
        )

        connection.execute(
            """
            UPDATE transactions
            SET disposition = 'Returned'
            WHERE return_time IS NOT NULL AND trim(disposition) = ''
            """
        )

        connection.execute("CREATE INDEX IF NOT EXISTS idx_transactions_cadet_id ON transactions(cadet_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_approved_by_admin_id ON transactions(approved_by_admin_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_return_approved_by_admin_id ON transactions(return_approved_by_admin_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_disposition ON transactions(disposition)"
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

    @staticmethod
    def _merge_duplicate_cadets(connection: sqlite3.Connection) -> None:
        """Merge legacy cadet rows that differ only by email case or whitespace."""
        duplicate_emails = connection.execute(
            """
            SELECT lower(trim(email)) AS normalized_email
            FROM cadets
            GROUP BY lower(trim(email))
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for duplicate_group in duplicate_emails:
            normalized_email = str(duplicate_group["normalized_email"] or "")
            rows = connection.execute(
                """
                SELECT cadet_id, full_name, email, created_at, updated_at
                FROM cadets
                WHERE lower(trim(email)) = ?
                ORDER BY cadet_id
                """,
                (normalized_email,),
            ).fetchall()
            if len(rows) < 2:
                continue

            keeper = rows[0]
            keeper_id = int(keeper["cadet_id"])
            keeper_name = str(keeper["full_name"])
            keeper_email = normalized_email
            for duplicate in rows[1:]:
                duplicate_id = int(duplicate["cadet_id"])
                size_entries = connection.execute(
                    """
                    SELECT *
                    FROM cadet_size_entries
                    WHERE cadet_id = ?
                    ORDER BY size_entry_id
                    """,
                    (duplicate_id,),
                ).fetchall()
                for entry in size_entries:
                    existing_entry = connection.execute(
                        """
                        SELECT *
                        FROM cadet_size_entries
                        WHERE cadet_id = ? AND size_label = ? COLLATE NOCASE
                        """,
                        (keeper_id, entry["size_label"]),
                    ).fetchone()
                    if existing_entry is None:
                        connection.execute(
                            "UPDATE cadet_size_entries SET cadet_id = ? WHERE size_entry_id = ?",
                            (keeper_id, entry["size_entry_id"]),
                        )
                    else:
                        if str(entry["updated_at"] or "") > str(existing_entry["updated_at"] or ""):
                            connection.execute(
                                """
                                UPDATE cadet_size_entries
                                SET size_value = ?, category = ?, catalog_item_no = ?, notes = ?,
                                    updated_at = ?
                                WHERE size_entry_id = ?
                                """,
                                (
                                    entry["size_value"],
                                    entry["category"],
                                    entry["catalog_item_no"],
                                    entry["notes"],
                                    entry["updated_at"],
                                    existing_entry["size_entry_id"],
                                ),
                            )
                        connection.execute(
                            "DELETE FROM cadet_size_entries WHERE size_entry_id = ?",
                            (entry["size_entry_id"],),
                        )

                connection.execute(
                    """
                    UPDATE transactions
                    SET cadet_id = ?, cadet_name = ?, cadet_email = ?
                    WHERE cadet_id = ?
                       OR (cadet_id IS NULL AND lower(trim(cadet_email)) = ?)
                    """,
                    (keeper_id, keeper_name, keeper_email, duplicate_id, normalized_email),
                )
                connection.execute("DELETE FROM cadets WHERE cadet_id = ?", (duplicate_id,))

            connection.execute(
                "UPDATE cadets SET email = ?, updated_at = ? WHERE cadet_id = ?",
                (keeper_email, utc_now(), keeper_id),
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
                    row.get("source")
                    or ("WINGS 26-Feb-26" if str(row["item_no"]).isdigit() else "Local Index"),
                    1 if str(row["item_no"]).isdigit() else 0,
                )
                for row in (*WINGS_CATALOG, *WINGS_OFFICIAL_IMPORT_ADDITIONS)
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
