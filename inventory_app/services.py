from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import zipfile
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from .barcode_utils import compact_wings_barcode, compose_barcode, normalize_token, open_file, write_label_pdf
from .config import AppSettings, BASE_DIR
from .database import EASTER_EGG_ADMINS, EASTER_EGG_CADETS, EASTER_EGG_OUTFIT_HISTORY, InventoryDatabase, utc_now
from .deployment import create_transfer_installer, ensure_icon_file
from .defaults import ITEM_NAME_ALIASES, ITEM_TYPE_ALIASES
from .image_utils import read_png_dimensions, scaled_dimensions
from .report_workbook import write_report_workbook
from .item_metadata import enrich_items, inventory_analysis
from .wings_catalog import WINGS_COLUMNS


NAME_PATTERN = re.compile(r"^\s*([^,]+?)\s*,\s*(?:([A-Za-z]{1,3})\.?\s*,\s*|,\s*)?([^,]+?)\s*$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+$")
MASTER_ADMIN_CODE = "Det005"
MASTER_ADMIN_ROLE = "CADRE"
DEFAULT_ADMIN_ROLE = "ADMIN CADET"
ACQUISITION_DISPOSITIONS = {"Acquired / Permanent Issue", "Purchased"}
RESERVED_ADMIN_IDS = {int(seed["admin_id"]) for seed in EASTER_EGG_ADMINS}
RESERVED_CADET_IDS = {int(seed["cadet_id"]) for seed in EASTER_EGG_CADETS}
EASTER_EGG_BARCODE_IDS = tuple(str(entry["barcode_id"]).strip().upper() for entry in EASTER_EGG_OUTFIT_HISTORY)
EASTER_EGG_CATALOG_VALUES = {
    "category": {str(entry["category"]).strip().upper() for entry in EASTER_EGG_OUTFIT_HISTORY},
    "variant": {str(entry["variant"]).strip().upper() for entry in EASTER_EGG_OUTFIT_HISTORY},
    "item_type": {str(entry["item_type"]).strip().upper() for entry in EASTER_EGG_OUTFIT_HISTORY},
    "item_name": {str(entry["item_name"]).strip().upper() for entry in EASTER_EGG_OUTFIT_HISTORY},
}
RANK_CATALOG_VERSION = "rank-catalog-v4-official-metal-no-notes"
INVENTORY_CHANGE_AUDIT_VERSION = "inventory-change-audit-v1"
LOCAL_INVENTORY_MAPPING_SOURCE = "A.C.E. Local Inventory Mapping"
ONE_SIZE_VARIANT = "ONE SIZE"
REPORT_COLUMN_LABELS = {
    "transaction_id": "Transaction #",
    "change_id": "Change #",
    "event_time": "Date & Time",
    "action": "Change",
    "barcode_id": "Barcode",
    "wings_item_no": "WINGS / Local Item #",
    "item_name": "Item",
    "category": "Category",
    "variant": "Size / Variant",
    "item_type": "Type",
    "cadet_name": "Cadet",
    "cadet_email": "Cadet Email",
    "approved_by_name": "Approved By",
    "approved_by_role": "Approver Role",
    "checkout_time": "Checked Out",
    "days_out": "Days Out",
    "disposition": "Status / Result",
    "closed_time": "Closed",
    "acquired_time": "Acquired / Purchased",
    "closed_by_name": "Closed By",
    "closed_by_role": "Closer Role",
    "condition_notes": "Notes",
    "loan_due_date": "Loan Due Date",
    "loan_purpose": "Loan Purpose",
    "quantity_change": "Qty Change",
    "total_before": "Previous Total",
    "total_after": "New Total",
    "available_before": "Previously Available",
    "available_after": "Available Now",
    "details": "Explanation",
    "source": "Recorded By",
    "activity_class": "Activity Class",
    "weekly_event": "Weekly Event",
    "cadet_id": "Cadet ID",
    "size_entry_id": "Fitting Entry #",
    "full_name": "Cadet",
    "email": "Cadet Email",
    "size_label": "Measurement / Item",
    "size_value": "Recorded Size",
    "catalog_item_no": "Catalog Item #",
    "source_category": "Source Category",
    "report_category": "Report Category",
    "created_at": "Created",
    "updated_at": "Last Updated",
    "total_quantity": "Total Quantity",
    "available_quantity": "Available Quantity",
    "status": "Current Status",
    "id_status": "Item Number Status",
    "validation_note": "Validation Note",
}
REPORT_TIMESTAMP_FIELDS = {
    "event_time",
    "checkout_time",
    "closed_time",
    "acquired_time",
    "created_at",
    "updated_at",
}
RANKS = (
    ("GMC100", "GMC 100 (C/4C)"),
    ("GMC200", "GMC 200 (C/3C)"),
    ("C2LT", "C/2d Lt"),
    ("C1LT", "C/1st Lt"),
    ("CCAPT", "C/Capt"),
    ("CMAJ", "C/Maj"),
    ("CLTCOL", "C/Lt Col"),
    ("CCOL", "C/Col"),
)
GMC_RANKS = RANKS[:2]
LOCAL_RANK_FAMILIES = (
    ("SBM", "Men's Cloth Blues Rank", "Men's Cloth Blues Ranks", "M", GMC_RANKS),
    ("SBW", "Women's Cloth Blues Rank", "Women's Cloth Blues Ranks", "F", GMC_RANKS),
    ("HB", "Hard Blues Rank", "Hard Blues Ranks", "", RANKS[:-2]),
    ("OCP", "OCP Rank Patch", "OCP Rank Patches", "", RANKS),
)
OFFICIAL_CLOTH_RANK_ITEM_NOS = {
    "LOCAL-RANK-SBW-CCOL": "867",
    "LOCAL-RANK-SBW-CLTCOL": "868",
    "LOCAL-RANK-SBW-CMAJ": "869",
    "LOCAL-RANK-SBW-CCAPT": "870",
    "LOCAL-RANK-SBW-C1LT": "871",
    "LOCAL-RANK-SBW-C2LT": "872",
    "LOCAL-RANK-SBM-CCOL": "873",
    "LOCAL-RANK-SBM-CLTCOL": "874",
    "LOCAL-RANK-SBM-CMAJ": "875",
    "LOCAL-RANK-SBM-CCAPT": "876",
    "LOCAL-RANK-SBM-C1LT": "877",
    "LOCAL-RANK-SBM-C2LT": "878",
}
OFFICIAL_METAL_RANK_ITEM_NOS = {
    "LOCAL-RANK-HB-CCOL": "2348",
    "LOCAL-RANK-HB-CLTCOL": "2349",
}
AUTOMATIC_RANK_MAPPING_NOTE_PATTERN = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] "
    r"Mapped from local (?:Soft Blues|Hard Blues) rank LOCAL-RANK-[A-Z0-9-]+ "
    r"to official WINGS item \d+\.$"
)
PACKAGING_VARIANT_PATTERN = re.compile(r"\s+(?:packed|unpacked)\s*$", flags=re.IGNORECASE)
LEGACY_PACKAGING_IMPORT_NOTE = (
    "Imported from Auburn Uniform Inventory Test.xlsm, Initial Roster; "
    "the original roster code is preserved in Variant."
)
IMPORTED_BLUE_TROUSER_REFERENCES = {
    "LOCAL-AUTO-BLUES-PANTS-39L-7AEA83E8": ("39 LONG", "8405013778092"),
    "LOCAL-AUTO-BLUES-PANTS-40R-612ED7A1": ("40 REGULAR", "8405013778104"),
    "LOCAL-AUTO-BLUES-PANTS-40L-4B39ECB0": ("40 LONG", "8405013778094"),
}
EASTER_EGG_EXPORT_PROFILES = [
    {
        "ace_name": "Heart",
        "cadet_id": 1,
        "trait": "Loyal",
        "outfit_title": "Regalia of the Steamheart Sovereign",
        "asset_path": Path(r"D:\Aseprite\palettes\heratcharacter.gif"),
        "asset_label": "heart_character.png",
    },
    {
        "ace_name": "Spade",
        "cadet_id": 2,
        "trait": "Smart",
        "outfit_title": "Industrial Labor Attire of the Subterranean Worker",
        "asset_path": Path(r"D:\Aseprite\palettes\spaddes2.png"),
        "asset_label": "spade_character.png",
    },
    {
        "ace_name": "Clubs",
        "cadet_id": 3,
        "trait": "Funny",
        "outfit_title": "Casual Civilian Streetwear of the Urban Commoner",
        "asset_path": Path(r"D:\Aseprite\palettes\club2.png"),
        "asset_label": "clubs_character.png",
    },
    {
        "ace_name": "Diamo",
        "cadet_id": 4,
        "trait": "Sweet",
        "outfit_title": "Administrative Attire of the Metropolitan Governor",
        "asset_path": Path(r"D:\Aseprite\palettes\Diamo.asse.png"),
        "asset_label": "diamo_character.png",
    },
    {
        "ace_name": "Devin",
        "cadet_id": 5,
        "trait": "Keeper of the Hidden Crew",
        "outfit_title": "ACE Inventory Dev Outfit",
        "asset_path": None,
        "asset_label": "",
    },
]
EASTER_EGG_GROUP_ASSET = {
    "asset_path": Path(r"D:\Aseprite\palettes\Beholdadoodlelikeyou'veneverseencaring,smart,fun,andtough.png"),
    "asset_label": "ace_group.png",
}


class InventoryError(Exception):
    """Raised when a business rule prevents the requested operation."""


class _WingsHtmlTableParser(HTMLParser):
    """Small dependency-free reader for WINGS HTML files exported with an .xls suffix."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []
        elif tag.casefold() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).replace("\xa0", " ").split()))
            self._cell = None
        elif lowered == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def close(self) -> None:
        super().close()
        if self._row:
            self.rows.append(self._row)
            self._row = None


from .loans import LoanServiceMixin
from .acquisition_undo import AcquisitionUndoMixin
from .catalog_inventory import CatalogInventoryMixin
from .cic import CicServiceMixin
from .cic_sharepoint import SharePointCicMixin


class InventoryService(LoanServiceMixin, AcquisitionUndoMixin, CatalogInventoryMixin, CicServiceMixin, SharePointCicMixin):
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.database = InventoryDatabase(settings)
        self._seed_rank_catalog()
        self._ensure_inventory_item_numbers()
        self._reconcile_packaging_variants()
        self._backfill_current_day_inventory_changes()

    def replace_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.database.swap_settings(settings)
        self._ensure_inventory_item_numbers()
        self._reconcile_packaging_variants()
        self._backfill_current_day_inventory_changes()
        if getattr(self,'catalog_inventory_enabled',False):self.ensure_catalog_inventory()

    def _backfill_current_day_inventory_changes(self) -> int:
        """Recover today's new-item totals once when upgrading from pre-audit builds."""
        recovered_count = 0
        today_prefix = f"{date.today().isoformat()}%"
        with self.database.connect() as connection:
            applied = connection.execute(
                "SELECT 1 FROM ace_feature_flags WHERE feature_key = ?",
                (INVENTORY_CHANGE_AUDIT_VERSION,),
            ).fetchone()
            if applied is not None:
                return 0
            cursor = connection.execute(
                """
                INSERT INTO inventory_changes(
                    event_time, action, barcode_id, wings_item_no, item_name,
                    category, variant, item_type, quantity_change, total_before,
                    total_after, available_before, available_after, details, source
                )
                SELECT
                    created_at,
                    'New Item Added (Recovered)',
                    barcode_id,
                    COALESCE(wings_item_no, ''),
                    item_name,
                    category,
                    variant,
                    item_type,
                    total_quantity,
                    0,
                    total_quantity,
                    0,
                    available_quantity,
                    'Recovered from the item creation timestamp when change tracking was enabled.',
                    'Upgrade recovery'
                FROM items
                WHERE created_at LIKE ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM inventory_changes changes
                      WHERE changes.barcode_id = items.barcode_id
                        AND changes.action IN ('New Item Added', 'New Item Added (Recovered)')
                  )
                """,
                (today_prefix,),
            )
            recovered_count = max(0, int(cursor.rowcount))
            connection.execute(
                "INSERT INTO ace_feature_flags(feature_key, applied_at) VALUES (?, ?)",
                (INVENTORY_CHANGE_AUDIT_VERSION, utc_now()),
            )
            connection.commit()
        if recovered_count:
            self.database.note_write()
        return recovered_count

    def _ensure_inventory_item_numbers(self) -> int:
        """Give every inventory row an official or explicit local catalog number."""
        updated_count = 0
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT barcode_id, item_name, category, variant, item_type
                FROM items
                WHERE wings_item_no IS NULL OR trim(wings_item_no) = ''
                ORDER BY barcode_id
                """
            ).fetchall()
            for row in rows:
                item_no = self._ensure_local_inventory_catalog_entry(connection, row)
                connection.execute(
                    "UPDATE items SET wings_item_no = ?, updated_at = ? WHERE barcode_id = ?",
                    (item_no, utc_now(), row["barcode_id"]),
                )
                updated_count += 1
            connection.commit()
        if updated_count:
            self.database.note_write()
        return updated_count

    @staticmethod
    def _base_inventory_variant(variant: str) -> str:
        return PACKAGING_VARIANT_PATTERN.sub("", str(variant)).strip()

    @staticmethod
    def _remove_legacy_packaging_note(notes: str | None) -> str:
        remaining = str(notes or "").replace(LEGACY_PACKAGING_IMPORT_NOTE, "")
        return "\n".join(line.strip() for line in remaining.splitlines() if line.strip())

    @classmethod
    def _merge_packaging_notes(cls, rows: list[sqlite3.Row]) -> str:
        merged: list[str] = []
        for row in rows:
            cleaned = cls._remove_legacy_packaging_note(row["notes"])
            for line in cleaned.splitlines():
                if line and line not in merged:
                    merged.append(line)
        return "\n".join(merged)

    def _reconcile_packaging_variants(self) -> dict[str, int]:
        """Collapse legacy packed/unpacked rows into one catalog item and keep old labels scannable."""
        merged_rows = 0
        normalized_items = 0
        relinked_transactions = 0
        reference_updates = 0
        with self.database.connect() as connection:
            for item_no, (size, stock_number) in IMPORTED_BLUE_TROUSER_REFERENCES.items():
                changed = connection.execute(
                    """
                    UPDATE wings_catalog
                    SET item_name = 'TROUSERS, MENS', size = ?, category = 'Pants/Skirt',
                        subcategory = 'Blues', sex = 'M', stock_number = ?, uom = 'PR',
                        source = 'USAF HGMAN stock-number reference; WINGS item number absent from attached export',
                        is_wings = 0
                    WHERE item_no = ? AND is_wings = 0
                      AND (
                          item_name <> 'TROUSERS, MENS' OR size <> ? OR category <> 'Pants/Skirt'
                          OR subcategory <> 'Blues' OR sex <> 'M' OR stock_number <> ? OR uom <> 'PR'
                          OR source <> 'USAF HGMAN stock-number reference; WINGS item number absent from attached export'
                      )
                    """,
                    (size, stock_number, item_no, size, stock_number),
                ).rowcount
                reference_updates += max(changed, 0)
            candidates = [
                row
                for row in connection.execute(
                    """
                    SELECT *
                    FROM items
                    WHERE status NOT IN ('Retired', 'Lost')
                    ORDER BY barcode_id
                    """
                ).fetchall()
                if PACKAGING_VARIANT_PATTERN.search(str(row["variant"] or ""))
            ]
            groups: dict[str, list[sqlite3.Row]] = {}
            for row in candidates:
                item_no = str(row["wings_item_no"] or "").strip()
                if item_no:
                    group_key = f"item-no:{item_no.casefold()}"
                else:
                    group_key = "identity:" + "|".join(
                        str(value or "").strip().casefold()
                        for value in (
                            row["item_name"],
                            row["category"],
                            self._base_inventory_variant(row["variant"]),
                            row["item_type"],
                        )
                    )
                groups.setdefault(group_key, []).append(row)

            for rows in groups.values():
                keeper = min(rows, key=lambda row: str(row["barcode_id"]))
                keeper_barcode = str(keeper["barcode_id"])
                item_no = str(keeper["wings_item_no"] or "").strip()
                catalog = connection.execute(
                    "SELECT * FROM wings_catalog WHERE item_no = ?",
                    (item_no,),
                ).fetchone()
                if catalog is not None:
                    item_name = str(catalog["item_name"] or keeper["item_name"])
                    category = str(catalog["category"] or keeper["category"])
                    variant = str(catalog["size"] or self._base_inventory_variant(keeper["variant"]))
                    item_type = str(catalog["subcategory"] or catalog["item_name"] or keeper["item_type"])
                else:
                    item_name = str(keeper["item_name"])
                    category = str(keeper["category"])
                    variant = self._base_inventory_variant(keeper["variant"])
                    item_type = str(keeper["item_type"])

                total_quantity = sum(int(row["total_quantity"]) for row in rows)
                created_at = min(str(row["created_at"]) for row in rows)
                merged_notes = self._merge_packaging_notes(rows)

                for row in rows:
                    old_barcode = str(row["barcode_id"])
                    if old_barcode == keeper_barcode:
                        continue
                    changed = connection.execute(
                        "UPDATE transactions SET barcode_id = ? WHERE barcode_id = ?",
                        (keeper_barcode, old_barcode),
                    ).rowcount
                    relinked_transactions += max(changed, 0)
                    connection.execute("DELETE FROM items WHERE barcode_id = ?", (old_barcode,))
                    connection.execute(
                        """
                        INSERT INTO barcode_aliases(alias_barcode_id, canonical_barcode_id, created_at, reason)
                        VALUES (?, ?, ?, 'Packed/unpacked inventory reconciliation')
                        ON CONFLICT(alias_barcode_id) DO UPDATE SET
                            canonical_barcode_id = excluded.canonical_barcode_id,
                            created_at = excluded.created_at,
                            reason = excluded.reason
                        """,
                        (old_barcode, keeper_barcode, utc_now()),
                    )
                    merged_rows += 1

                connection.execute(
                    """
                    UPDATE items
                    SET item_name = ?, category = ?, variant = ?, item_type = ?, notes = ?,
                        total_quantity = ?, created_at = ?, updated_at = ?
                    WHERE barcode_id = ?
                    """,
                    (
                        item_name,
                        category,
                        variant,
                        item_type,
                        merged_notes,
                        total_quantity,
                        created_at,
                        utc_now(),
                        keeper_barcode,
                    ),
                )
                self._sync_item_state(connection, keeper_barcode)
                self._record_catalog_values(connection, category, variant, item_type, item_name)
                normalized_items += 1

            if normalized_items:
                connection.execute(
                    """
                    DELETE FROM catalog_values
                    WHERE kind = 'variant'
                      AND (lower(value) LIKE '% packed' OR lower(value) LIKE '% unpacked')
                      AND NOT EXISTS (
                          SELECT 1 FROM items WHERE lower(items.variant) = lower(catalog_values.value)
                      )
                    """
                )
            if normalized_items or reference_updates:
                connection.commit()

        if normalized_items or reference_updates:
            self.database.note_write()
        return {
            "normalized_items": normalized_items,
            "merged_rows": merged_rows,
            "relinked_transactions": relinked_transactions,
            "reference_updates": reference_updates,
        }

    def _ensure_local_inventory_catalog_entry(
        self,
        connection: sqlite3.Connection,
        item: sqlite3.Row | dict[str, Any],
    ) -> str:
        item_name = " ".join(str(item["item_name"] or "Local Inventory Item").split())
        category = " ".join(str(item["category"] or "Other").split())
        variant = " ".join(str(item["variant"] or "Standard").split())
        item_type = " ".join(str(item["item_type"] or item_name).split())
        base_variant = self._base_inventory_variant(variant) or variant
        identity = "|".join(
            value.casefold() for value in (item_name, category, base_variant, item_type)
        )
        readable = re.sub(r"[^A-Z0-9]+", "-", f"{item_name}-{base_variant}".upper()).strip("-")
        readable = readable[:38].rstrip("-") or "ITEM"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8].upper()
        item_no = f"LOCAL-AUTO-{readable}-{digest}"
        paired_types = ("TROUSER", "PANT", "SHORT", "SHOE", "BOOT")
        uom = "PR" if any(token in item_type.upper() for token in paired_types) else "EA"
        connection.execute(
            """
            INSERT INTO wings_catalog(
                item_no, item_name, size, category, subcategory, sex,
                stock_number, uom, writeoffs, source, is_wings
            ) VALUES (?, ?, ?, ?, ?, '', '', ?, '', ?, 0)
            ON CONFLICT(item_no) DO UPDATE SET
                item_name = excluded.item_name,
                size = excluded.size,
                category = excluded.category,
                subcategory = excluded.subcategory,
                uom = excluded.uom,
                source = excluded.source,
                is_wings = 0
            """,
            (
                item_no,
                item_name,
                base_variant,
                category,
                item_type,
                uom,
                LOCAL_INVENTORY_MAPPING_SOURCE,
            ),
        )
        return item_no

    def clone_database(self, target_path: Path) -> Path:
        return self.database.clone_database(target_path)

    def create_manual_backup(self) -> Path:
        return self.database.create_backup(reason="manual")

    def backup_protection_status(self) -> dict[str, Any]:
        protected_dir = self.settings.protected_backup_dir
        return {
            "configured_path": str(protected_dir) if protected_dir is not None else "",
            "last_copy_path": (
                str(self.database.last_protected_backup_path)
                if self.database.last_protected_backup_path is not None
                else ""
            ),
            "last_error": self.database.last_protected_backup_error or "",
        }

    def ensure_app_icon(self, source_png: Path) -> Path:
        return ensure_icon_file(source_png, self.settings.database_path.parent / "app_icon.ico")

    def _seed_rank_catalog(self) -> None:
        connection = self.database.connect()
        try:
            already_applied = connection.execute(
                "SELECT 1 FROM ace_feature_flags WHERE feature_key = ?",
                (RANK_CATALOG_VERSION,),
            ).fetchone()
            if already_applied:
                return

            now = utc_now()
            legacy_soft_blues_item_nos = [
                f"LOCAL-RANK-SB-{rank_code}" for rank_code, _rank_name in RANKS
            ]
            for item_no in legacy_soft_blues_item_nos:
                is_linked = connection.execute(
                    "SELECT 1 FROM items WHERE wings_item_no = ? LIMIT 1",
                    (item_no,),
                ).fetchone()
                if is_linked:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO hidden_index_items(item_no, hidden_at)
                        VALUES (?, ?)
                        """,
                        (item_no, utc_now()),
                    )
                else:
                    connection.execute("DELETE FROM wings_catalog WHERE item_no = ?", (item_no,))

            # Remove only the automatic rank-mapping entries written by v1.4.1.
            # Original operational notes on those items remain untouched.
            items_with_mapping_notes = connection.execute(
                """
                SELECT barcode_id, notes
                FROM items
                WHERE notes LIKE '%Mapped from local % rank LOCAL-RANK-% to official WINGS item %'
                """
            ).fetchall()
            for item in items_with_mapping_notes:
                cleaned_notes = self._remove_automatic_rank_mapping_notes(item["notes"])
                if cleaned_notes != str(item["notes"] or ""):
                    connection.execute(
                        "UPDATE items SET notes = ?, updated_at = ? WHERE barcode_id = ?",
                        (cleaned_notes, now, item["barcode_id"]),
                    )

            # Officer cloth ranks use official WINGS items 867-878. The two
            # senior mini-metal ranks use official WINGS items 2348-2349.
            # Mapping changes descriptive fields only: barcodes, quantities,
            # notes, and checkout history remain untouched.
            official_rank_item_nos = {
                **OFFICIAL_CLOTH_RANK_ITEM_NOS,
                **OFFICIAL_METAL_RANK_ITEM_NOS,
            }
            for local_item_no, official_item_no in official_rank_item_nos.items():
                official = connection.execute(
                    """
                    SELECT item_no, item_name, size, category, subcategory
                    FROM wings_catalog
                    WHERE item_no = ? AND is_wings = 1
                    """,
                    (official_item_no,),
                ).fetchone()
                if official is None:
                    continue
                official_item_type = str(official["subcategory"] or official["item_name"])
                linked_items = connection.execute(
                    "SELECT barcode_id FROM items WHERE wings_item_no = ?",
                    (local_item_no,),
                ).fetchall()
                for item in linked_items:
                    connection.execute(
                        """
                        UPDATE items
                        SET wings_item_no = ?, item_name = ?, category = ?, variant = ?,
                            item_type = ?, updated_at = ?
                        WHERE barcode_id = ?
                        """,
                        (
                            official["item_no"],
                            official["item_name"],
                            official["category"],
                            official["size"],
                            official_item_type,
                            now,
                            item["barcode_id"],
                        ),
                    )
                connection.execute("DELETE FROM hidden_index_items WHERE item_no = ?", (local_item_no,))
                connection.execute("DELETE FROM wings_catalog WHERE item_no = ?", (local_item_no,))

            # WINGS has no official cloth records for the GMC 100 and GMC 200
            # rows. Keep those four entries local, but use Cloth terminology.
            for family_code, item_name, subcategory, _sex, ranks in LOCAL_RANK_FAMILIES[:2]:
                for rank_code, _rank_name in ranks:
                    connection.execute(
                        """
                        UPDATE items
                        SET item_name = ?, item_type = ?, updated_at = ?
                        WHERE wings_item_no = ?
                        """,
                        (
                            item_name,
                            subcategory,
                            now,
                            f"LOCAL-RANK-{family_code}-{rank_code}",
                        ),
                    )

            for kind, value, item_column in (
                ("item_name", "Soft Blues Rank", "item_name"),
                ("item_name", "Men's Soft Blues Rank", "item_name"),
                ("item_name", "Women's Soft Blues Rank", "item_name"),
                ("item_type", "Soft Blues Ranks", "item_type"),
                ("item_type", "Men's Soft Blues Ranks", "item_type"),
                ("item_type", "Women's Soft Blues Ranks", "item_type"),
            ):
                is_in_use = connection.execute(
                    f"SELECT 1 FROM items WHERE {item_column} = ? COLLATE NOCASE LIMIT 1",
                    (value,),
                ).fetchone()
                if not is_in_use:
                    connection.execute(
                        "DELETE FROM catalog_values WHERE kind = ? AND value = ? COLLATE NOCASE",
                        (kind, value),
                    )

            for family_code, item_name, subcategory, sex, ranks in LOCAL_RANK_FAMILIES:
                for rank_code, rank_name in ranks:
                    connection.execute(
                        """
                        INSERT INTO wings_catalog(
                            item_no, item_name, size, category, subcategory, sex,
                            stock_number, uom, writeoffs, source, is_wings
                        ) VALUES (?, ?, ?, 'Insignia', ?, ?, '', 'EA', '',
                                  'A.C.E. Rank Catalog', 0)
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
                        (
                            f"LOCAL-RANK-{family_code}-{rank_code}",
                            item_name,
                            rank_name,
                            subcategory,
                            sex,
                        ),
                    )
                    for kind, value in (
                        ("category", "Insignia"),
                        ("variant", rank_name),
                        ("item_type", subcategory),
                        ("item_name", item_name),
                    ):
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO catalog_values(kind, value, sort_order)
                            VALUES (?, ?, 850)
                            """,
                            (kind, value),
                        )

            connection.execute(
                "INSERT INTO ace_feature_flags(feature_key, applied_at) VALUES (?, ?)",
                (RANK_CATALOG_VERSION, now),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _remove_automatic_rank_mapping_notes(notes: str | None) -> str:
        lines = str(notes or "").splitlines()
        retained = [
            line
            for line in lines
            if not AUTOMATIC_RANK_MAPPING_NOTE_PATTERN.fullmatch(line.strip())
        ]
        return "\n".join(retained).strip()

    def authenticate_admin_code(self, code: str) -> dict[str, Any]:
        normalized_code = code.strip()
        if not normalized_code:
            raise InventoryError("Admin code is required.")

        if normalized_code.casefold() == MASTER_ADMIN_CODE.casefold():
            return {
                "admin_id": None,
                "display_name": "CADRE",
                "role": MASTER_ADMIN_ROLE,
                "is_master": True,
                "label": MASTER_ADMIN_ROLE,
            }

        code_hash = self._hash_admin_code(normalized_code)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT admin_id, display_name, role
                FROM admin_codes
                WHERE code_hash = ? AND is_active = 1
                """,
                (code_hash,),
            ).fetchone()
        if row is None:
            raise InventoryError("Admin code not recognized.")

        payload = dict(row)
        payload["is_master"] = False
        payload["label"] = f"{payload['role']} {payload['display_name']}".strip()
        return payload

    def list_admin_codes(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = [
            {
                "admin_id": "MASTER",
                "display_name": "Cadre Administrator",
                "role": MASTER_ADMIN_ROLE,
                "is_active": 1,
                "created_at": "",
                "updated_at": "",
                "label": f"{MASTER_ADMIN_ROLE} ({MASTER_ADMIN_CODE})",
            }
        ]
        with self.database.connect() as connection:
            db_rows = connection.execute(
                """
                SELECT admin_id, display_name, role, is_active, created_at, updated_at
                FROM admin_codes
                ORDER BY role, display_name
                """
            ).fetchall()
        rows.extend(dict(row) for row in db_rows if not self._is_easter_egg_admin_id(row["admin_id"]))
        return rows

    def get_admin_code_value(self, *, admin_id: int | str) -> str:
        if str(admin_id) == "MASTER":
            return MASTER_ADMIN_CODE

        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT code_value
                FROM admin_codes
                WHERE admin_id = ?
                """,
                (int(admin_id),),
            ).fetchone()
        if row is None:
            raise InventoryError("Admin code not found.")

        code_value = str(row["code_value"] or "").strip()
        if not code_value:
            raise InventoryError(
                "This admin code was created before code viewing was enabled. Save or reset that admin code once to make it viewable."
            )
        return code_value

    def save_admin_code(self, *, display_name: str, code: str, role: str = DEFAULT_ADMIN_ROLE) -> dict[str, Any]:
        name = self._smart_title(display_name)
        if not name:
            raise InventoryError("Admin name is required.")
        normalized_code = code.strip()
        if not normalized_code:
            raise InventoryError("Admin code is required.")
        if normalized_code.casefold() == MASTER_ADMIN_CODE.casefold():
            raise InventoryError("Det005 is reserved as the cadre administrator code.")

        code_hash = self._hash_admin_code(normalized_code)
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT admin_id FROM admin_codes WHERE code_hash = ?",
                (code_hash,),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE admin_codes
                    SET display_name = ?, role = ?, code_value = ?, is_active = 1, updated_at = ?
                    WHERE admin_id = ?
                    """,
                    (name, role, normalized_code, utc_now(), existing["admin_id"]),
                )
                admin_id = existing["admin_id"]
            else:
                admin_id = self._lowest_available_integer_id(
                    connection,
                    table_name="admin_codes",
                    id_column="admin_id",
                    reserved_ids=RESERVED_ADMIN_IDS,
                )
                cursor = connection.execute(
                    """
                    INSERT INTO admin_codes(admin_id, display_name, role, code_hash, code_value, created_at, updated_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (admin_id, name, role, code_hash, normalized_code, utc_now(), utc_now()),
                )
            row = connection.execute(
                """
                SELECT admin_id, display_name, role, is_active, created_at, updated_at
                FROM admin_codes
                WHERE admin_id = ?
                """,
                (admin_id,),
            ).fetchone()
            connection.commit()

        self.database.note_write()
        return dict(row)

    def deactivate_admin_code(self, *, admin_id: int) -> None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT admin_id FROM admin_codes WHERE admin_id = ?", (admin_id,)).fetchone()
            if row is None:
                raise InventoryError("Admin code not found.")
            connection.execute(
                "UPDATE admin_codes SET is_active = 0, updated_at = ? WHERE admin_id = ?",
                (utc_now(), admin_id),
            )
            connection.commit()
        self.database.note_write()

    def delete_admin_code(self, *, admin_id: int) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT admin_id FROM admin_codes WHERE admin_id = ?",
                (admin_id,),
            ).fetchone()
            if row is None:
                raise InventoryError("Admin code not found.")

            connection.execute(
                """
                UPDATE transactions
                SET approved_by_admin_id = NULL
                WHERE approved_by_admin_id = ?
                """,
                (admin_id,),
            )
            connection.execute(
                """
                UPDATE transactions
                SET return_approved_by_admin_id = NULL
                WHERE return_approved_by_admin_id = ?
                """,
                (admin_id,),
            )
            connection.execute(
                "DELETE FROM admin_codes WHERE admin_id = ?",
                (admin_id,),
            )
            connection.commit()
        self.database.note_write()

    def create_transfer_installer(self, *, icon_source: Path | None = None) -> Path:
        icon_path: Path | None = None
        if icon_source is not None:
            resolved_icon = Path(icon_source).expanduser().resolve()
            if not resolved_icon.exists():
                raise InventoryError(f"Icon source not found: {resolved_icon}")
            if resolved_icon.suffix.lower() == ".ico":
                icon_path = resolved_icon
            else:
                icon_path = ensure_icon_file(resolved_icon, self.settings.database_path.parent / "app_icon.ico")
        else:
            existing_icon = self.settings.database_path.parent / "app_icon.ico"
            if existing_icon.exists():
                icon_path = existing_icon

        installer_path = create_transfer_installer(
            project_dir=BASE_DIR,
            database_path=self.settings.database_path,
            icon_path=icon_path,
            app_title=self.settings.org_name,
            backup_interval_ops=self.settings.backup_interval_ops,
            overdue_days=self.settings.overdue_days,
        )
        return installer_path

    def list_catalog_values(self, kind: str) -> list[str]:
        item_column_map = {
            "category": "category",
            "variant": "variant",
            "item_type": "item_type",
            "item_name": "item_name",
        }
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT value FROM catalog_values WHERE kind = ? ORDER BY sort_order, value",
                (kind,),
            ).fetchall()
            visible_item_values: set[str] = set()
            item_column = item_column_map.get(kind)
            if item_column:
                visible_rows = connection.execute(
                    f"""
                    SELECT DISTINCT {item_column} AS value
                    FROM items
                    WHERE {self._not_in_clause('barcode_id', EASTER_EGG_BARCODE_IDS)}
                    """,
                    EASTER_EGG_BARCODE_IDS,
                ).fetchall()
                visible_item_values = {
                    str(row["value"]).strip().upper()
                    for row in visible_rows
                    if str(row["value"] or "").strip()
                }
        hidden_values = EASTER_EGG_CATALOG_VALUES.get(kind, set())
        return [
            row["value"]
            for row in rows
            if (
                str(row["value"]).strip().upper() not in hidden_values
                or str(row["value"]).strip().upper() in visible_item_values
            )
        ]

    def list_catalog_field_values(self, field: str, *, category: str = "") -> list[str]:
        allowed_fields = {
            "category": ("category", "category"),
            "subcategory": ("subcategory", "item_type"),
            "size": ("size", "variant"),
        }
        field_config = allowed_fields.get(field.strip().lower())
        if field_config is None:
            raise InventoryError("Unsupported catalog autofill field.")
        column, catalog_kind = field_config

        conditions = [f"trim({column}) <> ''"]
        params: list[str] = []
        if column == "subcategory" and category.strip():
            conditions.append("category = ? COLLATE NOCASE")
            params.append(category.strip())
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT value
                FROM (
                    SELECT {column} AS value
                    FROM wings_catalog
                    WHERE {' AND '.join(conditions)}
                    UNION
                    SELECT value
                    FROM catalog_values
                    WHERE kind = ? AND trim(value) <> ''
                )
                ORDER BY value COLLATE NOCASE
                """,
                [*params, catalog_kind],
            ).fetchall()
        return [str(row["value"]).strip() for row in rows]

    def list_custom_index_items(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT index_item_id, equipment_name, uniform_system, configuration,
                       size_system, search_aliases, created_at, updated_at
                FROM custom_index_items
                ORDER BY uniform_system, equipment_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_wings_catalog(
        self,
        *,
        search: str = "",
        category: str = "All",
        sort_by: str = "Item Number",
    ) -> list[dict[str, Any]]:
        conditions: list[str] = [
            "NOT EXISTS (SELECT 1 FROM hidden_index_items hidden WHERE hidden.item_no = wings_catalog.item_no)",
            "item_no NOT LIKE 'LOCAL-RANK-SB-%'",
        ]
        params: list[Any] = []
        words = [word for word in search.strip().casefold().split() if word]
        for word in words:
            searchable_word = str(int(word)) if word.isdigit() else word
            token = f"%{searchable_word}%"
            conditions.append(
                """
                (
                    lower(item_no) LIKE ? OR lower(item_name) LIKE ? OR lower(size) LIKE ?
                    OR lower(category) LIKE ? OR lower(subcategory) LIKE ? OR lower(sex) LIKE ?
                    OR lower(stock_number) LIKE ? OR lower(uom) LIKE ?
                )
                """
            )
            params.extend([token] * 8)
        if category and category != "All":
            conditions.append("category = ?")
            params.append(category)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_clause = (
            "is_wings DESC, CASE WHEN is_wings = 1 THEN CAST(item_no AS INTEGER) END, item_no"
            if sort_by == "Item Number"
            else "category, subcategory, item_name, size, item_no"
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT item_no, item_name, size, category, subcategory, sex,
                       stock_number, uom, writeoffs, source, is_wings
                FROM wings_catalog
                {where_clause}
                ORDER BY {order_clause}
                """,
                params,
            ).fetchall()
        catalog_rows = [dict(row) for row in rows]
        for row in catalog_rows:
            row["item_no_key"] = row["item_no"]
            row["item_no"] = self._format_wings_item_no(row["item_no"]) if row["is_wings"] else row["item_no"]
        return catalog_rows

    def get_wings_catalog_item(self, item_no: str) -> dict[str, Any]:
        cleaned_item_no = str(item_no).strip()
        if cleaned_item_no.isdigit():
            cleaned_item_no = str(int(cleaned_item_no))
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM wings_catalog WHERE item_no = ?",
                (cleaned_item_no,),
            ).fetchone()
        if row is None:
            raise InventoryError("Select an item from the WINGS catalog first.")
        return dict(row)

    def add_wings_catalog_item(
        self,
        *,
        item_no: str,
        item_name: str,
        size: str,
        category: str,
        subcategory: str,
        sex: str,
        stock_number: str,
        uom: str,
        source: str,
    ) -> str:
        raw_item_no = str(item_no).strip()
        if not raw_item_no.isdigit() or not 1 <= len(raw_item_no) <= 10:
            raise InventoryError("WINGS item number must contain 1 to 10 digits.")
        normalized_item_no = str(int(raw_item_no))
        if normalized_item_no == "0":
            raise InventoryError("WINGS item number must be greater than zero.")

        cleaned_name = " ".join(str(item_name).split())
        cleaned_category = " ".join(str(category).split())
        cleaned_subcategory = " ".join(str(subcategory).split())
        cleaned_uom = str(uom).strip().upper()
        cleaned_source = " ".join(str(source).split())
        if not cleaned_name:
            raise InventoryError("Item name is required.")
        if not cleaned_category:
            raise InventoryError("Category is required.")
        if not cleaned_subcategory:
            raise InventoryError("Subcategory is required.")
        if not cleaned_uom:
            raise InventoryError("UoM is required.")
        if not cleaned_source:
            raise InventoryError("Source is required.")

        cleaned_sex = str(sex).strip().upper()
        if cleaned_sex not in {"", "M", "F", "U"}:
            raise InventoryError("Sex must be blank, M, F, or U.")
        cleaned_stock_number = "".join(str(stock_number).split())
        if cleaned_stock_number and not cleaned_stock_number.isdigit():
            raise InventoryError("Stock number must contain digits only.")

        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT item_name FROM wings_catalog WHERE item_no = ?",
                (normalized_item_no,),
            ).fetchone()
            if existing is not None:
                raise InventoryError(
                    f"WINGS item {self._format_wings_item_no(normalized_item_no)} already exists as "
                    f"{existing['item_name']}."
                )
            connection.execute(
                """
                INSERT INTO wings_catalog(
                    item_no, item_name, size, category, subcategory, sex,
                    stock_number, uom, writeoffs, source, is_wings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Go to Writeoffs', ?, 1)
                """,
                (
                    normalized_item_no,
                    cleaned_name,
                    " ".join(str(size).split()),
                    cleaned_category,
                    cleaned_subcategory,
                    cleaned_sex,
                    cleaned_stock_number,
                    cleaned_uom,
                    cleaned_source,
                ),
            )
            connection.execute(
                "DELETE FROM hidden_index_items WHERE item_no = ?",
                (normalized_item_no,),
            )
            connection.commit()

        self.database.note_write()
        return self._format_wings_item_no(normalized_item_no)

    def add_custom_catalog_item(
        self,
        *,
        item_name: str,
        size: str,
        category: str,
        subcategory: str,
        sex: str,
        stock_number: str,
        uom: str,
        source: str,
    ) -> str:
        """Add a fully described local item without pretending it has a WINGS item number."""
        cleaned_name = " ".join(str(item_name).split())
        cleaned_category = " ".join(str(category).split())
        cleaned_subcategory = " ".join(str(subcategory).split())
        cleaned_uom = str(uom).strip().upper()
        cleaned_source = " ".join(str(source).split()) or "Local Custom Item"
        if not cleaned_name:
            raise InventoryError("Item name is required.")
        if not cleaned_category:
            raise InventoryError("Category is required.")
        if not cleaned_subcategory:
            raise InventoryError("Subcategory is required.")
        if not cleaned_uom:
            raise InventoryError("UoM is required.")
        cleaned_sex = str(sex).strip().upper()
        if cleaned_sex not in {"", "M", "F", "U"}:
            raise InventoryError("Sex must be blank, M, F, or U.")

        with self.database.connect() as connection:
            local_numbers = connection.execute(
                "SELECT item_no FROM wings_catalog WHERE item_no LIKE 'LOCAL-%'"
            ).fetchall()
            next_number = max(
                (
                    int(str(row["item_no"]).split("-", 1)[1])
                    for row in local_numbers
                    if str(row["item_no"]).split("-", 1)[-1].isdigit()
                ),
                default=0,
            ) + 1
            item_no = f"LOCAL-{next_number:04d}"
            connection.execute(
                """
                INSERT INTO wings_catalog(
                    item_no, item_name, size, category, subcategory, sex,
                    stock_number, uom, writeoffs, source, is_wings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, 0)
                """,
                (
                    item_no,
                    cleaned_name,
                    " ".join(str(size).split()),
                    cleaned_category,
                    cleaned_subcategory,
                    cleaned_sex,
                    " ".join(str(stock_number).split()),
                    cleaned_uom,
                    cleaned_source,
                ),
            )
            connection.commit()
        self.database.note_write()
        return item_no

    @staticmethod
    def _normalize_import_header(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).casefold())

    @staticmethod
    def _read_wings_html_rows(path: Path) -> list[list[str]]:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        parser = _WingsHtmlTableParser()
        parser.feed(text)
        parser.close()
        return parser.rows

    @staticmethod
    def _read_wings_csv_rows(path: Path) -> list[list[str]]:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        return [[str(cell).strip() for cell in row] for row in csv.reader(text.splitlines(), dialect)]

    @staticmethod
    def _read_wings_xlsx_rows(path: Path) -> list[list[str]]:
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        office_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        package_rel = "{http://schemas.openxmlformats.org/package/2006/relationships}"
        with zipfile.ZipFile(path, "r") as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in shared_root.findall(f"{namespace}si"):
                    shared_strings.append("".join(node.text or "" for node in item.iter(f"{namespace}t")))

            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            first_sheet = workbook_root.find(f"{namespace}sheets/{namespace}sheet")
            if first_sheet is None:
                return []
            relationship_id = first_sheet.attrib.get(f"{office_rel}id", "")
            rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            target = ""
            for relationship in rel_root.findall(f"{package_rel}Relationship"):
                if relationship.attrib.get("Id") == relationship_id:
                    target = relationship.attrib.get("Target", "")
                    break
            if not target:
                return []
            sheet_path = target.lstrip("/")
            if not sheet_path.startswith("xl/"):
                sheet_path = f"xl/{sheet_path}"
            sheet_root = ET.fromstring(archive.read(sheet_path))
            rows: list[list[str]] = []
            for row_node in sheet_root.findall(f".//{namespace}sheetData/{namespace}row"):
                values: dict[int, str] = {}
                for cell in row_node.findall(f"{namespace}c"):
                    reference = cell.attrib.get("r", "A1")
                    letters = "".join(character for character in reference if character.isalpha())
                    column_index = 0
                    for character in letters.upper():
                        column_index = column_index * 26 + ord(character) - 64
                    cell_type = cell.attrib.get("t", "")
                    value_node = cell.find(f"{namespace}v")
                    value = value_node.text if value_node is not None and value_node.text is not None else ""
                    if cell_type == "s" and value.isdigit() and int(value) < len(shared_strings):
                        value = shared_strings[int(value)]
                    elif cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(f"{namespace}t"))
                    values[column_index] = value.strip()
                if values:
                    rows.append([values.get(index, "") for index in range(1, max(values) + 1)])
            return rows

    def preview_wings_inventory_import(self, path: Path) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            raise InventoryError("The selected WINGS report could not be found.")
        suffix = path.suffix.casefold()
        try:
            if suffix in {".xls", ".html", ".htm"}:
                rows = self._read_wings_html_rows(path)
            elif suffix in {".csv", ".tsv"}:
                rows = self._read_wings_csv_rows(path)
            elif suffix == ".xlsx":
                rows = self._read_wings_xlsx_rows(path)
            else:
                raise InventoryError("Choose a WINGS Excel (.xls or .xlsx) or CSV report.")
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
            raise InventoryError(f"The selected report could not be read: {exc}") from exc

        header_aliases = {
            "item_no": {"itemno", "itemnumber", "wingsitemno"},
            "qty_issued": {"qtyissued", "quantityissued", "issued"},
            "qty_available": {"qtyavailable", "quantityavailable", "available"},
            "total": {"totalininventory", "totalinventory", "totalquantity", "total"},
            "item_name": {"itemname", "name"},
            "size": {"size"},
            "category": {"category"},
            "subcategory": {"subcategory", "subcat"},
            "sex": {"sex", "gender"},
            "stock_number": {"stock", "stockno", "stocknumber", "nsn"},
            "uom": {"uom", "unitofmeasure"},
            "writeoffs": {"gotowriteoffs", "writeoffs"},
            "source": {"source"},
        }
        header_index = -1
        columns: dict[str, int] = {}
        for index, row in enumerate(rows[:30]):
            normalized = [self._normalize_import_header(cell) for cell in row]
            candidate: dict[str, int] = {}
            for field, aliases in header_aliases.items():
                for column_index, heading in enumerate(normalized):
                    if heading in aliases:
                        candidate[field] = column_index
                        break
            if {"item_no", "item_name", "total"}.issubset(candidate):
                header_index = index
                columns = candidate
                break
        if header_index < 0:
            raise InventoryError(
                "This file does not look like a WINGS inventory report. Item No, Item Name, and Total in Inventory are required."
            )

        def cell(row: list[str], field: str) -> str:
            column_index = columns.get(field)
            return str(row[column_index]).strip() if column_index is not None and column_index < len(row) else ""

        def quantity(value: str, field_label: str, row_number: int) -> int:
            cleaned = str(value).replace(",", "").strip()
            if not cleaned:
                return 0
            try:
                numeric = float(cleaned)
            except ValueError as exc:
                raise InventoryError(f"Row {row_number} has an invalid {field_label}: {value}") from exc
            if numeric < 0 or not numeric.is_integer():
                raise InventoryError(f"Row {row_number} has an invalid {field_label}: {value}")
            return int(numeric)

        parsed_rows: list[dict[str, Any]] = []
        skipped: list[str] = []
        seen_item_numbers: set[str] = set()
        default_source = f"WINGS Import - {path.stem}"
        for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            raw_item_no = cell(row, "item_no")
            if not raw_item_no and not any(str(value).strip() for value in row):
                continue
            if not raw_item_no.isdigit() or int(raw_item_no) <= 0:
                skipped.append(f"Row {row_number}: unsupported item number {raw_item_no or '(blank)'}")
                continue
            item_no = str(int(raw_item_no))
            if item_no in seen_item_numbers:
                raise InventoryError(f"WINGS item {raw_item_no} appears more than once in the report.")
            seen_item_numbers.add(item_no)
            item_name = " ".join(cell(row, "item_name").split())
            if not item_name:
                skipped.append(f"Row {row_number}: item {raw_item_no} has no item name")
                continue
            total = quantity(cell(row, "total"), "total quantity", row_number)
            issued = quantity(cell(row, "qty_issued"), "issued quantity", row_number)
            available_text = cell(row, "qty_available")
            available = quantity(available_text, "available quantity", row_number) if available_text else total - issued
            if available < 0 or available > total or issued > total:
                raise InventoryError(
                    f"Row {row_number} has inconsistent quantities: issued {issued}, available {available}, total {total}."
                )
            if issued + available != total:
                raise InventoryError(
                    f"Row {row_number} does not balance: issued {issued} + available {available} does not equal total {total}."
                )
            parsed_rows.append(
                {
                    "item_no": item_no,
                    "item_name": item_name,
                    "size": " ".join(cell(row, "size").split()),
                    "category": " ".join(cell(row, "category").split()) or "Uncategorized",
                    "subcategory": " ".join(cell(row, "subcategory").split()) or "Other",
                    "sex": cell(row, "sex").strip().upper(),
                    "stock_number": "".join(cell(row, "stock_number").split()),
                    "uom": cell(row, "uom").strip().upper() or "EA",
                    "writeoffs": cell(row, "writeoffs") or "Go to Writeoffs",
                    "source": " ".join(cell(row, "source").split()) or default_source,
                    "issued": issued,
                    "available": available,
                    "total": total,
                }
            )
        if not parsed_rows:
            raise InventoryError("No valid WINGS inventory rows were found in the selected report.")
        return {
            "path": path,
            "rows": parsed_rows,
            "row_count": len(parsed_rows),
            "total_units": sum(row["total"] for row in parsed_rows),
            "issued_units": sum(row["issued"] for row in parsed_rows),
            "available_units": sum(row["available"] for row in parsed_rows),
            "skipped": skipped,
        }

    def replace_inventory_from_wings_report(self, path: Path) -> dict[str, Any]:
        preview = self.preview_wings_inventory_import(path)
        backup_path = self.database.create_backup(reason="before_wings_import")
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM transactions")
            connection.execute("DELETE FROM items")
            connection.execute("DELETE FROM barcode_sequences")
            for row in preview["rows"]:
                connection.execute(
                    """
                    INSERT INTO wings_catalog(
                        item_no, item_name, size, category, subcategory, sex,
                        stock_number, uom, writeoffs, source, is_wings
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
                        is_wings = 1
                    """,
                    (
                        row["item_no"], row["item_name"], row["size"], row["category"],
                        row["subcategory"], row["sex"], row["stock_number"], row["uom"],
                        row["writeoffs"], row["source"],
                    ),
                )
                connection.execute("DELETE FROM hidden_index_items WHERE item_no = ?", (row["item_no"],))
                if row["total"] <= 0:
                    continue
                barcode_id = compact_wings_barcode(row["item_no"])
                status = "Available" if row["available"] > 0 else "Checked Out"
                notes = (
                    f"Imported from {Path(path).name}. WINGS baseline shows "
                    f"{row['issued']} issued and {row['available']} available."
                )
                connection.execute(
                    """
                    INSERT INTO items(
                        barcode_id, wings_item_no, item_name, category, variant, item_type,
                        status, notes, total_quantity, available_quantity, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        barcode_id, row["item_no"], row["item_name"], row["category"], row["size"],
                        row["subcategory"], status, notes, row["total"], row["available"], now, now,
                    ),
                )
                for _ in range(row["issued"]):
                    connection.execute(
                        """
                        INSERT INTO transactions(
                            barcode_id, cadet_id, cadet_name, cadet_email, checkout_time,
                            approved_by_name, approved_by_role, approved_at, condition_notes
                        ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            barcode_id,
                            "WINGS Import - Holder Not Listed",
                            "wings-import@ace.local",
                            now,
                            "WINGS Import",
                            "SYSTEM",
                            now,
                            "Imported issued quantity. The summary report did not identify the individual holder.",
                        ),
                    )
            connection.commit()
        self.database.note_write()
        result = {key: value for key, value in preview.items() if key != "rows"}
        result["backup_path"] = backup_path
        return result

    def remove_index_entries(
        self,
        *,
        item_nos: list[str],
        custom_index_ids: list[int],
    ) -> dict[str, int]:
        normalized_item_nos: list[str] = []
        for item_no in item_nos:
            cleaned = str(item_no).strip()
            if cleaned.isdigit():
                cleaned = str(int(cleaned))
            if cleaned and cleaned not in normalized_item_nos:
                normalized_item_nos.append(cleaned)
        normalized_custom_ids = sorted({int(index_id) for index_id in custom_index_ids})

        hidden_count = 0
        deleted_local_count = 0
        deleted_custom_count = 0
        with self.database.connect() as connection:
            for item_no in normalized_item_nos:
                local_row = connection.execute(
                    "SELECT is_wings FROM wings_catalog WHERE item_no = ?",
                    (item_no,),
                ).fetchone()
                if local_row is not None and int(local_row["is_wings"]) == 0:
                    cursor = connection.execute("DELETE FROM wings_catalog WHERE item_no = ?", (item_no,))
                    deleted_local_count += max(0, int(cursor.rowcount))
                    continue
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO hidden_index_items(item_no, hidden_at)
                    SELECT item_no, ?
                    FROM wings_catalog
                    WHERE item_no = ?
                    """,
                    (utc_now(), item_no),
                )
                hidden_count += max(0, int(cursor.rowcount))
            if normalized_custom_ids:
                placeholders = ", ".join("?" for _ in normalized_custom_ids)
                cursor = connection.execute(
                    f"DELETE FROM custom_index_items WHERE index_item_id IN ({placeholders})",
                    normalized_custom_ids,
                )
                deleted_custom_count = max(0, int(cursor.rowcount))
            connection.commit()

        if hidden_count or deleted_local_count or deleted_custom_count:
            self.database.note_write()
        return {
            "hidden": hidden_count,
            "deleted_local": deleted_local_count,
            "deleted_custom": deleted_custom_count,
        }

    def restore_hidden_index_items(self) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM hidden_index_items")
            restored_count = max(0, int(cursor.rowcount))
            connection.commit()
        if restored_count:
            self.database.note_write()
        return restored_count

    def count_hidden_index_items(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS hidden_count FROM hidden_index_items").fetchone()
        return int(row["hidden_count"])

    def count_wings_catalog_items(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS catalog_count FROM wings_catalog WHERE is_wings = 1"
            ).fetchone()
        return int(row["catalog_count"])

    @staticmethod
    def _format_wings_item_no(item_no: str) -> str:
        cleaned = str(item_no).strip()
        return cleaned.zfill(10) if cleaned.isdigit() else cleaned

    def save_custom_index_item(
        self,
        *,
        equipment_name: str,
        uniform_system: str,
        configuration: str,
        size_system: str,
        search_aliases: str = "",
        index_item_id: int | None = None,
    ) -> int:
        name = " ".join(equipment_name.split())
        if not name:
            raise InventoryError("Equipment name is required.")
        system = uniform_system.strip().upper()
        allowed_systems = {"BLUES", "OCP", "PTG", "CADET RANK", "ACCOUTREMENTS", "OUTERWEAR", "FOOTWEAR", "OTHER"}
        if system not in allowed_systems:
            raise InventoryError("Select a valid uniform or equipment system.")
        config_map = {"standard": "Standard", "men's": "Men's", "mens": "Men's", "women's": "Women's", "womens": "Women's", "unisex": "Unisex"}
        config = config_map.get(configuration.strip().casefold(), "")
        if not config:
            raise InventoryError("Configuration must be Standard, Men's, Women's, or Unisex.")
        sizing = size_system.strip() or "Apparel Size"
        allowed_sizes = {
            "Apparel Size", "OCP Garment Size", "Women's OCP Garment Size",
            "Unisex OCP Garment Size", "Women's Garment Size", "Shoe Size",
            "Coat Size", "Waist × Inseam", "Neck × Sleeve", "Headgear Size", "One Size",
        }
        if sizing not in allowed_sizes:
            raise InventoryError("Select a valid size system.")
        aliases = ", ".join(part.strip() for part in search_aliases.split(",") if part.strip())
        now = utc_now()
        with self.database.connect() as connection:
            try:
                if index_item_id is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO custom_index_items(
                            equipment_name, uniform_system, configuration, size_system,
                            search_aliases, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (name, system, config, sizing, aliases, now, now),
                    )
                    saved_id = int(cursor.lastrowid)
                else:
                    cursor = connection.execute(
                        """
                        UPDATE custom_index_items
                        SET equipment_name = ?, uniform_system = ?, configuration = ?,
                            size_system = ?, search_aliases = ?, updated_at = ?
                        WHERE index_item_id = ?
                        """,
                        (name, system, config, sizing, aliases, now, int(index_item_id)),
                    )
                    if cursor.rowcount == 0:
                        raise InventoryError("That custom Index item no longer exists.")
                    saved_id = int(index_item_id)
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise InventoryError("An Index item with that equipment name already exists.") from exc
        self.database.note_write()
        return saved_id

    def delete_custom_index_item(self, index_item_id: int) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM custom_index_items WHERE index_item_id = ?",
                (int(index_item_id),),
            )
            if cursor.rowcount == 0:
                raise InventoryError("That custom Index item no longer exists.")
            connection.commit()
        self.database.note_write()

    def dashboard_summary(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            barcode_placeholders = ", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)
            barcode_params = list(EASTER_EGG_BARCODE_IDS)
            cadet_placeholders = ", ".join("?" for _ in RESERVED_CADET_IDS)
            cadet_params = sorted(RESERVED_CADET_IDS)
            inventory = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS sku_count,
                    COALESCE(SUM(total_quantity), 0) AS total_units,
                    COALESCE(SUM(available_quantity), 0) AS available_units,
                    COALESCE(SUM(
                        CASE
                            WHEN status NOT IN ('Lost', 'Retired') THEN total_quantity - available_quantity
                            ELSE 0
                        END
                    ), 0) AS checked_out_units,
                    SUM(CASE WHEN status = 'Lost' THEN 1 ELSE 0 END) AS lost_rows,
                    SUM(CASE WHEN status = 'Retired' THEN 1 ELSE 0 END) AS retired_rows
                FROM items
                WHERE barcode_id NOT IN ({barcode_placeholders})
                """,
                barcode_params,
            ).fetchone()
            recent_activity = connection.execute(
                f"""
                SELECT *
                FROM (
                    SELECT
                        checkout_time AS event_time,
                        'Checkout' AS action,
                        barcode_id,
                        cadet_name,
                        cadet_email
                    FROM transactions
                    UNION ALL
                    SELECT
                        return_time AS event_time,
                        CASE
                            WHEN disposition IN ('Acquired / Permanent Issue', 'Purchased') THEN disposition
                            ELSE 'Return'
                        END AS action,
                        barcode_id,
                        cadet_name,
                        cadet_email
                    FROM transactions
                    WHERE return_time IS NOT NULL
                ) activity
                LEFT JOIN items ON items.barcode_id = activity.barcode_id
                WHERE activity.barcode_id NOT IN ({barcode_placeholders})
                ORDER BY event_time DESC
                LIMIT 12
                """,
                barcode_params,
            ).fetchall()
            cadet_count = connection.execute(
                f"SELECT COUNT(*) AS cadet_count FROM cadets WHERE cadet_id NOT IN ({cadet_placeholders})",
                cadet_params,
            ).fetchone()
        return {
            "sku_count": inventory["sku_count"],
            "total_units": inventory["total_units"],
            "available_units": inventory["available_units"],
            "checked_out_units": inventory["checked_out_units"],
            "lost_rows": inventory["lost_rows"] or 0,
            "retired_rows": inventory["retired_rows"] or 0,
            "cadet_count": cadet_count["cadet_count"],
            "recent_activity": [dict(row) for row in recent_activity],
        }

    def list_items(self, *, search: str = "", status_filter: str = "All") -> list[dict[str, Any]]:
        conditions: list[str] = [self._not_in_clause("barcode_id", EASTER_EGG_BARCODE_IDS)]
        params: list[Any] = list(EASTER_EGG_BARCODE_IDS)

        if search.strip():
            search_text = f"%{search.strip()}%"
            conditions.append(
                """
                (
                    barcode_id LIKE ?
                    OR item_name LIKE ?
                    OR category LIKE ?
                    OR variant LIKE ?
                    OR item_type LIKE ?
                    OR notes LIKE ?
                    OR wings_item_no LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM barcode_aliases AS alias
                        WHERE alias.canonical_barcode_id = items.barcode_id
                          AND alias.alias_barcode_id = ? COLLATE NOCASE
                    )
                )
                """
            )
            params.extend([search_text] * 7)
            params.append(search.strip())

        if status_filter and status_filter != "All":
            conditions.append("status = ?")
            params.append(status_filter)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                barcode_id,
                wings_item_no,
                item_name,
                category,
                variant,
                item_type,
                status,
                total_quantity,
                available_quantity,
                notes,
                created_at,
                updated_at
            FROM items
            {where_clause}
            ORDER BY category, item_type, variant, barcode_id
        """
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return enrich_items(self, [dict(row) for row in rows])

    def list_label_records(self, *, search: str = "", status_filter: str = "All") -> list[dict[str, Any]]:
        return self.list_items(search=search, status_filter=status_filter)

    def preview_generated_barcode(
        self,
        *,
        category: str,
        variant: str,
        item_type: str,
        item_name: str = "",
        wings_item_no: str = "",
    ) -> dict[str, Any]:
        wings_record: dict[str, Any] | None = None
        if str(wings_item_no).strip():
            wings_record = self.get_wings_catalog_item(wings_item_no)
            wings_item_no = str(wings_record["item_no"])
            category = str(wings_record["category"])
            variant = str(wings_record["size"] or "").strip() or ONE_SIZE_VARIANT
            item_type = str(wings_record["subcategory"] or wings_record["item_name"])
            item_name = str(wings_record["item_name"])
        category = self._clean_lookup(category, "Category")
        variant = self._clean_lookup(variant, "Variant")
        item_type = self._clean_lookup(item_type, "Item type")
        item_name = self._clean_item_name(item_name) or self._suggest_item_name(category, variant, item_type)

        with self.database.connect() as connection:
            existing = self._find_matching_item(
                connection,
                category=category,
                variant=variant,
                item_type=item_type,
                item_name=item_name,
                wings_item_no=str(wings_item_no).strip(),
            )
            if existing is not None:
                payload = dict(existing)
                payload["action"] = "restock"
                payload["summary"] = (
                    f"Existing barcode {payload['barcode_id']} will be reused for this inventory line."
                )
                return payload

            barcode_id = self._next_barcode_for_prefix(connection, category=category, variant=variant, item_type=item_type)
            return {
                "barcode_id": barcode_id,
                "item_name": item_name,
                "category": category,
                "variant": variant,
                "item_type": item_type,
                "total_quantity": 0,
                "available_quantity": 0,
                "status": "New",
                "action": "create",
                "summary": f"New barcode {barcode_id} will be created for this inventory line.",
                "wings_item_no": str(wings_item_no).strip(),
            }

    def save_generated_barcode(
        self,
        *,
        category: str,
        variant: str,
        item_type: str,
        units_per_barcode: int,
        item_name: str = "",
        notes: str = "",
        wings_item_no: str = "",
        allow_zero: bool = False,
    ) -> dict[str, Any]:
        units_per_barcode = self._validate_quantity(units_per_barcode, field_name="Units per barcode", allow_zero=allow_zero)
        preview = self.preview_generated_barcode(
            category=category,
            variant=variant,
            item_type=item_type,
            item_name=item_name,
            wings_item_no=wings_item_no,
        )

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            matching_item = self._find_matching_item(
                connection,
                category=str(preview["category"]),
                variant=str(preview["variant"]),
                item_type=str(preview["item_type"]),
                item_name=str(preview["item_name"]),
                wings_item_no=str(preview.get("wings_item_no") or wings_item_no).strip(),
            )
            if matching_item is not None:
                preview = dict(matching_item)
                preview["action"] = "restock"
            else:
                preview["action"] = "create"
                preview["barcode_id"] = self._next_barcode_for_prefix(
                    connection,
                    category=str(preview["category"]),
                    variant=str(preview["variant"]),
                    item_type=str(preview["item_type"]),
                )

            if preview["action"] == "restock":
                item = connection.execute(
                    "SELECT * FROM items WHERE barcode_id = ?",
                    (preview["barcode_id"],),
                ).fetchone()
                if item is None:
                    raise InventoryError("Existing barcode could not be loaded for restock.")
                resolved_item_no = preview.get("wings_item_no") or wings_item_no
                if not str(resolved_item_no or "").strip():
                    resolved_item_no = self._ensure_local_inventory_catalog_entry(connection, preview)
                merged_notes = self._append_note(item["notes"], notes)
                connection.execute(
                    """
                    UPDATE items
                    SET
                        item_name = ?,
                        wings_item_no = ?,
                        total_quantity = total_quantity + ?,
                        available_quantity = available_quantity + ?,
                        notes = ?,
                        updated_at = ?
                    WHERE barcode_id = ?
                    """,
                    (
                        preview["item_name"],
                        resolved_item_no,
                        units_per_barcode,
                        units_per_barcode,
                        merged_notes,
                        utc_now(),
                        preview["barcode_id"],
                    ),
                )
                self._record_catalog_values(
                    connection,
                    preview["category"],
                    preview["variant"],
                    preview["item_type"],
                    preview["item_name"],
                )
                self._sync_item_state(connection, preview["barcode_id"])
                row = connection.execute("SELECT * FROM items WHERE barcode_id = ?", (preview["barcode_id"],)).fetchone()
                connection.commit()
                action = "restocked"
            else:
                now = utc_now()
                resolved_item_no = preview.get("wings_item_no") or wings_item_no
                if not str(resolved_item_no or "").strip():
                    resolved_item_no = self._ensure_local_inventory_catalog_entry(connection, preview)
                connection.execute(
                    """
                    INSERT INTO items(
                        barcode_id, wings_item_no, item_name, category, variant, item_type, status,
                        notes, total_quantity, available_quantity, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'Available', ?, ?, ?, ?, ?)
                    """,
                    (
                        preview["barcode_id"],
                        resolved_item_no,
                        preview["item_name"],
                        preview["category"],
                        preview["variant"],
                        preview["item_type"],
                        notes.strip(),
                        units_per_barcode,
                        units_per_barcode,
                        now,
                        now,
                    ),
                )
                self._record_catalog_values(
                    connection,
                    preview["category"],
                    preview["variant"],
                    preview["item_type"],
                    preview["item_name"],
                )
                row = connection.execute("SELECT * FROM items WHERE barcode_id = ?", (preview["barcode_id"],)).fetchone()
                connection.commit()
                action = "created"

        self.database.note_write()
        payload = dict(row)
        payload["action"] = action
        return payload

    def export_label_book(
        self,
        *,
        search: str = "",
        status_filter: str = "All",
        barcode_ids: list[str] | None = None,
        barcode_quantities: dict[str, int] | None = None,
        filename_stem: str = "all_inventory_labels",
        open_after: bool = True,
    ) -> Path:
        if barcode_ids:
            records = self._fetch_label_records_by_barcode_ids(barcode_ids)
        else:
            records = self.list_label_records(search=search, status_filter=status_filter)
        if barcode_quantities:
            records = self._expand_label_records(
                records,
                barcode_quantities=barcode_quantities,
                barcode_order=barcode_ids or [str(record["barcode_id"]) for record in records],
            )
        if not records:
            raise InventoryError("No barcode records matched the current label export filter.")

        safe_stem = normalize_token(filename_stem, fallback="LABELS").lower()
        pdf_path = self.settings.label_dir / f"{safe_stem}.pdf"
        write_label_pdf(pdf_path, records, self.settings.org_name, title=f"{self.settings.org_name} Labels")
        if open_after:
            open_file(pdf_path)
        return pdf_path

    def get_item(self, barcode_id: str) -> dict[str, Any] | None:
        cleaned_barcode = barcode_id.strip().upper()
        if self._is_easter_egg_barcode(cleaned_barcode):
            return None
        with self.database.connect() as connection:
            cleaned_barcode = self._resolve_barcode_alias(connection, cleaned_barcode)
            row = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?",
                (cleaned_barcode,),
            ).fetchone()
        return dict(row) if row else None

    def get_barcode_context(self, barcode_id: str) -> dict[str, Any]:
        cleaned_barcode = barcode_id.strip().upper()
        if self._is_easter_egg_barcode(cleaned_barcode):
            raise InventoryError("Barcode not found in inventory.")
        with self.database.connect() as connection:
            cleaned_barcode = self._resolve_barcode_alias(connection, cleaned_barcode)
            item = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?",
                (cleaned_barcode,),
            ).fetchone()
            open_transactions = connection.execute(
                """
                SELECT
                    transaction_id,
                    cadet_name,
                    cadet_email,
                    checkout_time,
                    approved_by_name,
                    approved_by_role,
                    condition_notes
                FROM transactions
                WHERE barcode_id = ? AND return_time IS NULL
                ORDER BY checkout_time
                """,
                (cleaned_barcode,),
            ).fetchall()

        if item is None:
            raise InventoryError("Barcode not found in inventory.")

        payload = dict(item)
        payload["open_transactions"] = [dict(row) for row in open_transactions]
        return payload

    def update_item(
        self,
        *,
        barcode_id: str,
        item_name: str,
        category: str,
        variant: str,
        item_type: str,
        total_quantity: int,
        notes: str = "",
    ) -> dict[str, Any]:
        barcode = barcode_id.strip().upper()
        if not barcode:
            raise InventoryError("Select a barcode to edit first.")

        quantity = self._validate_quantity(total_quantity, field_name="Total quantity", allow_zero=True)
        category = self._clean_lookup(category, "Category")
        variant = self._clean_lookup(variant, "Variant")
        item_type = self._clean_lookup(item_type, "Item type")
        item_name = self._clean_item_name(item_name) or self._suggest_item_name(
            category, variant, item_type
        )

        with self.database.connect() as connection:
            barcode = self._resolve_barcode_alias(connection, barcode)
            existing = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?", (barcode,)
            ).fetchone()
            if existing is None:
                raise InventoryError("That barcode no longer exists.")

            existing_item_no = str(existing["wings_item_no"] or "").strip()
            duplicate = self._find_matching_item(
                connection,
                category=category,
                variant=variant,
                item_type=item_type,
                item_name=item_name,
                wings_item_no=existing_item_no,
                exclude_barcode=barcode,
            )
            if duplicate is None and existing_item_no and not existing_item_no.isdigit():
                duplicate = self._find_matching_item(
                    connection,
                    category=category,
                    variant=variant,
                    item_type=item_type,
                    item_name=item_name,
                    exclude_barcode=barcode,
                )
            if duplicate is not None:
                raise InventoryError(
                    f"Those item details already use barcode {duplicate['barcode_id']}. "
                    "Restock that barcode instead of creating duplicate item definitions."
                )

            checked_out = self._open_checkout_count(connection, barcode)
            if quantity < checked_out:
                raise InventoryError(
                    f"Total quantity cannot be below the {checked_out} unit(s) currently checked out."
                )

            connection.execute(
                """
                UPDATE items
                SET item_name = ?, category = ?, variant = ?, item_type = ?,
                    total_quantity = ?, available_quantity = ?, notes = ?, updated_at = ?
                WHERE barcode_id = ?
                """,
                (
                    item_name,
                    category,
                    variant,
                    item_type,
                    quantity,
                    max(quantity - checked_out, 0),
                    notes.strip(),
                    utc_now(),
                    barcode,
                ),
            )
            self._record_catalog_values(connection, category, variant, item_type, item_name)
            self._sync_item_state(connection, barcode)
            updated = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?", (barcode,)
            ).fetchone()
            connection.commit()

        self.database.note_write()
        return dict(updated)

    def create_manual_item(
        self,
        *,
        barcode_id: str,
        item_name: str,
        category: str,
        variant: str,
        item_type: str,
        quantity: int,
        notes: str = "",
    ) -> str:
        barcode = barcode_id.strip().upper()
        if not barcode:
            raise InventoryError("Barcode is required.")
        quantity = self._validate_quantity(quantity)
        category = self._clean_lookup(category, "Category")
        variant = self._clean_lookup(variant, "Variant")
        item_type = self._clean_lookup(item_type, "Item type")
        item_name = self._clean_item_name(item_name) or self._suggest_item_name(category, variant, item_type)

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM items WHERE barcode_id = ?",
                (barcode,),
            ).fetchone()
            if exists:
                raise InventoryError("That barcode already exists. Restock it instead of creating a duplicate.")

            reserved_alias = connection.execute(
                "SELECT canonical_barcode_id FROM barcode_aliases WHERE alias_barcode_id = ? COLLATE NOCASE",
                (barcode,),
            ).fetchone()
            if reserved_alias is not None:
                raise InventoryError(
                    f"Barcode {barcode} is reserved as an alias for {reserved_alias['canonical_barcode_id']}. "
                    "Use a different barcode."
                )

            duplicate = self._find_matching_item(
                connection,
                category=category,
                variant=variant,
                item_type=item_type,
                item_name=item_name,
            )
            if duplicate is not None:
                raise InventoryError(
                    f"An identical item already uses barcode {duplicate['barcode_id']}. "
                    "Restock that barcode instead of creating another one."
                )

            now = utc_now()
            local_item_no = self._ensure_local_inventory_catalog_entry(
                connection,
                {
                    "item_name": item_name,
                    "category": category,
                    "variant": variant,
                    "item_type": item_type,
                },
            )
            connection.execute(
                """
                INSERT INTO items(
                    barcode_id, wings_item_no, item_name, category, variant, item_type, status,
                    notes, total_quantity, available_quantity, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Available', ?, ?, ?, ?, ?)
                """,
                (
                    barcode,
                    local_item_no,
                    item_name,
                    category,
                    variant,
                    item_type,
                    notes.strip(),
                    quantity,
                    quantity,
                    now,
                    now,
                ),
            )
            self._record_catalog_values(connection, category, variant, item_type, item_name)
            connection.commit()

        self.database.note_write()
        return barcode

    def restock_item(self, *, barcode_id: str, quantity: int, notes: str = "") -> None:
        barcode = barcode_id.strip().upper()
        quantity = self._validate_quantity(quantity)

        with self.database.connect() as connection:
            barcode = self._resolve_barcode_alias(connection, barcode)
            item = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?",
                (barcode,),
            ).fetchone()
            if item is None:
                raise InventoryError("Barcode not found. Create the item first.")
            if item["status"] in {"Retired", "Lost"}:
                raise InventoryError("Reactivate the item before restocking a retired or lost barcode.")

            merged_notes = self._append_note(item["notes"], notes)
            connection.execute(
                """
                UPDATE items
                SET
                    total_quantity = total_quantity + ?,
                    available_quantity = available_quantity + ?,
                    notes = ?,
                    updated_at = ?
                WHERE barcode_id = ?
                """,
                (quantity, quantity, merged_notes, utc_now(), barcode),
            )
            self._sync_item_state(connection, barcode)
            connection.commit()

        self.database.note_write()

    def set_item_status(self, *, barcode_id: str, status: str, notes: str = "") -> None:
        barcode = barcode_id.strip().upper()
        if status not in {"Available", "Retired", "Lost"}:
            raise InventoryError("Only Available, Retired, or Lost can be set manually.")

        with self.database.connect() as connection:
            barcode = self._resolve_barcode_alias(connection, barcode)
            item = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?",
                (barcode,),
            ).fetchone()
            if item is None:
                raise InventoryError("Barcode not found.")

            open_units = self._open_checkout_count(connection, barcode)
            if status in {"Retired", "Lost"} and open_units > 0:
                raise InventoryError("All checked-out units must be returned before retiring or marking an item lost.")

            merged_notes = self._append_note(item["notes"], notes)
            if status == "Available":
                connection.execute(
                    """
                    UPDATE items
                    SET notes = ?, updated_at = ?, available_quantity = total_quantity, status = 'Available'
                    WHERE barcode_id = ?
                    """,
                    (merged_notes, utc_now(), barcode),
                )
                self._sync_item_state(connection, barcode)
            else:
                connection.execute(
                    """
                    UPDATE items
                    SET notes = ?, updated_at = ?, available_quantity = 0, status = ?
                    WHERE barcode_id = ?
                    """,
                    (merged_notes, utc_now(), status, barcode),
                )
            connection.commit()

        self.database.note_write()

    def delete_item(self, *, barcode_id: str) -> None:
        barcode = barcode_id.strip().upper()
        if not barcode:
            raise InventoryError("Barcode is required.")

        with self.database.connect() as connection:
            barcode = self._resolve_barcode_alias(connection, barcode)
            item = connection.execute("SELECT 1 FROM items WHERE barcode_id = ?", (barcode,)).fetchone()
            if item is None:
                raise InventoryError("Barcode not found.")

            connection.execute("DELETE FROM transactions WHERE barcode_id = ?", (barcode,))
            connection.execute("DELETE FROM items WHERE barcode_id = ?", (barcode,))
            connection.commit()

        self.database.note_write()

    def generate_barcodes(
        self,
        *,
        category: str,
        variant: str,
        item_type: str,
        label_count: int,
        units_per_barcode: int,
        item_name: str = "",
        notes: str = "",
        open_after: bool = True,
    ) -> dict[str, Any]:
        label_count = self._validate_quantity(label_count, field_name="Barcode count")
        units_per_barcode = self._validate_quantity(units_per_barcode, field_name="Units per barcode")
        category = self._clean_lookup(category, "Category")
        variant = self._clean_lookup(variant, "Variant")
        item_type = self._clean_lookup(item_type, "Item type")
        item_name = self._clean_item_name(item_name) or self._suggest_item_name(category, variant, item_type)
        created_records: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            local_item_no = self._ensure_local_inventory_catalog_entry(
                connection,
                {
                    "item_name": item_name,
                    "category": category,
                    "variant": variant,
                    "item_type": item_type,
                },
            )
            for _ in range(label_count):
                barcode_id = self._next_barcode_for_prefix(
                    connection,
                    category=category,
                    variant=variant,
                    item_type=item_type,
                )

                now = utc_now()
                connection.execute(
                    """
                    INSERT INTO items(
                        barcode_id, wings_item_no, item_name, category, variant, item_type, status,
                        notes, total_quantity, available_quantity, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'Available', ?, ?, ?, ?, ?)
                    """,
                    (
                        barcode_id,
                        local_item_no,
                        item_name,
                        category,
                        variant,
                        item_type,
                        notes.strip(),
                        units_per_barcode,
                        units_per_barcode,
                        now,
                        now,
                    ),
                )
                created_records.append(
                    {
                        "barcode_id": barcode_id,
                        "item_name": item_name,
                        "category": category,
                        "variant": variant,
                        "item_type": item_type,
                        "total_quantity": units_per_barcode,
                        "status": "Available",
                    }
                )
            self._record_catalog_values(connection, category, variant, item_type, item_name)
            connection.commit()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_pdf_path = self.settings.label_dir / f"label_batch_{timestamp}.pdf"
        write_label_pdf(
            batch_pdf_path,
            created_records,
            self.settings.org_name,
            title=f"{self.settings.org_name} Batch Labels",
        )
        master_pdf_path = self.export_label_book(open_after=False)

        if open_after:
            open_file(batch_pdf_path)

        self.database.note_write()
        return {
            "records": created_records,
            "batch_pdf_path": batch_pdf_path,
            "master_pdf_path": master_pdf_path,
        }

    def save_cadet(self, *, cadet_name: str, cadet_email: str) -> dict[str, Any]:
        name, email = self._validate_cadet_identity(cadet_name, cadet_email)
        with self.database.connect() as connection:
            cadet = self._upsert_cadet(connection, name, email)
            connection.execute(
                """
                UPDATE transactions
                SET cadet_id = ?
                WHERE cadet_id IS NULL AND lower(cadet_email) = lower(?)
                """,
                (cadet["cadet_id"], email),
            )
            connection.commit()

        self.database.note_write()
        return cadet

    def update_cadet(self, *, cadet_id: int, cadet_name: str, cadet_email: str) -> dict[str, Any]:
        name, email = self._validate_cadet_identity(cadet_name, cadet_email)
        with self.database.connect() as connection:
            existing = connection.execute(
                """
                SELECT cadet_id, full_name, email, created_at, updated_at
                FROM cadets
                WHERE cadet_id = ?
                """,
                (cadet_id,),
            ).fetchone()
            if existing is None:
                raise InventoryError("Saved cadet record not found.")

            duplicate = connection.execute(
                """
                SELECT cadet_id
                FROM cadets
                WHERE lower(email) = lower(?) AND cadet_id <> ?
                """,
                (email, cadet_id),
            ).fetchone()
            if duplicate is not None:
                raise InventoryError("Another saved cadet already uses that email address.")

            previous_email = str(existing["email"] or "")
            connection.execute(
                """
                UPDATE cadets
                SET full_name = ?, email = ?, updated_at = ?
                WHERE cadet_id = ?
                """,
                (name, email, utc_now(), cadet_id),
            )
            connection.execute(
                """
                UPDATE transactions
                SET cadet_id = ?
                WHERE cadet_id IS NULL
                  AND (lower(cadet_email) = lower(?) OR lower(cadet_email) = lower(?))
                """,
                (cadet_id, previous_email, email),
            )
            row = connection.execute(
                """
                SELECT cadet_id, full_name, email, created_at, updated_at
                FROM cadets
                WHERE cadet_id = ?
                """,
                (cadet_id,),
            ).fetchone()
            connection.commit()

        self.database.note_write()
        return dict(row)

    def save_cadet_size_entry(
        self,
        *,
        cadet_id: int,
        size_label: str,
        size_value: str,
        category: str = "",
        catalog_item_no: str = "",
        notes: str = "",
        size_entry_id: int | None = None,
    ) -> dict[str, Any]:
        cleaned_label = " ".join(str(size_label).split())
        cleaned_value = " ".join(str(size_value).split())
        cleaned_category = " ".join(str(category).split())
        cleaned_item_no = str(catalog_item_no).strip()
        if cleaned_item_no.isdigit():
            cleaned_item_no = str(int(cleaned_item_no))
        cleaned_notes = str(notes).strip()
        if not cleaned_label:
            raise InventoryError("Size item or measurement is required.")
        if not cleaned_value:
            raise InventoryError("Size or measurement value is required.")

        with self.database.connect() as connection:
            cadet = connection.execute(
                "SELECT cadet_id FROM cadets WHERE cadet_id = ?",
                (int(cadet_id),),
            ).fetchone()
            if cadet is None:
                raise InventoryError("Saved cadet record not found.")
            now = utc_now()
            try:
                if size_entry_id is not None:
                    existing = connection.execute(
                        "SELECT size_entry_id FROM cadet_size_entries WHERE size_entry_id = ? AND cadet_id = ?",
                        (int(size_entry_id), int(cadet_id)),
                    ).fetchone()
                    if existing is None:
                        raise InventoryError("Cadet size entry not found.")
                    connection.execute(
                        """
                        UPDATE cadet_size_entries
                        SET size_label = ?, size_value = ?, category = ?,
                            catalog_item_no = ?, notes = ?, updated_at = ?
                        WHERE size_entry_id = ? AND cadet_id = ?
                        """,
                        (
                            cleaned_label,
                            cleaned_value,
                            cleaned_category,
                            cleaned_item_no,
                            cleaned_notes,
                            now,
                            int(size_entry_id),
                            int(cadet_id),
                        ),
                    )
                    resolved_id = int(size_entry_id)
                else:
                    connection.execute(
                        """
                        INSERT INTO cadet_size_entries(
                            cadet_id, size_label, size_value, category, catalog_item_no,
                            notes, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(cadet_id, size_label) DO UPDATE SET
                            size_value = excluded.size_value,
                            category = excluded.category,
                            catalog_item_no = excluded.catalog_item_no,
                            notes = excluded.notes,
                            updated_at = excluded.updated_at
                        """,
                        (
                            int(cadet_id),
                            cleaned_label,
                            cleaned_value,
                            cleaned_category,
                            cleaned_item_no,
                            cleaned_notes,
                            now,
                            now,
                        ),
                    )
                    resolved = connection.execute(
                        """
                        SELECT size_entry_id
                        FROM cadet_size_entries
                        WHERE cadet_id = ? AND size_label = ? COLLATE NOCASE
                        """,
                        (int(cadet_id), cleaned_label),
                    ).fetchone()
                    resolved_id = int(resolved["size_entry_id"])
            except sqlite3.IntegrityError as exc:
                raise InventoryError("That cadet already has an entry with this size label.") from exc

            row = connection.execute(
                """
                SELECT size_entry_id, cadet_id, size_label, size_value, category,
                       catalog_item_no, notes, created_at, updated_at
                FROM cadet_size_entries
                WHERE size_entry_id = ?
                """,
                (resolved_id,),
            ).fetchone()
            connection.commit()

        self.database.note_write()
        return dict(row)

    def list_cadet_size_entries(self, cadet_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            cadet = connection.execute(
                "SELECT cadet_id FROM cadets WHERE cadet_id = ?",
                (int(cadet_id),),
            ).fetchone()
            if cadet is None:
                raise InventoryError("Saved cadet record not found.")
            rows = connection.execute(
                """
                SELECT size_entry_id, cadet_id, size_label, size_value, category,
                       catalog_item_no, notes, created_at, updated_at
                FROM cadet_size_entries
                WHERE cadet_id = ?
                ORDER BY size_label COLLATE NOCASE, size_entry_id
                """,
                (int(cadet_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_cadet_fitting_categories(self) -> list[str]:
        """Return searchable catalog categories for the guided cadet fitting index."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT category
                FROM wings_catalog
                WHERE trim(category) <> ''
                  AND item_no NOT LIKE 'LOCAL-RANK-SB-%'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM hidden_index_items hidden
                      WHERE hidden.item_no = wings_catalog.item_no
                  )
                ORDER BY category COLLATE NOCASE
                """
            ).fetchall()
        return [str(row["category"]).strip() for row in rows]

    def list_cadet_fitting_options(
        self,
        *,
        category: str = "All",
        search: str = "",
    ) -> list[dict[str, Any]]:
        """List known fitting sizes with current stock counts for fast category lookup."""
        conditions = [
            "catalog.item_no NOT LIKE 'LOCAL-RANK-SB-%'",
            "NOT EXISTS (SELECT 1 FROM hidden_index_items hidden WHERE hidden.item_no = catalog.item_no)",
        ]
        params: list[Any] = []
        cleaned_category = str(category).strip()
        if cleaned_category and cleaned_category != "All":
            conditions.append("catalog.category = ? COLLATE NOCASE")
            params.append(cleaned_category)
        fitting_search_aliases = {
            "first": "1st",
            "second": "2d",
            "lieutenant": "lt",
            "captain": "capt",
            "major": "maj",
            "colonel": "col",
        }
        for word in [part for part in str(search).casefold().split() if part]:
            searchable_word = str(int(word)) if word.isdigit() else fitting_search_aliases.get(word, word)
            token = f"%{searchable_word}%"
            conditions.append(
                """
                (
                    lower(catalog.item_no) LIKE ? OR lower(catalog.item_name) LIKE ?
                    OR lower(catalog.size) LIKE ? OR lower(catalog.category) LIKE ?
                    OR lower(catalog.subcategory) LIKE ? OR lower(catalog.sex) LIKE ?
                    OR lower(catalog.stock_number) LIKE ?
                )
                """
            )
            params.extend([token] * 7)

        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                WITH inventory_totals AS (
                    SELECT
                        wings_item_no,
                        COALESCE(SUM(total_quantity), 0) AS total_quantity,
                        COALESCE(SUM(available_quantity), 0) AS available_quantity
                    FROM items
                    GROUP BY wings_item_no
                )
                SELECT
                    catalog.item_no,
                    catalog.item_name,
                    catalog.size,
                    catalog.category,
                    catalog.subcategory,
                    catalog.sex,
                    catalog.stock_number,
                    catalog.source,
                    catalog.is_wings,
                    COALESCE(inventory.total_quantity, 0) AS total_quantity,
                    COALESCE(inventory.available_quantity, 0) AS available_quantity
                FROM wings_catalog catalog
                LEFT JOIN inventory_totals inventory
                    ON inventory.wings_item_no = catalog.item_no
                WHERE {' AND '.join(conditions)}
                ORDER BY
                    catalog.category COLLATE NOCASE,
                    catalog.subcategory COLLATE NOCASE,
                    catalog.item_name COLLATE NOCASE,
                    catalog.sex COLLATE NOCASE,
                    catalog.size COLLATE NOCASE,
                    catalog.is_wings DESC,
                    CASE WHEN catalog.is_wings = 1 THEN CAST(catalog.item_no AS INTEGER) END,
                    catalog.item_no
                """,
                params,
            ).fetchall()

        options: list[dict[str, Any]] = []
        for source_row in rows:
            row = dict(source_row)
            raw_item_no = str(row["item_no"])
            item_name = str(row["item_name"] or "").strip()
            sex = str(row["sex"] or "").strip().upper()
            lowered_name = item_name.casefold()
            if sex == "M" and not any(token in lowered_name for token in ("men", "male")):
                fitting_label = f"{item_name} (Men's)"
            elif sex == "F" and not any(token in lowered_name for token in ("women", "female")):
                fitting_label = f"{item_name} (Women's)"
            else:
                fitting_label = item_name
            row["item_no_key"] = raw_item_no
            row["item_no"] = (
                self._format_wings_item_no(raw_item_no)
                if int(row["is_wings"]) == 1
                else raw_item_no
            )
            row["fitting_label"] = fitting_label
            options.append(row)
        return options

    def delete_cadet_size_entry(self, *, cadet_id: int, size_entry_id: int) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM cadet_size_entries WHERE size_entry_id = ? AND cadet_id = ?",
                (int(size_entry_id), int(cadet_id)),
            )
            if cursor.rowcount < 1:
                raise InventoryError("Cadet size entry not found.")
            connection.commit()
        self.database.note_write()

    def list_cadets(self, *, search: str = "") -> list[dict[str, Any]]:
        conditions = [self._not_in_clause("c.cadet_id", sorted(RESERVED_CADET_IDS))]
        params: list[Any] = []
        params.extend(sorted(RESERVED_CADET_IDS))
        if search.strip():
            search_text = f"%{search.strip().lower()}%"
            conditions.append("(lower(full_name) LIKE ? OR lower(email) LIKE ?)")
            params.extend([search_text, search_text])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                c.cadet_id,
                c.full_name,
                c.email,
                c.created_at,
                c.updated_at,
                COALESCE((
                    SELECT COUNT(*)
                    FROM transactions t
                    WHERE
                        (t.cadet_id = c.cadet_id OR (t.cadet_id IS NULL AND lower(t.cadet_email) = lower(c.email)))
                        AND t.return_time IS NULL
                ), 0) AS open_items,
                COALESCE((
                    SELECT COUNT(*)
                    FROM transactions t
                    WHERE t.cadet_id = c.cadet_id OR (t.cadet_id IS NULL AND lower(t.cadet_email) = lower(c.email))
                ), 0) AS total_transactions,
                COALESCE((
                    SELECT COUNT(*)
                    FROM transactions t
                    WHERE
                        (t.cadet_id = c.cadet_id OR (t.cadet_id IS NULL AND lower(t.cadet_email) = lower(c.email)))
                        AND t.disposition IN ('Acquired / Permanent Issue', 'Purchased')
                ), 0) AS acquired_items,
                (
                    SELECT MAX(t.checkout_time)
                    FROM transactions t
                    WHERE t.cadet_id = c.cadet_id OR (t.cadet_id IS NULL AND lower(t.cadet_email) = lower(c.email))
                ) AS last_checkout_time
            FROM cadets c
            {where_clause}
            ORDER BY c.full_name, c.email
        """
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_cadet_details(self, cadet_id: int) -> dict[str, Any]:
        if self._is_easter_egg_cadet_id(cadet_id):
            raise InventoryError("Saved cadet record not found.")
        barcode_placeholders = ", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)
        with self.database.connect() as connection:
            cadet = connection.execute(
                "SELECT cadet_id, full_name, email, created_at, updated_at FROM cadets WHERE cadet_id = ?",
                (cadet_id,),
            ).fetchone()
            if cadet is None:
                raise InventoryError("Saved cadet record not found.")

            current_items = connection.execute(
                f"""
                SELECT
                    t.transaction_id,
                    t.barcode_id,
                    i.item_name,
                    i.category,
                    i.variant,
                    i.item_type,
                    t.checkout_time,
                    t.approved_by_name,
                    t.approved_by_role,
                    t.condition_notes
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE
                    (t.cadet_id = ? OR (t.cadet_id IS NULL AND lower(t.cadet_email) = lower(?)))
                    AND t.return_time IS NULL
                    AND t.barcode_id NOT IN ({barcode_placeholders})
                ORDER BY t.checkout_time DESC, t.transaction_id DESC
                """,
                (cadet_id, cadet["email"], *EASTER_EGG_BARCODE_IDS),
            ).fetchall()
            history = connection.execute(
                f"""
                SELECT
                    t.transaction_id,
                    t.barcode_id,
                    i.item_name,
                    t.checkout_time,
                    CASE
                        WHEN t.return_time IS NULL THEN 'Checked Out'
                        WHEN trim(t.disposition) <> '' THEN t.disposition
                        ELSE 'Returned'
                    END AS disposition,
                    t.return_time AS closed_time,
                    t.approved_by_name,
                    t.approved_by_role,
                    t.return_approved_by_name AS closed_by_name,
                    t.return_approved_by_role AS closed_by_role,
                    t.condition_notes
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE (t.cadet_id = ? OR (t.cadet_id IS NULL AND lower(t.cadet_email) = lower(?)))
                  AND t.barcode_id NOT IN ({barcode_placeholders})
                ORDER BY t.checkout_time DESC, t.transaction_id DESC
                """,
                (cadet_id, cadet["email"], *EASTER_EGG_BARCODE_IDS),
            ).fetchall()
            size_entries = connection.execute(
                """
                SELECT size_entry_id, cadet_id, size_label, size_value, category,
                       catalog_item_no, notes, created_at, updated_at
                FROM cadet_size_entries
                WHERE cadet_id = ?
                ORDER BY size_label COLLATE NOCASE, size_entry_id
                """,
                (cadet_id,),
            ).fetchall()

        history_rows = [dict(row) for row in history]
        return {
            "cadet": dict(cadet),
            "current_items": [dict(row) for row in current_items],
            "history": history_rows,
            "size_entries": [dict(row) for row in size_entries],
            "acquired_items": sum(
                1 for row in history_rows if row["disposition"] in ACQUISITION_DISPOSITIONS
            ),
        }

    def acquire_checked_out_items(
        self,
        *,
        cadet_id: int,
        transaction_ids: list[int],
        disposition: str,
        approved_by: dict[str, Any] | None = None,
        notes: str = "",
    ) -> list[dict[str, Any]]:
        cleaned_disposition = " ".join(str(disposition).split())
        if cleaned_disposition not in ACQUISITION_DISPOSITIONS:
            raise InventoryError("Disposition must be Acquired / Permanent Issue or Purchased.")

        cleaned_transaction_ids: list[int] = []
        seen_ids: set[int] = set()
        for transaction_id in transaction_ids:
            try:
                cleaned_id = int(transaction_id)
            except (TypeError, ValueError) as exc:
                raise InventoryError("Select valid checked-out transaction rows.") from exc
            if cleaned_id < 1 or cleaned_id in seen_ids:
                continue
            seen_ids.add(cleaned_id)
            cleaned_transaction_ids.append(cleaned_id)
        if not cleaned_transaction_ids:
            raise InventoryError("Select at least one checked-out item first.")

        approval = self._normalize_admin_identity(approved_by)
        self.database.create_backup(reason="pre_acquisition")
        placeholders = ", ".join("?" for _ in cleaned_transaction_ids)
        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            cadet = connection.execute(
                "SELECT cadet_id, full_name, email FROM cadets WHERE cadet_id = ?",
                (int(cadet_id),),
            ).fetchone()
            if cadet is None:
                raise InventoryError("Saved cadet record not found.")

            rows = connection.execute(
                f"""
                SELECT
                    t.transaction_id,
                    t.barcode_id,
                    t.cadet_id,
                    t.cadet_email,
                    t.return_time,
                    t.condition_notes,
                    i.item_name,
                    i.total_quantity,
                    i.notes AS item_notes
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE t.transaction_id IN ({placeholders})
                ORDER BY t.transaction_id
                """,
                cleaned_transaction_ids,
            ).fetchall()
            if len(rows) != len(cleaned_transaction_ids):
                raise InventoryError("One or more selected checkout records no longer exist.")

            for row in rows:
                belongs_to_cadet = (
                    row["cadet_id"] == cadet["cadet_id"]
                    or (
                        row["cadet_id"] is None
                        and str(row["cadet_email"] or "").casefold()
                        == str(cadet["email"] or "").casefold()
                    )
                )
                if not belongs_to_cadet:
                    raise InventoryError("Every selected item must belong to the selected cadet.")
                if row["return_time"] is not None:
                    raise InventoryError("One or more selected items are no longer checked out.")

            units_by_barcode: dict[str, int] = {}
            item_rows: dict[str, sqlite3.Row] = {}
            for row in rows:
                barcode = str(row["barcode_id"])
                units_by_barcode[barcode] = units_by_barcode.get(barcode, 0) + 1
                item_rows[barcode] = row
            for barcode, units in units_by_barcode.items():
                if int(item_rows[barcode]["total_quantity"]) < units:
                    raise InventoryError(
                        f"Inventory total for {barcode} is below the selected acquisition quantity."
                    )

            closed_at = utc_now()
            undo_before = [dict(row) for row in connection.execute(
                f'SELECT * FROM transactions WHERE transaction_id IN ({placeholders}) ORDER BY transaction_id',
                cleaned_transaction_ids)]
            undo_notes = {barcode: {'before': row['item_notes'] or ''} for barcode, row in item_rows.items()}
            reason = " ".join(str(notes).split())
            transaction_note = cleaned_disposition
            if reason:
                transaction_note = f"{transaction_note}: {reason}"
            for row in rows:
                connection.execute(
                    """
                    UPDATE transactions
                    SET return_time = ?, return_approved_by_admin_id = ?,
                        return_approved_by_name = ?, return_approved_by_role = ?,
                        return_approved_at = ?, disposition = ?, condition_notes = ?
                    WHERE transaction_id = ?
                    """,
                    (
                        closed_at,
                        approval["admin_id"],
                        approval["approved_by_name"],
                        approval["approved_by_role"],
                        closed_at,
                        cleaned_disposition,
                        self._append_note(row["condition_notes"], transaction_note),
                        row["transaction_id"],
                    ),
                )

            for barcode, units in units_by_barcode.items():
                inventory_note = (
                    f"{units} unit(s) removed as {cleaned_disposition} for {cadet['full_name']}."
                )
                if reason:
                    inventory_note = f"{inventory_note} Reason: {reason}"
                connection.execute(
                    """
                    UPDATE items
                    SET total_quantity = total_quantity - ?, notes = ?, updated_at = ?
                    WHERE barcode_id = ?
                    """,
                    (
                        units,
                        self._append_note(item_rows[barcode]["item_notes"], inventory_note),
                        closed_at,
                        barcode,
                    ),
                )
                self._sync_item_state(connection, barcode)
                undo_notes[barcode]['after'] = connection.execute(
                    'SELECT notes FROM items WHERE barcode_id=?', (barcode,)).fetchone()[0] or ''
            undo_after = [dict(row) for row in connection.execute(
                f'SELECT * FROM transactions WHERE transaction_id IN ({placeholders}) ORDER BY transaction_id',
                cleaned_transaction_ids)]
            connection.execute('''INSERT INTO acquisition_actions(cadet_id,created_at,before_json,after_json,item_notes_json)
                VALUES(?,?,?,?,?)''', (int(cadet_id),closed_at,json.dumps(undo_before),json.dumps(undo_after),json.dumps(undo_notes)))
            connection.commit()

        self.database.note_write()
        return [
            {
                "transaction_id": int(row["transaction_id"]),
                "barcode_id": str(row["barcode_id"]),
                "item_name": str(row["item_name"]),
                "disposition": cleaned_disposition,
                "closed_time": closed_at,
            }
            for row in rows
        ]

    def return_cadet_items(
        self,
        *,
        cadet_id: int,
        transaction_ids: list[int],
        approved_by: dict[str, Any] | None = None,
        condition_notes: str = "",
    ) -> list[dict[str, Any]]:
        try:
            cleaned_cadet_id = int(cadet_id)
        except (TypeError, ValueError) as exc:
            raise InventoryError("Select a valid saved cadet who is returning items.") from exc

        cleaned_transaction_ids: list[int] = []
        seen_ids: set[int] = set()
        for transaction_id in transaction_ids:
            try:
                cleaned_id = int(transaction_id)
            except (TypeError, ValueError) as exc:
                raise InventoryError("Select valid checked-out transaction rows.") from exc
            if cleaned_id < 1 or cleaned_id in seen_ids:
                continue
            seen_ids.add(cleaned_id)
            cleaned_transaction_ids.append(cleaned_id)
        if not cleaned_transaction_ids:
            raise InventoryError("Select at least one checked-out item to return.")

        approval = self._normalize_admin_identity(approved_by)
        placeholders = ", ".join("?" for _ in cleaned_transaction_ids)
        with self.database.connect() as connection:
            cadet = connection.execute(
                "SELECT cadet_id, full_name, email FROM cadets WHERE cadet_id = ?",
                (cleaned_cadet_id,),
            ).fetchone()
            if cadet is None:
                raise InventoryError("Saved cadet record not found.")

            rows = connection.execute(
                f"""
                SELECT
                    t.transaction_id,
                    t.barcode_id,
                    t.cadet_id,
                    t.cadet_name,
                    t.cadet_email,
                    t.checkout_time,
                    t.return_time,
                    t.condition_notes,
                    i.item_name
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE t.transaction_id IN ({placeholders})
                ORDER BY t.transaction_id
                """,
                cleaned_transaction_ids,
            ).fetchall()
            if len(rows) != len(cleaned_transaction_ids):
                raise InventoryError("One or more selected checkout records no longer exist.")

            for row in rows:
                belongs_to_cadet = (
                    row["cadet_id"] == cadet["cadet_id"]
                    or (
                        row["cadet_id"] is None
                        and str(row["cadet_email"] or "").casefold()
                        == str(cadet["email"] or "").casefold()
                    )
                )
                if not belongs_to_cadet:
                    raise InventoryError("Every selected return item must belong to the selected cadet.")
                if row["return_time"] is not None:
                    raise InventoryError("One or more selected items are no longer checked out.")

            returned_at = utc_now()
            cleaned_notes = " ".join(str(condition_notes).split())
            affected_barcodes: set[str] = set()
            for row in rows:
                connection.execute(
                    """
                    UPDATE transactions
                    SET return_time = ?, return_approved_by_admin_id = ?,
                        return_approved_by_name = ?, return_approved_by_role = ?,
                        return_approved_at = ?, disposition = 'Returned', condition_notes = ?
                    WHERE transaction_id = ?
                    """,
                    (
                        returned_at,
                        approval["admin_id"],
                        approval["approved_by_name"],
                        approval["approved_by_role"],
                        returned_at,
                        self._append_note(row["condition_notes"], cleaned_notes),
                        row["transaction_id"],
                    ),
                )
                affected_barcodes.add(str(row["barcode_id"]))

            for barcode in affected_barcodes:
                self._sync_item_state(connection, barcode)
            connection.commit()

        self.database.note_write()
        return [
            {
                "transaction_id": int(row["transaction_id"]),
                "barcode_id": str(row["barcode_id"]),
                "item_name": str(row["item_name"]),
                "cadet_id": cleaned_cadet_id,
                "cadet_name": str(cadet["full_name"]),
                "cadet_email": str(cadet["email"]),
                "checkout_time": str(row["checkout_time"]),
                "return_time": returned_at,
                "disposition": "Returned",
            }
            for row in rows
        ]

    def delete_cadet(self, *, cadet_id: int) -> None:
        with self.database.connect() as connection:
            cadet = connection.execute(
                "SELECT cadet_id, full_name, email FROM cadets WHERE cadet_id = ?",
                (cadet_id,),
            ).fetchone()
            if cadet is None:
                raise InventoryError("Saved cadet record not found.")

            connection.execute(
                "UPDATE transactions SET cadet_id = NULL WHERE cadet_id = ?",
                (cadet_id,),
            )
            connection.execute(
                "DELETE FROM cadets WHERE cadet_id = ?",
                (cadet_id,),
            )
            connection.commit()

        self.database.note_write()

    def checkout_item(
        self,
        *,
        barcode_id: str,
        cadet_name: str,
        cadet_email: str,
        quantity: int,
        approved_by: dict[str, Any] | None = None,
        condition_notes: str = "",
    ) -> None:
        barcode = barcode_id.strip().upper()
        quantity = self._validate_quantity(quantity)
        cadet_name, cadet_email = self._validate_cadet_identity(cadet_name, cadet_email)
        approval = self._normalize_admin_identity(approved_by)

        with self.database.connect() as connection:
            barcode = self._resolve_barcode_alias(connection, barcode)
            item = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?",
                (barcode,),
            ).fetchone()
            if item is None:
                raise InventoryError("Barcode not found in inventory.")
            if item["status"] in {"Retired", "Lost"}:
                raise InventoryError(f"{item['status']} items cannot be checked out.")
            if item["available_quantity"] < quantity:
                raise InventoryError("Checkout would drive inventory negative. Reduce the quantity or restock first.")

            cadet = self._upsert_cadet(connection, cadet_name, cadet_email)
            for _ in range(quantity):
                connection.execute(
                    """
                    INSERT INTO transactions(
                        barcode_id, cadet_id, cadet_name, cadet_email, checkout_time,
                        approved_by_admin_id, approved_by_name, approved_by_role, approved_at, condition_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        barcode,
                        cadet["cadet_id"],
                        cadet_name,
                        cadet_email,
                        utc_now(),
                        approval["admin_id"],
                        approval["approved_by_name"],
                        approval["approved_by_role"],
                        utc_now(),
                        condition_notes.strip(),
                    ),
                )

            self._sync_item_state(connection, barcode)
            connection.commit()

        self.database.note_write()

    def checkout_items_bulk(
        self,
        *,
        line_items: list[dict[str, Any]],
        cadet_name: str,
        cadet_email: str,
        approved_by: dict[str, Any] | None = None,
        condition_notes: str = "",
        loan_due_date: str = "",
        loan_purpose: str = "",
    ) -> list[dict[str, Any]]:
        if not line_items:
            raise InventoryError("Add at least one barcode to the checkout list first.")

        normalized_name, normalized_email = self._validate_cadet_identity(cadet_name, cadet_email)
        approval = self._normalize_admin_identity(approved_by)
        if loan_due_date:
            loan_due_date = self.validate_loan_date(loan_due_date, earliest=date.today())
        processed_items: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            cadet = self._upsert_cadet(connection, normalized_name, normalized_email)
            for line in line_items:
                barcode = str(line.get("barcode_id", "")).strip().upper()
                barcode = self._resolve_barcode_alias(connection, barcode)
                quantity = self._validate_quantity(line.get("quantity", 1))
                item = connection.execute("SELECT * FROM items WHERE barcode_id = ?", (barcode,)).fetchone()
                if item is None:
                    raise InventoryError(f"Barcode {barcode} was not found in inventory.")
                if item["status"] in {"Retired", "Lost"}:
                    raise InventoryError(f"{item['status']} items cannot be checked out.")
                if item["available_quantity"] < quantity:
                    raise InventoryError(
                        f"Checkout would drive inventory negative for {barcode}. Reduce the quantity or restock first."
                    )

                for _ in range(quantity):
                    cursor = connection.execute(
                        """
                        INSERT INTO transactions(
                            barcode_id, cadet_id, cadet_name, cadet_email, checkout_time,
                            approved_by_admin_id, approved_by_name, approved_by_role, approved_at, condition_notes
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            barcode,
                            cadet["cadet_id"],
                            normalized_name,
                            normalized_email,
                            utc_now(),
                            approval["admin_id"],
                            approval["approved_by_name"],
                            approval["approved_by_role"],
                            utc_now(),
                            condition_notes.strip(),
                        ),
                    )
                    if loan_due_date:
                        connection.execute(
                            'UPDATE transactions SET loan_due_date=?, loan_purpose=? WHERE transaction_id=?',
                            (loan_due_date, loan_purpose.strip(), cursor.lastrowid),
                        )
                        self._loan_event(connection, cursor.lastrowid, 'Loan issued',
                                         f'Due {loan_due_date}; {loan_purpose.strip()}', approval['label'])
                self._sync_item_state(connection, barcode)
                processed_items.append(
                    {
                        "barcode_id": barcode,
                        "item_name": item["item_name"],
                        "quantity": quantity,
                    }
                )
            connection.commit()

        self.database.note_write()
        return processed_items

    def return_item(
        self,
        *,
        barcode_id: str,
        quantity: int,
        approved_by: dict[str, Any] | None = None,
        condition_notes: str = "",
    ) -> list[dict[str, Any]]:
        barcode = barcode_id.strip().upper()
        quantity = self._validate_quantity(quantity)
        approval = self._normalize_admin_identity(approved_by)

        with self.database.connect() as connection:
            barcode = self._resolve_barcode_alias(connection, barcode)
            item = connection.execute(
                "SELECT * FROM items WHERE barcode_id = ?",
                (barcode,),
            ).fetchone()
            if item is None:
                raise InventoryError("Barcode not found in inventory.")

            open_transactions = connection.execute(
                """
                SELECT transaction_id, cadet_name, cadet_email, checkout_time, condition_notes
                FROM transactions
                WHERE barcode_id = ? AND return_time IS NULL
                ORDER BY checkout_time
                LIMIT ?
                """,
                (barcode, quantity),
            ).fetchall()
            if len(open_transactions) < quantity:
                raise InventoryError("There are not enough checked-out units to return that quantity.")

            returned_rows: list[dict[str, Any]] = []
            for row in open_transactions:
                connection.execute(
                    """
                    UPDATE transactions
                    SET return_time = ?, return_approved_by_admin_id = ?, return_approved_by_name = ?,
                        return_approved_by_role = ?, return_approved_at = ?, disposition = 'Returned',
                        condition_notes = ?
                    WHERE transaction_id = ?
                    """,
                    (
                        utc_now(),
                        approval["admin_id"],
                        approval["approved_by_name"],
                        approval["approved_by_role"],
                        utc_now(),
                        self._append_note(row["condition_notes"], condition_notes),
                        row["transaction_id"],
                    ),
                )
                returned_rows.append(dict(row))

            self._sync_item_state(connection, barcode)
            connection.commit()

        self.database.note_write()
        return returned_rows

    def return_items_bulk(
        self,
        *,
        line_items: list[dict[str, Any]],
        approved_by: dict[str, Any] | None = None,
        condition_notes: str = "",
    ) -> list[dict[str, Any]]:
        if not line_items:
            raise InventoryError("Add at least one barcode to the return list first.")

        approval = self._normalize_admin_identity(approved_by)
        returned_rows: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            for line in line_items:
                barcode = str(line.get("barcode_id", "")).strip().upper()
                barcode = self._resolve_barcode_alias(connection, barcode)
                quantity = self._validate_quantity(line.get("quantity", 1))
                item = connection.execute("SELECT * FROM items WHERE barcode_id = ?", (barcode,)).fetchone()
                if item is None:
                    raise InventoryError(f"Barcode {barcode} was not found in inventory.")

                open_transactions = connection.execute(
                    """
                    SELECT transaction_id, cadet_name, cadet_email, checkout_time, condition_notes
                    FROM transactions
                    WHERE barcode_id = ? AND return_time IS NULL
                    ORDER BY checkout_time
                    LIMIT ?
                    """,
                    (barcode, quantity),
                ).fetchall()
                if len(open_transactions) < quantity:
                    raise InventoryError(f"There are not enough checked-out units to return for {barcode}.")

                for row in open_transactions:
                    connection.execute(
                        """
                        UPDATE transactions
                        SET return_time = ?, return_approved_by_admin_id = ?, return_approved_by_name = ?,
                            return_approved_by_role = ?, return_approved_at = ?, disposition = 'Returned',
                            condition_notes = ?
                        WHERE transaction_id = ?
                        """,
                        (
                            utc_now(),
                            approval["admin_id"],
                            approval["approved_by_name"],
                            approval["approved_by_role"],
                            utc_now(),
                            self._append_note(row["condition_notes"], condition_notes),
                            row["transaction_id"],
                        ),
                    )
                    returned_rows.append(
                        {
                            "barcode_id": barcode,
                            "cadet_name": row["cadet_name"],
                            "cadet_email": row["cadet_email"],
                            "checkout_time": row["checkout_time"],
                        }
                    )
                self._sync_item_state(connection, barcode)
            connection.commit()

        self.database.note_write()
        return returned_rows

    def get_report(
        self,
        report_name: str,
        *,
        start_date: str = "",
        end_date: str = "",
    ) -> tuple[list[str], list[dict[str, Any]]]:
        start_day = self._parse_report_date(start_date, field_name="Start date")
        end_day = self._parse_report_date(end_date, field_name="End date")
        if start_day is not None and end_day is not None and end_day < start_day:
            raise InventoryError("End date cannot be before start date.")

        if report_name == "Checked Out Items":
            columns, rows = self._checked_out_report()
            date_fields = ("checkout_time",)
        elif report_name == "Acquired / Purchased Items":
            columns, rows = self._acquired_items_report()
            date_fields = ("acquired_time",)
        elif report_name == "Inventory Changes":
            columns, rows = self._inventory_changes_report()
            date_fields = ("event_time",)
        else:
            columns, rows = self._transaction_history_report()
            date_fields = ("checkout_time", "closed_time")
        if start_day is None and end_day is None:
            return columns, rows
        return columns, [
            row
            for row in rows
            if self._report_row_matches_date_range(
                row,
                date_fields=date_fields,
                start_day=start_day,
                end_day=end_day,
            )
        ]

    @staticmethod
    def _parse_report_date(value: str, *, field_name: str) -> date | None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned)
        except ValueError as exc:
            raise InventoryError(f"{field_name} must use YYYY-MM-DD format.") from exc

    def _report_row_matches_date_range(
        self,
        row: dict[str, Any],
        *,
        date_fields: tuple[str, ...],
        start_day: date | None,
        end_day: date | None,
    ) -> bool:
        for field in date_fields:
            parsed = self._parse_export_timestamp(row.get(field))
            if parsed is None:
                continue
            event_day = parsed.astimezone().date() if parsed.tzinfo is not None else parsed.date()
            if start_day is not None and event_day < start_day:
                continue
            if end_day is not None and event_day > end_day:
                continue
            return True
        return False

    @staticmethod
    def report_column_label(column: str) -> str:
        return REPORT_COLUMN_LABELS.get(column, column.replace("_", " ").title())

    def format_report_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted_rows: list[dict[str, Any]] = []
        for row in rows:
            formatted: dict[str, Any] = {}
            for column, value in row.items():
                if column in REPORT_TIMESTAMP_FIELDS:
                    parsed = self._parse_export_timestamp(value)
                    if parsed is None:
                        formatted[column] = ""
                    else:
                        local_value = parsed.astimezone() if parsed.tzinfo is not None else parsed
                        formatted[column] = local_value.strftime("%b %d, %Y %I:%M %p").replace(
                            " 0", " "
                        )
                elif column == "quantity_change" and value not in (None, ""):
                    numeric_value = int(value)
                    formatted[column] = f"{numeric_value:+d}" if numeric_value else "0"
                else:
                    formatted[column] = value
            formatted_rows.append(formatted)
        return formatted_rows

    def summarize_report(self, report_name: str, rows: list[dict[str, Any]]) -> str:
        if report_name == "Inventory Changes":
            units_added = sum(max(0, int(row.get("quantity_change") or 0)) for row in rows)
            units_removed = sum(max(0, -int(row.get("quantity_change") or 0)) for row in rows)
            item_count = len({str(row.get("barcode_id") or "") for row in rows})
            return (
                f"{len(rows)} recorded change(s) across {item_count} item(s): "
                f"{units_added} unit(s) added and {units_removed} unit(s) removed."
            )
        if report_name == "Checked Out Items":
            cadet_count = len({str(row.get("cadet_email") or "") for row in rows})
            return f"{len(rows)} unit(s) currently checked out to {cadet_count} cadet(s)."
        if report_name == "Acquired / Purchased Items":
            cadet_count = len({str(row.get("cadet_email") or "") for row in rows})
            return f"{len(rows)} permanently issued or purchased unit(s) for {cadet_count} cadet(s)."
        status_counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("disposition") or "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        breakdown = ", ".join(
            f"{status}: {count}" for status, count in sorted(status_counts.items())
        )
        return f"{len(rows)} transaction event(s)" + (f" ({breakdown})." if breakdown else ".")

    def export_rows_to_csv(self, path: Path, columns: list[str], rows: list[dict[str, Any]]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        readable_columns = [self.report_column_label(column) for column in columns]
        formatted_rows = self.format_report_rows(rows)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=readable_columns)
            writer.writeheader()
            for formatted in formatted_rows:
                writer.writerow(
                    {
                        self.report_column_label(column): formatted.get(column, "")
                        for column in columns
                    }
                )
        return path

    def export_report_spreadsheet(
        self,
        path: Path,
        *,
        report_name: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        start_date: str = "",
        end_date: str = "",
    ) -> Path:
        readable_columns = [self.report_column_label(column) for column in columns]
        formatted_rows = self.format_report_rows(rows)
        readable_rows = [
            {
                self.report_column_label(column): row.get(column, "")
                for column in columns
            }
            for row in formatted_rows
        ]
        start_label = start_date.strip() or "Earliest recorded date"
        end_label = end_date.strip() or date.today().isoformat()
        period_label = f"{start_label} through {end_label}. Generated {date.today().isoformat()}"
        cadets = {
            str(row.get("cadet_email") or row.get("cadet_name") or "").strip().casefold()
            for row in rows
            if str(row.get("cadet_email") or row.get("cadet_name") or "").strip()
        }
        items = {
            str(row.get("barcode_id") or "").strip().upper()
            for row in rows
            if str(row.get("barcode_id") or "").strip()
        }
        units_added = sum(max(0, int(row.get("quantity_change") or 0)) for row in rows)
        units_removed = sum(max(0, -int(row.get("quantity_change") or 0)) for row in rows)
        permanent = sum(
            str(row.get("disposition") or "") in ACQUISITION_DISPOSITIONS for row in rows
        )
        current_loans = self.list_loans()
        date_fields = ("event_time", "checkout_time", "acquired_time", "closed_time")
        daily: dict[str, dict[str, Any]] = {}
        for row in rows:
            parsed = next(
                (self._parse_export_timestamp(row.get(field)) for field in date_fields if self._parse_export_timestamp(row.get(field)) is not None),
                None,
            )
            if parsed is None:
                continue
            key = parsed.date().isoformat()
            entry = daily.setdefault(key, {"Date": key, "Records": 0, "Units Added": 0, "Units Removed": 0})
            entry["Records"] += 1
            change = int(row.get("quantity_change") or 0)
            entry["Units Added"] += max(0, change)
            entry["Units Removed"] += max(0, -change)
        daily_rows = [daily[key] for key in sorted(daily)][-14:]
        summary_text = self.summarize_report(report_name, rows)
        summary = {
            "metrics": [
                ("Records", len(rows)), ("Cadets", len(cadets)),
                ("Inventory items", len(items)), ("Current loans", len(current_loans)),
                ("Units added", units_added), ("Units removed", units_removed),
                ("Permanent issues", permanent), ("Overdue loans", sum(bool(row["overdue"]) for row in current_loans)),
            ],
            "bluf": summary_text,
            "daily_columns": ["Date", "Records", "Units Added", "Units Removed"],
            "daily_rows": daily_rows,
            "daily_totals": {
                "Records": sum(row["Records"] for row in daily_rows),
                "Units Added": sum(row["Units Added"] for row in daily_rows),
                "Units Removed": sum(row["Units Removed"] for row in daily_rows),
            },
            "major_activities": (
                f"1. Generated the {report_name} report for {start_label} through {end_label}.\n"
                f"2. Included {len(rows)} records across {len(items)} inventory items and {len(cadets)} cadets.\n"
                f"3. Current loan accountability includes {len(current_loans)} outstanding units."
            ),
            "coa_validation": (
                "Review the detail sheet against source records. Reconcile open items and temporary loans "
                "with physical returns before making inventory corrections."
            ),
            "source_note": "Source: live A.C.E. inventory database. Counts reflect recorded data.",
        }
        return write_report_workbook(
            path,
            title=f"{self.settings.org_name} {report_name} Report",
            subtitle=period_label,
            org_line="Resource Management Flight, Detachment 005",
            summary=summary,
            detail_sheets=[{"sheet_name": report_name, "columns": readable_columns, "rows": readable_rows}],
        )

    def get_weekly_activity_report_data(
        self,
        *,
        start_date: str = "",
        end_date: str = "",
        bluf: str = "",
        major_activities: str = "",
        coa_validation: str = "",
    ) -> dict[str, Any]:
        """Build one consolidated, read-only weekly activity report."""
        report_end = self._parse_report_date(end_date, field_name="End date") or date.today()
        report_start = self._parse_report_date(start_date, field_name="Start date")
        if report_start is None:
            report_start = report_end - timedelta(days=6)
        if report_end < report_start:
            raise InventoryError("End date cannot be before start date.")

        with self.database.connect() as connection:
            uncounted_baseline={row[0] for row in connection.execute('''SELECT DISTINCT a.barcode_id FROM inventory_changes a
                WHERE a.action='Catalog Baseline Created' AND NOT EXISTS(
                    SELECT 1 FROM inventory_count_state s WHERE s.barcode_id=a.barcode_id)''')}

        with self.database.connect() as connection:
            change_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        change_id, event_time, action, barcode_id, wings_item_no,
                        item_name, category, variant, item_type, quantity_change,
                        total_before, total_after, available_before, available_after,
                        details, source
                    FROM inventory_changes
                    ORDER BY event_time, change_id
                    """
                ).fetchall()
            ]
            item_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        items.barcode_id, items.wings_item_no, items.item_name,
                        items.category, items.variant, items.item_type,
                        items.total_quantity, items.available_quantity, items.status,
                        items.created_at, items.updated_at,
                        COALESCE(catalog.is_wings, 0) AS is_wings
                    FROM items
                    LEFT JOIN wings_catalog AS catalog
                        ON catalog.item_no = items.wings_item_no
                    ORDER BY items.created_at, items.barcode_id
                    """
                ).fetchall()
            ]
            transaction_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        transactions.transaction_id, transactions.barcode_id,
                        items.wings_item_no, items.item_name, items.category,
                        items.variant, items.item_type, transactions.cadet_id,
                        transactions.cadet_name, transactions.cadet_email,
                        transactions.approved_by_name, transactions.approved_by_role,
                        transactions.checkout_time,
                        CASE
                            WHEN transactions.return_time IS NULL THEN 'Checked Out'
                            WHEN trim(transactions.disposition) <> '' THEN transactions.disposition
                            ELSE 'Returned'
                        END AS disposition,
                        transactions.return_time AS closed_time,
                        transactions.return_approved_by_name AS closed_by_name,
                        transactions.return_approved_by_role AS closed_by_role,
                        transactions.condition_notes,
                        transactions.loan_due_date,
                        transactions.loan_purpose
                    FROM transactions
                    LEFT JOIN items ON items.barcode_id = transactions.barcode_id
                    ORDER BY transactions.checkout_time, transactions.transaction_id
                    """
                ).fetchall()
            ]
            fitting_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        entries.size_entry_id, entries.cadet_id, cadets.full_name,
                        cadets.email, entries.category AS source_category,
                        entries.size_label, entries.size_value,
                        entries.catalog_item_no, entries.notes,
                        entries.created_at, entries.updated_at
                    FROM cadet_size_entries AS entries
                    JOIN cadets ON cadets.cadet_id = entries.cadet_id
                    ORDER BY entries.updated_at, entries.size_entry_id
                    """
                ).fetchall()
            ]
            cadet_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT cadet_id, full_name, email, created_at, updated_at
                    FROM cadets
                    ORDER BY created_at, cadet_id
                    """
                ).fetchall()
            ]

        def in_range(row: dict[str, Any], *date_fields: str) -> bool:
            return self._report_row_matches_date_range(
                row,
                date_fields=tuple(date_fields),
                start_day=report_start,
                end_day=report_end,
            )

        filtered_changes: list[dict[str, Any]] = []
        repair_change_count = 0
        routine_units_added = 0
        recovered_units = 0
        units_removed = 0
        net_units_recorded = 0
        inferred_wings_barcodes: set[str] = set()
        for raw_row in change_rows:
            if not in_range(raw_row, "event_time"):
                continue
            if self._is_easter_egg_barcode(str(raw_row.get("barcode_id") or "")):
                continue
            row = dict(raw_row)
            action = str(row.get("action") or "")
            if action == 'Catalog Baseline Created':continue
            details = str(row.get("details") or "")
            lowered = f"{action} {details}".casefold()
            quantity_change = int(row.get("quantity_change") or 0)
            is_repair = "duplicate" in lowered or "alias" in lowered or "consolidat" in lowered
            if is_repair:
                activity_class = "Barcode / Mapping Repair"
                repair_change_count += 1
            elif quantity_change < 0:
                activity_class = "Inventory Removal"
                units_removed += -quantity_change
                net_units_recorded += quantity_change
            elif action in {"New Item Added", "Quantity Added"}:
                activity_class = "Routine Inventory Add"
                routine_units_added += quantity_change
                net_units_recorded += quantity_change
            elif quantity_change > 0 and ("recover" in lowered or action == "Acquisition Undone"):
                activity_class = "Recovered Inventory Add"
                recovered_units += quantity_change
                net_units_recorded += quantity_change
            elif quantity_change > 0:
                activity_class = "Other Inventory Add"
                routine_units_added += quantity_change
                net_units_recorded += quantity_change
            else:
                activity_class = "Record Update"
            if "inferred" in lowered and str(row.get("wings_item_no") or "").strip():
                inferred_wings_barcodes.add(str(row.get("barcode_id") or "").strip().upper())
            row["activity_class"] = activity_class
            filtered_changes.append(row)

        filtered_items: list[dict[str, Any]] = []
        for raw_row in item_rows:
            if not in_range(raw_row, "created_at"):
                continue
            if self._is_easter_egg_barcode(str(raw_row.get("barcode_id") or "")):
                continue
            row = dict(raw_row)
            barcode_id = str(row.get("barcode_id") or "").strip().upper()
            if barcode_id in uncounted_baseline:continue
            if int(row.pop("is_wings") or 0):
                if barcode_id in inferred_wings_barcodes:
                    row["id_status"] = "Official WINGS ID - verify"
                    row["validation_note"] = "Numeric catalog match was inferred; validate in WINGS."
                else:
                    row["id_status"] = "Official WINGS ID"
                    row["validation_note"] = "Matched to the official WINGS catalog."
            else:
                row["id_status"] = "Local A.C.E. ID"
                row["validation_note"] = "Validate against WINGS before using this row for an official import."
            filtered_items.append(row)

        filtered_transactions: list[dict[str, Any]] = []
        checkout_count = 0
        closed_count = 0
        checkout_cadets: set[str] = set()
        for raw_row in transaction_rows:
            if self._is_easter_egg_barcode(str(raw_row.get("barcode_id") or "")):
                continue
            checkout_in_range = in_range(raw_row, "checkout_time")
            closed_in_range = in_range(raw_row, "closed_time")
            if not checkout_in_range and not closed_in_range:
                continue
            row = dict(raw_row)
            if checkout_in_range and closed_in_range:
                row["weekly_event"] = "Checked Out and Closed"
            elif checkout_in_range:
                row["weekly_event"] = "Checked Out"
            else:
                row["weekly_event"] = "Closed / Returned"
            if checkout_in_range:
                checkout_count += 1
                cadet_key = str(row.get("cadet_id") or "").strip()
                if not cadet_key:
                    cadet_key = str(row.get("cadet_email") or "").strip().casefold()
                if cadet_key:
                    checkout_cadets.add(cadet_key)
            if closed_in_range:
                closed_count += 1
            filtered_transactions.append(row)

        filtered_fittings: list[dict[str, Any]] = []
        fitted_cadets: set[str] = set()
        for raw_row in fitting_rows:
            if not in_range(raw_row, "updated_at"):
                continue
            row = dict(raw_row)
            source_category = str(row.get("source_category") or "").strip()
            size_label = str(row.get("size_label") or "").strip()
            if size_label.casefold() == "blues service coat":
                row["report_category"] = "Blues Service Coats"
            else:
                row["report_category"] = source_category or "Measurements"
            filtered_fittings.append(row)
            fitted_cadets.add(str(row.get("cadet_id") or row.get("email") or ""))

        filtered_cadets = [row for row in cadet_rows if in_range(row, "created_at")]
        identifier_audit = self.inventory_item_number_audit()
        inventory_rows_with_ids = identifier_audit["total_rows"] - identifier_audit["missing_rows"]
        report_period = f"{report_start.isoformat()} through {report_end.isoformat()}"
        generated_text = datetime.now().strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")

        current_loans = self.list_loans()
        permanent_issues = sum(
            row.get("disposition") in ACQUISITION_DISPOSITIONS
            and in_range(row, "checkout_time")
            for row in filtered_transactions
        )
        overdue_loans = sum(bool(row["overdue"]) for row in current_loans)
        daily_rows = []
        current_day = report_start
        while current_day <= report_end:
            day_key = current_day.isoformat()
            day_changes = [row for row in filtered_changes if str(row.get("event_time") or "")[:10] == day_key]
            day_changes = [row for row in day_changes if row.get('activity_class') != 'Barcode / Mapping Repair']
            daily_rows.append(
                {
                    "Date": day_key,
                    "Units Added": sum(max(0, int(row.get("quantity_change") or 0)) for row in day_changes),
                    "Units Removed": sum(max(0, -int(row.get("quantity_change") or 0)) for row in day_changes),
                    "Net Units": sum(int(row.get("quantity_change") or 0) for row in day_changes),
                    "Checkouts": sum(str(row.get("checkout_time") or "")[:10] == day_key for row in filtered_transactions),
                    "Returns": sum(str(row.get("closed_time") or "")[:10] == day_key for row in filtered_transactions),
                    "Fittings": sum(str(row.get("updated_at") or "")[:10] == day_key for row in filtered_fittings),
                }
            )
            current_day += timedelta(days=1)
        default_bluf = (
            f"During {report_period}, A.C.E. recorded {routine_units_added + recovered_units} units added "
            f"and {units_removed} units removed, a net change of {net_units_recorded}. "
            f"There were {checkout_count} checkout transactions across {len(checkout_cadets)} cadets, "
            f"including {permanent_issues} permanent issues. Current temporary loans include "
            f"{len(current_loans)} items, with {overdue_loans} overdue."
        )
        default_activities = (
            f"1. Recorded {len(filtered_changes)} inventory change events and created {len(filtered_items)} catalog rows.\n"
            f"2. Processed {checkout_count} checkouts and {closed_count} returns or acquisitions.\n"
            f"3. Added or updated {len(filtered_fittings)} fitting records and created {len(filtered_cadets)} cadet profiles.\n"
            f"4. Current item-number coverage is {inventory_rows_with_ids} of {identifier_audit['total_rows']} inventory rows."
        )
        default_coa = (
            "Reconcile outstanding loans against physical returns. Follow up on overdue entries and upcoming "
            "deadlines. Validate local A.C.E. identifiers against official WINGS records when available."
        )
        resolved_bluf = bluf.strip() or default_bluf
        resolved_activities = major_activities.strip() or default_activities
        resolved_coa = coa_validation.strip() or default_coa

        summary_rows = [
            {"Report Section": "BLUF", "Value": resolved_bluf},
            {"Report Section": "MAs", "Value": resolved_activities},
            {"Report Section": "COA / Validation", "Value": resolved_coa},
            {"Report Section": "Report Period", "Value": report_period},
            {"Report Section": "Generated", "Value": generated_text},
            {"Report Section": "Routine Units Added", "Value": routine_units_added},
            {"Report Section": "Recovered Units Added", "Value": recovered_units},
            {"Report Section": "Units Removed", "Value": units_removed},
            {"Report Section": "Net Units Recorded", "Value": net_units_recorded},
            {"Report Section": "New Catalog Rows", "Value": len(filtered_items)},
            {"Report Section": "Checkout Transactions", "Value": checkout_count},
            {"Report Section": "Cadets With Checkouts", "Value": len(checkout_cadets)},
            {"Report Section": "Returns / Acquisitions Closed", "Value": closed_count},
            {"Report Section": "Fitting Entries Recorded or Updated", "Value": len(filtered_fittings)},
            {"Report Section": "Cadets Fitted", "Value": len(fitted_cadets)},
            {"Report Section": "New Cadet Records", "Value": len(filtered_cadets)},
            {"Report Section": "Barcode / Mapping Repairs", "Value": repair_change_count},
            {"Report Section": "Live Inventory Rows", "Value": identifier_audit["total_rows"]},
            {"Report Section": "Rows With Item Numbers", "Value": inventory_rows_with_ids},
            {"Report Section": "Official WINGS IDs", "Value": identifier_audit["official_rows"]},
            {"Report Section": "Local A.C.E. IDs", "Value": identifier_audit["local_rows"]},
        ]

        quality_rows = [
            {
                "Check": "Inventory item-number coverage",
                "Value": f"{inventory_rows_with_ids} of {identifier_audit['total_rows']}",
                "Status": "Complete" if identifier_audit["missing_rows"] == 0 else "Needs Attention",
                "Details": "Every live inventory row should have an official WINGS ID or an explicit local A.C.E. ID.",
            },
            {
                "Check": "Official WINGS mappings",
                "Value": identifier_audit["official_rows"],
                "Status": "Recorded",
                "Details": "Rows currently matched to the bundled official WINGS catalog.",
            },
            {
                "Check": "Local A.C.E. mappings",
                "Value": identifier_audit["local_rows"],
                "Status": "Validate in WINGS" if identifier_audit["local_rows"] else "None",
                "Details": "Local identifiers preserve accountability but are not official WINGS item numbers.",
            },
            {
                "Check": "Weekly inferred WINGS mappings",
                "Value": len(inferred_wings_barcodes),
                "Status": "Validate in WINGS" if inferred_wings_barcodes else "None",
                "Details": "Numeric matches marked as inferred in the audit trail during this report period.",
            },
        ]

        def readable_sheet(
            sheet_name: str,
            columns: list[str],
            rows: list[dict[str, Any]],
        ) -> dict[str, Any]:
            formatted_rows = self.format_report_rows(rows)
            readable_columns = [self.report_column_label(column) for column in columns]
            return {
                "sheet_name": sheet_name,
                "columns": readable_columns,
                "rows": [
                    {
                        self.report_column_label(column): row.get(column, "")
                        for column in columns
                    }
                    for row in formatted_rows
                ],
            }

        sheets = [
            {
                "sheet_name": "Executive Summary",
                "columns": ["Report Section", "Value"],
                "rows": summary_rows,
            },
            readable_sheet(
                "Catalog Activity",
                [
                    "event_time", "activity_class", "action", "item_name", "variant",
                    "quantity_change", "total_before", "total_after", "available_after",
                    "barcode_id", "wings_item_no", "category", "details", "source",
                ],
                filtered_changes,
            ),
            readable_sheet(
                "New Catalog Items",
                [
                    "created_at", "barcode_id", "wings_item_no", "id_status", "item_name",
                    "category", "variant", "item_type", "total_quantity",
                    "available_quantity", "status", "validation_note",
                ],
                filtered_items,
            ),
            readable_sheet(
                "Checkouts",
                [
                    "weekly_event", "transaction_id", "checkout_time", "closed_time",
                    "disposition", "cadet_name", "cadet_email", "barcode_id",
                    "wings_item_no", "item_name", "variant", "approved_by_name",
                    "closed_by_name", "loan_due_date", "loan_purpose", "condition_notes",
                ],
                filtered_transactions,
            ),
            readable_sheet(
                "Fittings",
                [
                    "updated_at", "cadet_id", "full_name", "email", "report_category",
                    "source_category", "size_label", "size_value", "catalog_item_no", "notes",
                ],
                filtered_fittings,
            ),
            readable_sheet(
                "Cadet Records",
                ["created_at", "cadet_id", "full_name", "email", "updated_at"],
                filtered_cadets,
            ),
            readable_sheet(
                "Current Loans",
                [
                    "loan_status", "loan_due_date", "loan_purpose", "cadet_name",
                    "cadet_email", "item_name", "variant", "barcode_id",
                    "wings_item_no", "checkout_time", "approved_by_name",
                ],
                current_loans,
            ),
            {
                "sheet_name": "Data Quality",
                "columns": ["Check", "Value", "Status", "Details"],
                "rows": quality_rows,
            },
        ]
        current_inventory = enrich_items(self, item_rows)
        sheets.extend(inventory_analysis(current_inventory))
        sheets.append(readable_sheet('Current Inventory', [
            'barcode_id','wings_item_no','item_name','category','variant','item_type',
            'family','season','tags','status','total_quantity','available_quantity','count_status','counted_at'],
            [{**row, 'tags': ', '.join(row['tags'])} for row in current_inventory]))
        return {
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
            "summary": {
                "routine_units_added": routine_units_added,
                "recovered_units": recovered_units,
                "units_removed": units_removed,
                "net_units_recorded": net_units_recorded,
                "new_catalog_rows": len(filtered_items),
                "checkout_transactions": checkout_count,
                "checkout_cadets": len(checkout_cadets),
                "closed_transactions": closed_count,
                "fitting_entries": len(filtered_fittings),
                "cadets_fitted": len(fitted_cadets),
                "new_cadets": len(filtered_cadets),
                "barcode_repairs": repair_change_count,
                "permanent_issues": permanent_issues,
                "current_loans": len(current_loans),
                "overdue_loans": overdue_loans,
            },
            "presentation": {
                "metrics": [
                    ("Units added", routine_units_added + recovered_units),
                    ("Units removed", units_removed),
                    ("Net units", net_units_recorded),
                    ("New catalog rows", len(filtered_items)),
                    ("Checkouts", checkout_count),
                    ("Cadets checked out", len(checkout_cadets)),
                    ("Current loans", len(current_loans)),
                    ("Overdue loans", overdue_loans),
                ],
                "bluf": resolved_bluf,
                "major_activities": resolved_activities,
                "coa_validation": resolved_coa,
                "daily_columns": ["Date", "Units Added", "Units Removed", "Net Units", "Checkouts", "Returns", "Fittings"],
                "daily_rows": daily_rows,
                "daily_totals": {
                    "Units Added": sum(row["Units Added"] for row in daily_rows),
                    "Units Removed": sum(row["Units Removed"] for row in daily_rows),
                    "Net Units": sum(row["Net Units"] for row in daily_rows),
                    "Checkouts": sum(row["Checkouts"] for row in daily_rows),
                    "Returns": sum(row["Returns"] for row in daily_rows),
                    "Fittings": sum(row["Fittings"] for row in daily_rows),
                },
                "source_note": "Source: live A.C.E. inventory database. Counts reflect recorded data.",
            },
            "sheets": sheets,
        }

    def export_activity_html(
        self, *, start_date="", end_date="", bluf="", major_activities="",
        open_after=True, filename_stem="",
    ) -> Path:
        from .report_html import write_activity_html
        report = self.get_weekly_activity_report_data(
            start_date=start_date, end_date=end_date, bluf=bluf,
            major_activities=major_activities,
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = Path(filename_stem).name if filename_stem.strip() else f"ACE_activity_report_{report['start_date']}_to_{report['end_date']}"
        export_path = self.settings.database_path.parent / "exports" / f"{stem}_{timestamp}.html"
        write_activity_html(export_path, report)
        if open_after:
            open_file(export_path)
        return export_path

    def export_weekly_activity_spreadsheet(
        self,
        *,
        start_date: str = "",
        end_date: str = "",
        bluf: str = "",
        major_activities: str = "",
        coa_validation: str = "",
        open_after: bool = True,
        filename_stem: str = "",
    ) -> Path:
        report = self.get_weekly_activity_report_data(
            start_date=start_date,
            end_date=end_date,
            bluf=bluf,
            major_activities=major_activities,
            coa_validation=coa_validation,
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.settings.database_path.parent / "exports"
        export_path = export_dir / (
            f"{filename_stem.strip()}_{timestamp}.xlsx"
            if filename_stem.strip()
            else f"ACE_activity_report_{report['start_date']}_to_{report['end_date']}_{timestamp}.xlsx"
        )
        write_report_workbook(
            export_path,
            title=f"{self.settings.org_name} Inventory Activity Report",
            subtitle=(
                f"{report['start_date']} through {report['end_date']}. "
                f"Generated {date.today().isoformat()}"
            ),
            org_line="Resource Management Flight, Detachment 005",
            summary=report["presentation"],
            detail_sheets=report["sheets"][1:],
        )
        if open_after:
            open_file(export_path)
        return export_path

    def export_inventory_spreadsheet(self, *, open_after: bool = True) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.settings.database_path.parent / "exports"
        export_path = export_dir / f"WINGS_inventory_{timestamp}.xlsx"
        rows = self.list_wings_export_rows()
        self._write_simple_xlsx(
            export_path,
            sheet_name="WINGs Inventory",
            columns=list(WINGS_COLUMNS),
            rows=rows,
        )
        if open_after:
            open_file(export_path)
        return export_path

    def export_complete_inventory_spreadsheet(self, *, open_after: bool = True) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.settings.database_path.parent / "exports"
        export_path = export_dir / f"ACE_complete_inventory_{timestamp}.xlsx"
        rows = self.list_complete_inventory_export_rows()
        self._write_simple_xlsx(
            export_path,
            sheet_name="A.C.E. Complete Inventory",
            columns=list(WINGS_COLUMNS),
            rows=rows,
        )
        if open_after:
            open_file(export_path)
        return export_path

    def list_wings_export_rows(self) -> list[dict[str, Any]]:
        return self._list_inventory_export_rows(official_only=True)

    def list_complete_inventory_export_rows(self) -> list[dict[str, Any]]:
        return self._list_inventory_export_rows(official_only=False)

    def _list_inventory_export_rows(self, *, official_only: bool) -> list[dict[str, Any]]:
        official_filter = "WHERE catalog.is_wings = 1" if official_only else ""
        with self.database.connect() as connection:
            catalog_rows = connection.execute(
                f"""
                SELECT
                    catalog.item_no,
                    catalog.item_name,
                    catalog.size,
                    catalog.category,
                    catalog.subcategory,
                    catalog.sex,
                    catalog.stock_number,
                    catalog.uom,
                    catalog.writeoffs,
                    catalog.source,
                    catalog.is_wings,
                    COALESCE(SUM(items.total_quantity), 0) AS total_quantity,
                    COALESCE(SUM(items.available_quantity), 0) AS available_quantity
                FROM wings_catalog AS catalog
                LEFT JOIN items ON items.wings_item_no = catalog.item_no
                {official_filter}
                GROUP BY catalog.item_no
                HAVING COALESCE(SUM(items.total_quantity), 0) > 0
                ORDER BY
                    catalog.is_wings DESC,
                    CASE WHEN catalog.is_wings = 1 THEN CAST(catalog.item_no AS INTEGER) END,
                    catalog.item_no
                """
            ).fetchall()
        return [
            {
                "Item No": (
                    self._format_wings_item_no(row["item_no"])
                    if int(row["is_wings"]) == 1
                    else str(row["item_no"])
                ),
                "Qty Issued": int(row["total_quantity"]) - int(row["available_quantity"]),
                "Qty Available": int(row["available_quantity"]),
                "Total in Inventory": int(row["total_quantity"]),
                "Item Name": row["item_name"],
                "Size": row["size"],
                "Category": row["category"],
                "Subcategory": row["subcategory"],
                "Sex": row["sex"],
                "Stock #": row["stock_number"],
                "UoM": row["uom"],
                "Go to Writeoffs": row["writeoffs"],
                "Source": row["source"],
            }
            for row in catalog_rows
        ]

    def inventory_item_number_audit(self) -> dict[str, int]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_rows,
                    SUM(CASE WHEN items.wings_item_no IS NULL OR trim(items.wings_item_no) = '' THEN 1 ELSE 0 END) AS missing_rows,
                    SUM(CASE WHEN catalog.is_wings = 1 THEN 1 ELSE 0 END) AS official_rows,
                    SUM(CASE WHEN catalog.is_wings = 0 THEN 1 ELSE 0 END) AS local_rows
                FROM items
                LEFT JOIN wings_catalog AS catalog ON catalog.item_no = items.wings_item_no
                """
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("total_rows", "missing_rows", "official_rows", "local_rows")}

    def export_cadet_history_spreadsheet(self, cadet_id: int, *, open_after: bool = True) -> Path:
        details = self.get_cadet_details(cadet_id)
        cadet = details["cadet"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.settings.database_path.parent / "exports"
        cadet_token = self._safe_filename_token(str(cadet["full_name"]), fallback=f"cadet_{cadet_id}")
        export_path = export_dir / f"cadet_history_{cadet_token}_{timestamp}.xlsx"

        overview_rows = [
            {
                "cadet_id": cadet["cadet_id"],
                "full_name": cadet["full_name"],
                "email": cadet["email"],
                "created_at": cadet["created_at"],
                "updated_at": cadet["updated_at"],
                "open_items": len(details["current_items"]),
                "acquired_items": details["acquired_items"],
                "history_entries": len(details["history"]),
                "fitting_size_entries": len(details["size_entries"]),
            }
        ]

        current_rows: list[dict[str, Any]] = []
        for row in details["current_items"]:
            enriched_row = dict(row)
            enriched_row["days_out"] = self._days_between_timestamps(row.get("checkout_time"))
            current_rows.append(enriched_row)

        history_rows: list[dict[str, Any]] = []
        for row in details["history"]:
            enriched_row = dict(row)
            enriched_row["days_out"] = self._days_between_timestamps(
                row.get("checkout_time"),
                row.get("closed_time"),
            )
            history_rows.append(enriched_row)

        self._write_simple_xlsx_workbook(
            export_path,
            workbook_title=f"{self.settings.org_name} Cadet History Export",
            sheets=[
                {
                    "sheet_name": "Cadet Overview",
                    "columns": [
                        "cadet_id",
                        "full_name",
                        "email",
                        "created_at",
                        "updated_at",
                        "open_items",
                        "acquired_items",
                        "history_entries",
                        "fitting_size_entries",
                    ],
                    "rows": overview_rows,
                },
                {
                    "sheet_name": "Fitting Sizes",
                    "columns": [
                        "size_entry_id",
                        "category",
                        "size_label",
                        "size_value",
                        "catalog_item_no",
                        "notes",
                        "created_at",
                        "updated_at",
                    ],
                    "rows": details["size_entries"],
                },
                {
                    "sheet_name": "Current Items",
                    "columns": [
                        "transaction_id",
                        "barcode_id",
                        "item_name",
                        "category",
                        "variant",
                        "item_type",
                        "approved_by_role",
                        "approved_by_name",
                        "checkout_time",
                        "days_out",
                        "condition_notes",
                    ],
                    "rows": current_rows,
                },
                {
                    "sheet_name": "Transaction History",
                    "columns": [
                        "transaction_id",
                        "barcode_id",
                        "item_name",
                        "approved_by_role",
                        "approved_by_name",
                        "checkout_time",
                        "disposition",
                        "closed_time",
                        "days_out",
                        "closed_by_role",
                        "closed_by_name",
                        "condition_notes",
                    ],
                    "rows": history_rows,
                },
            ],
        )
        if open_after:
            open_file(export_path)
        return export_path

    def export_hidden_easter_egg_spreadsheet(self, *, open_after: bool = True) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = self.settings.database_path.parent / "exports"
        export_path = export_dir / f"hidden_easter_egg_export_{timestamp}.xlsx"
        admin_placeholders = ", ".join("?" for _ in sorted(RESERVED_ADMIN_IDS))
        cadet_placeholders = ", ".join("?" for _ in sorted(RESERVED_CADET_IDS))
        barcode_placeholders = ", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)

        with self.database.connect() as connection:
            admin_rows = connection.execute(
                f"""
                SELECT admin_id, display_name, role, code_value, is_active, created_at, updated_at
                FROM admin_codes
                WHERE admin_id IN ({admin_placeholders})
                ORDER BY admin_id
                """,
                sorted(RESERVED_ADMIN_IDS),
            ).fetchall()
            cadet_rows = connection.execute(
                f"""
                SELECT cadet_id, full_name, email, created_at, updated_at
                FROM cadets
                WHERE cadet_id IN ({cadet_placeholders})
                ORDER BY cadet_id
                """,
                sorted(RESERVED_CADET_IDS),
            ).fetchall()
            item_rows = connection.execute(
                f"""
                SELECT barcode_id, item_name, category, variant, item_type, status, total_quantity, available_quantity, notes, created_at, updated_at
                FROM items
                WHERE barcode_id IN ({barcode_placeholders})
                ORDER BY barcode_id
                """,
                EASTER_EGG_BARCODE_IDS,
            ).fetchall()
            transaction_rows = connection.execute(
                f"""
                SELECT
                    transaction_id,
                    barcode_id,
                    cadet_id,
                    cadet_name,
                    cadet_email,
                    checkout_time,
                    approved_by_admin_id,
                    approved_by_name,
                    approved_by_role,
                    approved_at,
                    return_time,
                    return_approved_by_admin_id,
                    return_approved_by_name,
                    return_approved_by_role,
                    return_approved_at,
                    disposition,
                    condition_notes
                FROM transactions
                WHERE barcode_id IN ({barcode_placeholders})
                ORDER BY transaction_id
                """,
                EASTER_EGG_BARCODE_IDS,
            ).fetchall()

        # Devin says Heart is loyal, so the private workbook starts with the character roster instead of the raw IDs :D
        profile_rows, equipment_log_rows, gallery_rows, gallery_images = self._build_hidden_easter_egg_export_views(
            admin_rows=[dict(row) for row in admin_rows],
            cadet_rows=[dict(row) for row in cadet_rows],
            item_rows=[dict(row) for row in item_rows],
            transaction_rows=[dict(row) for row in transaction_rows],
        )

        self._write_simple_xlsx_workbook(
            export_path,
            workbook_title=f"{self.settings.org_name} Hidden Easter Egg Export",
            sheets=[
                {
                    "sheet_name": "ACE Profiles",
                    "columns": [
                        "ace_name",
                        "trait",
                        "cadet_name",
                        "cadet_email",
                        "admin_name",
                        "admin_code",
                        "outfit_title",
                        "item_name",
                        "barcode_id",
                        "checkout_time",
                        "equipment_log",
                    ],
                    "rows": profile_rows,
                },
                {
                    "sheet_name": "Equipment Logs",
                    "columns": [
                        "transaction_id",
                        "ace_name",
                        "trait",
                        "cadet_name",
                        "approved_by_name",
                        "approved_by_role",
                        "barcode_id",
                        "item_name",
                        "outfit_title",
                        "checkout_status",
                        "checkout_time",
                        "condition_notes",
                    ],
                    "rows": equipment_log_rows,
                },
                {
                    "sheet_name": "ACE Gallery",
                    "columns": ["ace_name", "trait", "outfit_title", "asset_file", "notes"],
                    "rows": gallery_rows,
                    "images": gallery_images,
                },
                {
                    "sheet_name": "Hidden Admins",
                    "columns": ["admin_id", "display_name", "role", "code_value", "is_active", "created_at", "updated_at"],
                    "rows": [dict(row) for row in admin_rows],
                },
                {
                    "sheet_name": "Hidden Cadets",
                    "columns": ["cadet_id", "full_name", "email", "created_at", "updated_at"],
                    "rows": [dict(row) for row in cadet_rows],
                },
                {
                    "sheet_name": "Hidden Items",
                    "columns": [
                        "barcode_id",
                        "item_name",
                        "category",
                        "variant",
                        "item_type",
                        "status",
                        "total_quantity",
                        "available_quantity",
                        "notes",
                        "created_at",
                        "updated_at",
                    ],
                    "rows": [dict(row) for row in item_rows],
                },
                {
                    "sheet_name": "Hidden Transactions",
                    "columns": [
                        "transaction_id",
                        "barcode_id",
                        "cadet_id",
                        "cadet_name",
                        "cadet_email",
                        "checkout_time",
                        "approved_by_admin_id",
                        "approved_by_name",
                        "approved_by_role",
                        "approved_at",
                        "return_time",
                        "return_approved_by_admin_id",
                        "return_approved_by_name",
                        "return_approved_by_role",
                        "return_approved_at",
                        "disposition",
                        "condition_notes",
                    ],
                    "rows": [dict(row) for row in transaction_rows],
                },
            ],
        )
        if open_after:
            open_file(export_path)
        return export_path

    def _build_hidden_easter_egg_export_views(
        self,
        *,
        admin_rows: list[dict[str, Any]],
        cadet_rows: list[dict[str, Any]],
        item_rows: list[dict[str, Any]],
        transaction_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        admin_map = {int(row["admin_id"]): dict(row) for row in admin_rows}
        cadet_map = {int(row["cadet_id"]): dict(row) for row in cadet_rows}
        item_map = {str(row["barcode_id"]).strip().upper(): dict(row) for row in item_rows}
        transaction_map = {int(row["cadet_id"]): dict(row) for row in transaction_rows}

        profile_rows: list[dict[str, Any]] = []
        equipment_log_rows: list[dict[str, Any]] = []
        gallery_rows: list[dict[str, Any]] = []
        gallery_images: list[dict[str, Any]] = []
        gallery_row_number = 2

        for profile in EASTER_EGG_EXPORT_PROFILES:
            cadet = cadet_map.get(int(profile["cadet_id"]))
            transaction = transaction_map.get(int(profile["cadet_id"]))
            if cadet is None or transaction is None:
                continue
            item = item_map.get(str(transaction["barcode_id"]).strip().upper(), {})
            admin = admin_map.get(int(transaction.get("approved_by_admin_id") or 0), {})
            equipment_log = str(item.get("notes") or transaction.get("condition_notes") or "")

            # Devin says Spade is smart, so every hidden row lines up the person, outfit, and checkout trail in one place :D
            profile_rows.append(
                {
                    "ace_name": profile["ace_name"],
                    "trait": profile["trait"],
                    "cadet_name": cadet.get("full_name", ""),
                    "cadet_email": cadet.get("email", ""),
                    "admin_name": admin.get("display_name", transaction.get("approved_by_name", "")),
                    "admin_code": admin.get("code_value", ""),
                    "outfit_title": profile["outfit_title"],
                    "item_name": item.get("item_name", ""),
                    "barcode_id": transaction.get("barcode_id", ""),
                    "checkout_time": transaction.get("checkout_time", ""),
                    "equipment_log": equipment_log,
                }
            )
            equipment_log_rows.append(
                {
                    "transaction_id": transaction.get("transaction_id", ""),
                    "ace_name": profile["ace_name"],
                    "trait": profile["trait"],
                    "cadet_name": cadet.get("full_name", ""),
                    "approved_by_name": transaction.get("approved_by_name", ""),
                    "approved_by_role": transaction.get("approved_by_role", ""),
                    "barcode_id": transaction.get("barcode_id", ""),
                    "item_name": item.get("item_name", ""),
                    "outfit_title": profile["outfit_title"],
                    "checkout_status": "Open Checkout",
                    "checkout_time": transaction.get("checkout_time", ""),
                    "condition_notes": equipment_log,
                }
            )
            gallery_rows.append(
                {
                    "ace_name": profile["ace_name"],
                    "trait": profile["trait"],
                    "outfit_title": profile["outfit_title"],
                    "asset_file": profile["asset_label"],
                    "notes": equipment_log,
                }
            )
            if profile.get("asset_path"):
                # Devin says Diamo is sweet, so the gallery keeps the art close to the outfit notes instead of hiding it in a side folder :D
                gallery_images.append(
                    {
                        "path": profile["asset_path"],
                        "row": gallery_row_number,
                        "column": 7,
                        "max_width_px": 220,
                        "max_height_px": 260,
                        "name": profile["asset_label"] or f"{profile['ace_name']}_character.png",
                    }
                )
            for _ in range(7):
                gallery_rows.append({})
            gallery_row_number += 8

        group_row = gallery_row_number + 2
        gallery_rows.append(
            {
                "ace_name": "ACE Crew",
                "trait": "Heart loyal | Spade smart | Clubs funny | Diamo sweet",
                "outfit_title": "Group Snapshot",
                "asset_file": EASTER_EGG_GROUP_ASSET["asset_label"],
                "notes": "Private testing art sheet for the hidden ACE roster.",
            }
        )
        if EASTER_EGG_GROUP_ASSET.get("asset_path"):
            # Devin says Clubs is funny, so the crew shot gets a little stage space at the end of the gallery :D
            gallery_images.append(
                {
                    "path": EASTER_EGG_GROUP_ASSET["asset_path"],
                    "row": group_row,
                    "column": 7,
                    "max_width_px": 320,
                    "max_height_px": 220,
                    "name": str(EASTER_EGG_GROUP_ASSET["asset_label"]),
                }
            )

        return profile_rows, equipment_log_rows, gallery_rows, gallery_images

    def _checked_out_report(self) -> tuple[list[str], list[dict[str, Any]]]:
        columns = [
            "barcode_id",
            "item_name",
            "category",
            "variant",
            "item_type",
            "cadet_name",
            "cadet_email",
            "approved_by_name",
            "approved_by_role",
            "checkout_time",
            "days_out",
        ]
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    t.barcode_id,
                    i.item_name,
                    i.category,
                    i.variant,
                    i.item_type,
                    t.cadet_name,
                    t.cadet_email,
                    t.approved_by_name,
                    t.approved_by_role,
                    t.checkout_time,
                    CAST(julianday('now') - julianday(t.checkout_time) AS INTEGER) AS days_out
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE t.return_time IS NULL
                  AND t.barcode_id NOT IN ({", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)})
                ORDER BY t.checkout_time DESC
                """,
                EASTER_EGG_BARCODE_IDS,
            ).fetchall()
        return columns, [dict(row) for row in rows]

    def _inventory_changes_report(self) -> tuple[list[str], list[dict[str, Any]]]:
        columns = [
            "event_time",
            "action",
            "item_name",
            "variant",
            "quantity_change",
            "total_before",
            "total_after",
            "available_after",
            "barcode_id",
            "wings_item_no",
            "category",
            "details",
            "source",
        ]
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    event_time,
                    action,
                    item_name,
                    variant,
                    quantity_change,
                    total_before,
                    total_after,
                    available_after,
                    barcode_id,
                    wings_item_no,
                    category,
                    details,
                    source
                FROM inventory_changes
                ORDER BY event_time DESC, change_id DESC
                """
            ).fetchall()
        return columns, [dict(row) for row in rows]

    def _transaction_history_report(self) -> tuple[list[str], list[dict[str, Any]]]:
        columns = [
            "transaction_id",
            "barcode_id",
            "item_name",
            "cadet_name",
            "cadet_email",
            "approved_by_name",
            "approved_by_role",
            "checkout_time",
            "disposition",
            "closed_time",
            "closed_by_name",
            "closed_by_role",
            "condition_notes",
        ]
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    t.transaction_id,
                    t.barcode_id,
                    i.item_name,
                    t.cadet_name,
                    t.cadet_email,
                    t.approved_by_name,
                    t.approved_by_role,
                    t.checkout_time,
                    CASE
                        WHEN t.return_time IS NULL THEN 'Checked Out'
                        WHEN trim(t.disposition) <> '' THEN t.disposition
                        ELSE 'Returned'
                    END AS disposition,
                    t.return_time AS closed_time,
                    t.return_approved_by_name AS closed_by_name,
                    t.return_approved_by_role AS closed_by_role,
                    t.condition_notes
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE t.barcode_id NOT IN ({", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)})
                ORDER BY t.checkout_time DESC, t.transaction_id DESC
                """,
                EASTER_EGG_BARCODE_IDS,
            ).fetchall()
        return columns, [dict(row) for row in rows]

    def _acquired_items_report(self) -> tuple[list[str], list[dict[str, Any]]]:
        columns = [
            "transaction_id",
            "cadet_name",
            "cadet_email",
            "barcode_id",
            "item_name",
            "category",
            "variant",
            "item_type",
            "disposition",
            "acquired_time",
            "approved_by_name",
            "approved_by_role",
            "condition_notes",
        ]
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    t.transaction_id,
                    t.cadet_name,
                    t.cadet_email,
                    t.barcode_id,
                    i.item_name,
                    i.category,
                    i.variant,
                    i.item_type,
                    t.disposition,
                    t.return_time AS acquired_time,
                    t.return_approved_by_name AS approved_by_name,
                    t.return_approved_by_role AS approved_by_role,
                    t.condition_notes
                FROM transactions t
                JOIN items i ON i.barcode_id = t.barcode_id
                WHERE t.disposition IN ('Acquired / Permanent Issue', 'Purchased')
                  AND t.barcode_id NOT IN ({", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)})
                ORDER BY t.return_time DESC, t.transaction_id DESC
                """,
                EASTER_EGG_BARCODE_IDS,
            ).fetchall()
        return columns, [dict(row) for row in rows]

    def _fetch_label_records_by_barcode_ids(self, barcode_ids: list[str]) -> list[dict[str, Any]]:
        cleaned_ids = [
            barcode.strip().upper()
            for barcode in barcode_ids
            if barcode.strip() and not self._is_easter_egg_barcode(barcode)
        ]
        if not cleaned_ids:
            return []
        placeholders = ", ".join("?" for _ in cleaned_ids)
        query = f"""
            SELECT
                barcode_id,
                item_name,
                category,
                variant,
                item_type,
                status,
                total_quantity,
                available_quantity,
                notes,
                created_at,
                updated_at
            FROM items
            WHERE barcode_id IN ({placeholders})
            ORDER BY category, item_type, variant, barcode_id
        """
        with self.database.connect() as connection:
            rows = connection.execute(query, cleaned_ids).fetchall()
        return [dict(row) for row in rows]

    def _expand_label_records(
        self,
        records: list[dict[str, Any]],
        *,
        barcode_quantities: dict[str, int],
        barcode_order: list[str],
    ) -> list[dict[str, Any]]:
        record_map = {str(record["barcode_id"]).upper(): record for record in records}
        expanded_records: list[dict[str, Any]] = []

        for barcode_id in barcode_order:
            cleaned_barcode = barcode_id.strip().upper()
            record = record_map.get(cleaned_barcode)
            if record is None:
                continue
            quantity = barcode_quantities.get(cleaned_barcode, 1)
            try:
                copies = max(1, int(quantity))
            except (TypeError, ValueError):
                copies = 1
            for _ in range(copies):
                expanded_records.append(dict(record))

        return expanded_records

    def _write_simple_xlsx(
        self,
        path: Path,
        *,
        sheet_name: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> Path:
        return self._write_simple_xlsx_workbook(
            path,
            workbook_title=f"{self.settings.org_name} Inventory Export",
            sheets=[
                {
                    "sheet_name": sheet_name,
                    "columns": columns,
                    "rows": rows,
                }
            ],
        )

    def _write_simple_xlsx_workbook(
        self,
        path: Path,
        *,
        workbook_title: str,
        sheets: list[dict[str, Any]],
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        normalized_sheets = self._normalize_xlsx_sheets(sheets)
        prepared_images = self._prepare_xlsx_sheet_images(normalized_sheets)
        drawing_sheet_indexes = [sheet_index for sheet_index, sheet in enumerate(normalized_sheets, start=1) if sheet["images"]]

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{escape(sheet["sheet_name"])}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>'
                for sheet_index, sheet in enumerate(normalized_sheets, start=1)
            )
            + "</sheets>"
            + "</workbook>"
        )

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2">'
            '<font><sz val="10"/><name val="Aptos Narrow"/></font>'
            '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos Narrow"/></font>'
            '</fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FF03244D"/><bgColor indexed="64"/></patternFill></fill>'
            '</fills>'
            '<borders count="2">'
            '<border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left style="thin"><color rgb="FFD1D5DB"/></left>'
            '<right style="thin"><color rgb="FFD1D5DB"/></right>'
            '<top style="thin"><color rgb="FFD1D5DB"/></top>'
            '<bottom style="thin"><color rgb="FFD1D5DB"/></bottom><diagonal/></border>'
            '</borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
            '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            '<alignment vertical="top" wrapText="1"/></xf>'
            '</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        )

        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + ('<Default Extension="png" ContentType="image/png"/>' if prepared_images else "")
            + '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{sheet_index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for sheet_index in range(1, len(normalized_sheets) + 1)
            )
            + "".join(
                f'<Override PartName="/xl/drawings/drawing{drawing_index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
                for drawing_index, _sheet_index in enumerate(drawing_sheet_indexes, start=1)
            )
            + '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + '<Override PartName="/docProps/core.xml" '
            'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            + '<Override PartName="/docProps/app.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            + "</Types>"
        )

        root_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"
        )

        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{sheet_index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{sheet_index}.xml"/>'
                for sheet_index in range(1, len(normalized_sheets) + 1)
            )
            + f'<Relationship Id="rId{len(normalized_sheets) + 1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        )

        app_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            f"<Application>{escape(self.settings.org_name)}</Application>"
            "<HeadingPairs>"
            "<vt:vector size=\"2\" baseType=\"variant\">"
            "<vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>"
            f"<vt:variant><vt:i4>{len(normalized_sheets)}</vt:i4></vt:variant>"
            "</vt:vector>"
            "</HeadingPairs>"
            "<TitlesOfParts>"
            f'<vt:vector size="{len(normalized_sheets)}" baseType="lpstr">'
            + "".join(f"<vt:lpstr>{escape(sheet['sheet_name'])}</vt:lpstr>" for sheet in normalized_sheets)
            + "</vt:vector>"
            "</TitlesOfParts>"
            "</Properties>"
        )

        core_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(workbook_title)}</dc:title>"
            f"<dc:creator>{escape(self.settings.org_name)}</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created_utc}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created_utc}</dcterms:modified>'
            "</cp:coreProperties>"
        )

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
            workbook.writestr("[Content_Types].xml", content_types_xml)
            workbook.writestr("_rels/.rels", root_rels_xml)
            workbook.writestr("docProps/app.xml", app_xml)
            workbook.writestr("docProps/core.xml", core_xml)
            workbook.writestr("xl/workbook.xml", workbook_xml)
            workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            workbook.writestr("xl/styles.xml", styles_xml)
            for sheet_index, sheet in enumerate(normalized_sheets, start=1):
                has_images = bool(sheet["images"])
                worksheet_xml = self._build_xlsx_worksheet_xml(sheet["columns"], sheet["rows"], has_images=has_images)
                workbook.writestr(f"xl/worksheets/sheet{sheet_index}.xml", worksheet_xml)
                if has_images:
                    workbook.writestr(
                        f"xl/worksheets/_rels/sheet{sheet_index}.xml.rels",
                        self._build_xlsx_sheet_relationships_xml(int(sheet["drawing_index"])),
                    )
                    workbook.writestr(
                        f"xl/drawings/drawing{sheet['drawing_index']}.xml",
                        self._build_xlsx_drawing_xml(sheet["images"]),
                    )
                    workbook.writestr(
                        f"xl/drawings/_rels/drawing{sheet['drawing_index']}.xml.rels",
                        self._build_xlsx_drawing_relationships_xml(sheet["images"]),
                    )
            for image in prepared_images:
                workbook.writestr(f"xl/media/{image['media_name']}", image["content"])
        return path

    def _normalize_xlsx_sheets(self, sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_sheets: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for sheet in sheets:
            raw_name = str(sheet.get("sheet_name") or "Sheet")
            columns = list(sheet.get("columns") or [])
            rows = list(sheet.get("rows") or [])
            images = list(sheet.get("images") or [])
            sheet_name = self._unique_xlsx_sheet_name(raw_name, used_names)
            normalized_sheets.append(
                {
                    "sheet_name": sheet_name,
                    "columns": columns,
                    "rows": rows,
                    "images": images,
                }
            )
        if not normalized_sheets:
            normalized_sheets.append({"sheet_name": "Sheet1", "columns": [], "rows": [], "images": []})
        return normalized_sheets

    def _build_xlsx_worksheet_xml(self, columns: list[str], rows: list[dict[str, Any]], *, has_images: bool = False) -> str:
        width_map = {
            "Item No": 14, "Qty Issued": 12, "Qty Available": 14,
            "Total in Inventory": 18, "Item Name": 34, "Size": 18,
            "Category": 22, "Subcategory": 22, "Sex": 9, "Stock #": 18,
            "UoM": 9, "Go to Writeoffs": 18, "Source": 18,
            "Report Detail": 22, "Value": 70, "Date & Time": 24,
            "Report Section": 30, "Activity Class": 26, "Weekly Event": 24,
            "Change": 24, "Item": 38, "Size / Variant": 20,
            "Qty Change": 12, "Previous Total": 15, "New Total": 12,
            "Available Now": 15, "Barcode": 16, "WINGS / Local Item #": 24,
            "Explanation": 54, "Cadet": 28, "Cadet Email": 30,
            "Approved By": 24, "Checked Out": 24, "Closed": 24,
            "Notes": 48, "Details": 58, "Validation Note": 58,
            "Measurement / Item": 28, "Recorded Size": 18,
            "Source Category": 22, "Report Category": 22,
        }
        columns_xml = "".join(
            f'<col min="{index}" max="{index}" width="{width_map.get(column, 18)}" customWidth="1"/>'
            for index, column in enumerate(columns, start=1)
        )
        last_column = self._xlsx_column_name(max(1, len(columns)))
        last_row = max(1, len(rows) + 1)
        used_range = f"A1:{last_column}{last_row}"
        sheet_rows: list[str] = []
        header_cells = "".join(
            self._xlsx_inline_string_cell(
                column_index + 1,
                1,
                (
                    column
                    if column in WINGS_COLUMNS or (" " in column and "_" not in column)
                    else column.replace("_", " ").title()
                ),
                style_id=1,
            )
            for column_index, column in enumerate(columns)
        )
        sheet_rows.append(f'<row r="1" ht="30" customHeight="1">{header_cells}</row>')

        for row_index, row in enumerate(rows, start=2):
            cell_xml = "".join(
                self._xlsx_cell(column_index + 1, row_index, row.get(column, ""), style_id=2)
                for column_index, column in enumerate(columns)
            )
            sheet_rows.append(f'<row r="{row_index}">{cell_xml}</row>')

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<dimension ref="{used_range}"/>'
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{columns_xml}</cols>'
            f'<sheetData>{"".join(sheet_rows)}</sheetData>'
            f'<autoFilter ref="{used_range}"/>'
            + ('<drawing r:id="rId1"/>' if has_images else "")
            + "</worksheet>"
        )

    def _prepare_xlsx_sheet_images(self, sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared_images: list[dict[str, Any]] = []
        drawing_index = 1
        media_index = 1
        for sheet in sheets:
            raw_images = list(sheet.get("images") or [])
            normalized_images: list[dict[str, Any]] = []
            for image in raw_images:
                # Devin says Heart is loyal, so missing art quietly steps aside instead of breaking the whole secret workbook :D
                prepared = self._prepare_xlsx_image(image, media_index=media_index)
                if prepared is None:
                    continue
                media_index += 1
                normalized_images.append(prepared)
                prepared_images.append(prepared)
            sheet["images"] = normalized_images
            if normalized_images:
                sheet["drawing_index"] = drawing_index
                drawing_index += 1
        return prepared_images

    def _prepare_xlsx_image(self, image: dict[str, Any], *, media_index: int) -> dict[str, Any] | None:
        raw_path = image.get("path")
        if raw_path is None:
            return None
        image_path = Path(str(raw_path)).expanduser()
        if not image_path.exists():
            return None

        image_bytes = image_path.read_bytes()
        try:
            source_width, source_height = read_png_dimensions(image_bytes)
        except ValueError:
            return None
        display_width, display_height = scaled_dimensions(
            source_width,
            source_height,
            max_width=image.get("max_width_px"),
            max_height=image.get("max_height_px"),
        )

        media_name = f"image{media_index}.png"
        return {
            "media_name": media_name,
            "content": image_bytes,
            "row": max(1, int(image.get("row", 1))),
            "column": max(1, int(image.get("column", 1))),
            "width_px": display_width,
            "height_px": display_height,
            "name": str(image.get("name") or media_name),
        }

    def _build_xlsx_sheet_relationships_xml(self, drawing_index: int) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing{drawing_index}.xml"/>'
            "</Relationships>"
        )

    def _build_xlsx_drawing_xml(self, images: list[dict[str, Any]]) -> str:
        anchors = "".join(
            self._build_xlsx_image_anchor(image, picture_id=picture_id)
            for picture_id, image in enumerate(images, start=1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"{anchors}"
            "</xdr:wsDr>"
        )

    def _build_xlsx_drawing_relationships_xml(self, images: list[dict[str, Any]]) -> str:
        relationships = "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{escape(image["media_name"])}"/>'
            for index, image in enumerate(images, start=1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{relationships}"
            "</Relationships>"
        )

    def _build_xlsx_image_anchor(self, image: dict[str, Any], *, picture_id: int) -> str:
        width_emu = int(int(image["width_px"]) * 9525)
        height_emu = int(int(image["height_px"]) * 9525)
        start_column = max(0, int(image["column"]) - 1)
        start_row = max(0, int(image["row"]) - 1)
        image_name = escape(str(image["name"]))
        relationship_id = f"rId{picture_id}"
        # Devin says Clubs is funny, so the gallery anchors leave room for each sprite to steal the scene a little :D
        return (
            "<xdr:oneCellAnchor>"
            f"<xdr:from><xdr:col>{start_column}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{start_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
            f'<xdr:ext cx="{width_emu}" cy="{height_emu}"/>'
            "<xdr:pic>"
            f'<xdr:nvPicPr><xdr:cNvPr id="{picture_id}" name="{image_name}"/><xdr:cNvPicPr/></xdr:nvPicPr>'
            f'<xdr:blipFill><a:blip r:embed="{relationship_id}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
            f'<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
            "</xdr:pic>"
            "<xdr:clientData/>"
            "</xdr:oneCellAnchor>"
        )

    @staticmethod
    def _unique_xlsx_sheet_name(raw_name: str, used_names: set[str]) -> str:
        sanitized = re.sub(r"[:\\/?*\[\]]", "-", raw_name).strip() or "Sheet"
        base_name = sanitized[:31]
        candidate = base_name
        suffix = 2
        while candidate in used_names:
            suffix_text = f"_{suffix}"
            candidate = f"{base_name[: max(1, 31 - len(suffix_text))]}{suffix_text}"
            suffix += 1
        used_names.add(candidate)
        return candidate

    @staticmethod
    def _safe_filename_token(value: str, *, fallback: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
        return cleaned or fallback

    @classmethod
    def _days_between_timestamps(cls, start_value: Any, end_value: Any | None = None) -> int | str:
        start_dt = cls._parse_export_timestamp(start_value)
        if start_dt is None:
            return ""
        end_dt = cls._parse_export_timestamp(end_value) if end_value else datetime.now()
        if end_dt is None:
            end_dt = datetime.now()
        if (start_dt.tzinfo is None) != (end_dt.tzinfo is None):
            start_dt = start_dt.replace(tzinfo=None)
            end_dt = end_dt.replace(tzinfo=None)
        return max(0, int((end_dt - start_dt).total_seconds() // 86400))

    @staticmethod
    def _parse_export_timestamp(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        for candidate in (text, text.replace(" ", "T", 1)):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def _xlsx_cell(cls, column_index: int, row_index: int, value: Any, *, style_id: int = 0) -> str:
        if isinstance(value, bool):
            value = "TRUE" if value else "FALSE"
        if isinstance(value, int) and not isinstance(value, bool):
            cell_ref = f"{cls._xlsx_column_name(column_index)}{row_index}"
            return f'<c r="{cell_ref}" s="{style_id}"><v>{value}</v></c>'
        return cls._xlsx_inline_string_cell(
            column_index,
            row_index,
            "" if value is None else str(value),
            style_id=style_id,
        )

    @classmethod
    def _xlsx_inline_string_cell(
        cls,
        column_index: int,
        row_index: int,
        value: str,
        *,
        style_id: int = 0,
    ) -> str:
        cell_ref = f"{cls._xlsx_column_name(column_index)}{row_index}"
        escaped_value = escape(value)
        return (
            f'<c r="{cell_ref}" s="{style_id}" t="inlineStr">'
            f'<is><t xml:space="preserve">{escaped_value}</t></is></c>'
        )

    @staticmethod
    def _xlsx_column_name(index: int) -> str:
        letters: list[str] = []
        current = index
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            letters.append(chr(65 + remainder))
        return "".join(reversed(letters)) or "A"

    @staticmethod
    def _not_in_clause(column_name: str, values: list[Any] | tuple[Any, ...] | set[Any]) -> str:
        values_list = list(values)
        placeholders = ", ".join("?" for _ in values_list)
        return f"{column_name} NOT IN ({placeholders})"

    @staticmethod
    def _is_easter_egg_barcode(barcode_id: str | None) -> bool:
        return str(barcode_id or "").strip().upper() in EASTER_EGG_BARCODE_IDS

    @staticmethod
    def _resolve_barcode_alias(connection: sqlite3.Connection, barcode_id: str) -> str:
        resolved = str(barcode_id or "").strip().upper()
        seen: set[str] = set()
        while resolved and resolved not in seen:
            seen.add(resolved)
            active_item = connection.execute(
                "SELECT 1 FROM items WHERE barcode_id = ? COLLATE NOCASE",
                (resolved,),
            ).fetchone()
            if active_item is not None:
                break
            row = connection.execute(
                "SELECT canonical_barcode_id FROM barcode_aliases WHERE alias_barcode_id = ?",
                (resolved,),
            ).fetchone()
            if row is None:
                break
            resolved = str(row["canonical_barcode_id"] or "").strip().upper()
        return resolved

    @staticmethod
    def _is_easter_egg_cadet_id(cadet_id: int | str | None) -> bool:
        try:
            return int(cadet_id or 0) in RESERVED_CADET_IDS
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _is_easter_egg_admin_id(admin_id: int | str | None) -> bool:
        try:
            return int(admin_id or 0) in RESERVED_ADMIN_IDS
        except (TypeError, ValueError):
            return False

    def _upsert_cadet(self, connection: sqlite3.Connection, full_name: str, email: str) -> dict[str, Any]:
        name, normalized_email = self._validate_cadet_identity(full_name, email)
        existing = connection.execute(
            "SELECT cadet_id, full_name FROM cadets WHERE lower(email) = lower(?)",
            (normalized_email,),
        ).fetchone()
        if existing:
            supplied=NAME_PATTERN.match(name)
            saved=NAME_PATTERN.match(existing['full_name'])
            if supplied and saved and not supplied.group(2) and saved.group(2) and all(
                supplied.group(k).casefold()==saved.group(k).casefold() for k in (1,3)):
                name=existing['full_name']
            connection.execute(
                """
                UPDATE cadets
                SET full_name = ?, email = ?, updated_at = ?
                WHERE cadet_id = ?
                """,
                (name, normalized_email, utc_now(), existing["cadet_id"]),
            )
            cadet_id = existing["cadet_id"]
        else:
            cadet_id = self._lowest_available_integer_id(
                connection,
                table_name="cadets",
                id_column="cadet_id",
                reserved_ids=RESERVED_CADET_IDS,
            )
            cursor = connection.execute(
                """
                INSERT INTO cadets(cadet_id, full_name, email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cadet_id, name, normalized_email, utc_now(), utc_now()),
            )

        connection.execute(
            """
            UPDATE transactions
            SET cadet_id = ?
            WHERE cadet_id IS NULL AND lower(cadet_email) = lower(?)
            """,
            (cadet_id, normalized_email),
        )

        row = connection.execute(
            "SELECT cadet_id, full_name, email, created_at, updated_at FROM cadets WHERE cadet_id = ?",
            (cadet_id,),
        ).fetchone()
        return dict(row)

    @staticmethod
    def _lowest_available_integer_id(
        connection: sqlite3.Connection,
        *,
        table_name: str,
        id_column: str,
        reserved_ids: set[int] | None = None,
    ) -> int:
        reserved = set(reserved_ids or set())
        rows = connection.execute(
            f"SELECT {id_column} FROM {table_name} ORDER BY {id_column}"
        ).fetchall()
        used_ids = {int(row[id_column]) for row in rows}
        candidate = 1
        while True:
            if candidate not in reserved and candidate not in used_ids:
                return candidate
            candidate += 1

    def _sync_item_state(self, connection: sqlite3.Connection, barcode_id: str) -> None:
        item = connection.execute(
            "SELECT total_quantity, status FROM items WHERE barcode_id = ?",
            (barcode_id,),
        ).fetchone()
        if item is None:
            return
        if item["status"] in {"Retired", "Lost"}:
            connection.execute(
                "UPDATE items SET available_quantity = 0, updated_at = ? WHERE barcode_id = ?",
                (utc_now(), barcode_id),
            )
            return

        open_units = self._open_checkout_count(connection, barcode_id)
        available_quantity = max(item["total_quantity"] - open_units, 0)
        status = "Available" if available_quantity > 0 or open_units == 0 else "Checked Out"
        connection.execute(
            """
            UPDATE items
            SET available_quantity = ?, status = ?, updated_at = ?
            WHERE barcode_id = ?
            """,
            (available_quantity, status, utc_now(), barcode_id),
        )

    def _open_checkout_count(self, connection: sqlite3.Connection, barcode_id: str) -> int:
        row = connection.execute(
            "SELECT COUNT(*) AS open_count FROM transactions WHERE barcode_id = ? AND return_time IS NULL",
            (barcode_id,),
        ).fetchone()
        return int(row["open_count"])

    def _record_catalog_values(
        self,
        connection: sqlite3.Connection,
        category: str,
        variant: str,
        item_type: str,
        item_name: str,
    ) -> None:
        self.database.record_lookup_value("category", category, connection=connection)
        self.database.record_lookup_value("variant", variant, connection=connection)
        self.database.record_lookup_value("item_type", item_type, connection=connection)
        self.database.record_lookup_value("item_name", item_name, connection=connection)

    def _find_matching_item(
        self,
        connection: sqlite3.Connection,
        *,
        category: str,
        variant: str,
        item_type: str,
        item_name: str,
        wings_item_no: str = "",
        exclude_barcode: str = "",
    ) -> sqlite3.Row | None:
        excluded = str(exclude_barcode or "").strip().upper()
        exclusion_sql = " AND barcode_id <> ? COLLATE NOCASE" if excluded else ""
        excluded_params: tuple[str, ...] = (excluded,) if excluded else ()
        if wings_item_no:
            wings_match = connection.execute(
                f"""
                SELECT * FROM items
                WHERE lower(trim(COALESCE(wings_item_no, ''))) = lower(trim(?))
                  {exclusion_sql}
                  AND barcode_id NOT IN ({", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)})
                ORDER BY created_at, barcode_id
                LIMIT 1
                """,
                (wings_item_no, *excluded_params, *EASTER_EGG_BARCODE_IDS),
            ).fetchone()
            return wings_match
        exact_match = connection.execute(
            f"""
            SELECT *
            FROM items
            WHERE lower(trim(category)) = lower(trim(?))
              AND lower(trim(variant)) = lower(trim(?))
              AND lower(trim(item_type)) = lower(trim(?))
              AND lower(trim(item_name)) = lower(trim(?))
              {exclusion_sql}
              AND barcode_id NOT IN ({", ".join("?" for _ in EASTER_EGG_BARCODE_IDS)})
            ORDER BY created_at, barcode_id
            LIMIT 1
            """,
            (
                category,
                variant,
                item_type,
                item_name,
                *excluded_params,
                *EASTER_EGG_BARCODE_IDS,
            ),
        ).fetchone()
        if exact_match is not None:
            return exact_match
        return None

    def _next_barcode_for_prefix(
        self,
        connection: sqlite3.Connection,
        *,
        category: str,
        variant: str,
        item_type: str,
    ) -> str:
        rows = connection.execute(
            """
            WITH reserved_barcodes AS (
                SELECT barcode_id FROM items
                UNION
                SELECT alias_barcode_id AS barcode_id FROM barcode_aliases
            )
            SELECT barcode_id
            FROM reserved_barcodes
            WHERE barcode_id GLOB 'A[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
            ORDER BY barcode_id
            """
        ).fetchall()
        sequence_number = 1
        for row in rows:
            used_number = int(str(row["barcode_id"])[1:])
            if used_number < sequence_number:
                continue
            if used_number > sequence_number:
                break
            sequence_number += 1
        if sequence_number <= 9_999_999:
            return compose_barcode(category, variant, item_type, sequence_number)
        raise InventoryError("No unused A.C.E. barcode numbers remain.")

    @staticmethod
    def _validate_quantity(quantity: int, *, field_name: str = "Quantity", allow_zero: bool = False) -> int:
        try:
            value = int(quantity)
        except (TypeError, ValueError) as exc:
            raise InventoryError(f"{field_name} must be a whole number.") from exc
        minimum = 0 if allow_zero else 1
        if value < minimum:
            raise InventoryError(f"{field_name} must be at least {minimum}.")
        return value

    @staticmethod
    def _clean_lookup(value: str, label: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise InventoryError(f"{label} is required.")
        if label == "Item type":
            cleaned = ITEM_TYPE_ALIASES.get(cleaned, cleaned)
        return cleaned

    @staticmethod
    def _clean_item_name(value: str) -> str:
        cleaned = value.strip()
        folded = cleaned.casefold()
        for legacy_name, canonical_name in ITEM_NAME_ALIASES.items():
            if legacy_name.casefold() == folded:
                return canonical_name
        return cleaned

    def _normalize_admin_identity(self, approved_by: dict[str, Any] | None) -> dict[str, Any]:
        if not approved_by:
            raise InventoryError("An authenticated admin is required before approving this action.")

        role = str(approved_by.get("role") or DEFAULT_ADMIN_ROLE).strip().upper()
        display_name = str(approved_by.get("display_name") or "").strip()
        admin_id = approved_by.get("admin_id")

        if role == MASTER_ADMIN_ROLE:
            approved_name = "CADRE"
        else:
            if not display_name:
                raise InventoryError("Authenticated admin record is missing a display name.")
            approved_name = self._smart_title(display_name)

        return {
            "admin_id": admin_id,
            "approved_by_name": approved_name,
            "approved_by_role": role,
            "label": f"{role} {approved_name}".strip() if role != MASTER_ADMIN_ROLE else MASTER_ADMIN_ROLE,
        }

    def _validate_cadet_identity(self, full_name: str, email: str) -> tuple[str, str]:
        email_value = email.strip().lower()
        if not EMAIL_PATTERN.match(email_value):
            raise InventoryError("Cadet email must include an @ symbol and cannot contain spaces.")

        match = NAME_PATTERN.match(full_name)
        if not match:
            raise InventoryError("Enter first and last name. Middle initials are optional ('Last, First' or 'Last, MI, First').")

        last_name = self._smart_title(match.group(1))
        middle_initials = (match.group(2) or '').replace(".", "").upper()
        first_name = self._smart_title(match.group(3))
        normalized_name = f"{last_name}, {middle_initials}, {first_name}" if middle_initials else f"{last_name}, {first_name}"
        return normalized_name, email_value

    @staticmethod
    def _smart_title(value: str) -> str:
        cleaned = " ".join(value.strip().split())
        return cleaned.title()

    @staticmethod
    def _hash_admin_code(code: str) -> str:
        return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _suggest_item_name(category: str, variant: str, item_type: str) -> str:
        title_variant = variant.replace("-", " ").title()
        title_type = item_type.replace("-", " ").title()
        if category == "PT" and variant in {"DRY", "DRY-WICKING", "COTTON"}:
            return f"{title_variant} {title_type}"
        return f"{title_type} ({title_variant})"

    @staticmethod
    def _append_note(existing_notes: str | None, new_note: str) -> str:
        existing = (existing_notes or "").strip()
        addition = new_note.strip()
        if not addition:
            return existing
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{timestamp}] {addition}"
        return f"{existing}\n{entry}".strip() if existing else entry
