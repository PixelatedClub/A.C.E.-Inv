from __future__ import annotations

import bisect
import ctypes
import random
import re
import shutil
import string
import time
import tkinter as tk
import textwrap
import wave
from pathlib import Path
from typing import Any, Callable
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageSequence, ImageTk

from .barcode_utils import extract_scanned_barcode
from .config import (
    APP_TITLE,
    AppSettings,
    alternate_icons_enabled,
    device_backup_setup_completed,
    save_alternate_icons_enabled,
    save_device_backup_settings,
    save_settings,
)
from .services import InventoryError, InventoryService
from .defaults import ITEM_NAME_ALIASES, ITEM_TYPE_ALIASES
from .wings_catalog import WINGS_COLUMNS

try:
    import winsound
except ImportError:  # pragma: no cover - Windows provides winsound for packaged builds.
    winsound = None


CREDIT_QUOTES = [
    {"text": '"Do a job so well no one ever has to do it again."', "author": "Ethan Williams"},
    {
        "text": '"ACE Inventory\'s full name is actually Airman Clothing & Equipment Inventory System, but ACE Inventory System sounded cooler than ACEIS."',
        "author": "Ethan Williams",
    },
    {"text": '"You know, I sometimes wonder if anyone reads these?"', "author": "Ethan Williams"},
    {"text": '"You know, I make comics for fun sometimes."', "author": "Ethan Williams"},
    {
        "text": '"I hope that one day, in like 12 years, someone is still using this system and realizes how much tape and super glue was used."',
        "author": "Ethan Williams",
    },
    {
        "text": '"Team SHAPES has actually been around since I was in high school. Granted, we only worked on Minecraft videos, so we\'ve come a long way... Well, I have. Team SHAPES is just the name I want to use for my own game studio one day. I\'m currently the only member."',
        "author": "Ethan Williams",
    },
    {
        "text": '"I named the program ACE after the name of a game I want to make, ACELAND, not the Air Force methodology of dynamic warfighting."',
        "author": "Ethan Williams",
    },
    {"text": '"I made these quotes to procrastinate studying for finals."', "author": "Ethan Williams"},
]

SUIT_ICON_CODE_MAP = {
    "club": "club",
    "clubs": "club",
    "diamond": "diamond",
    "diamonds": "diamond",
    "diamo": "diamond",
    "heart": "heart",
    "hearts": "heart",
    "spade": "spade",
    "spades": "spade",
}

SUIT_ICON_FILENAMES = {
    "club": "club.png",
    "diamond": "diamond.png",
    "heart": "heart.png",
    "spade": "spade.png",
    "evil_clubs": "Evil Clubs.png",
    "diamond_emote": "diamoemotereally.png",
    "heart_rage": "heartemoterage.png",
    "shades_spades": "shadesNspades.png",
}

NORMAL_SUIT_ICON_KEYS = ("club", "diamond", "heart", "spade")
RARE_SUIT_ICON_KEYS = ("evil_clubs", "diamond_emote", "heart_rage", "shades_spades")
NORMAL_RARE_ICON_ODDS = 4000
ALTERNATE_RARE_ICON_ODDS = 4

SUIT_ICON_SOURCE_PATHS = {
    "club": Path(r"D:\Aseprite\palettes\Club.png"),
    "diamond": Path(r"D:\Aseprite\palettes\DiamondDog.png"),
    "heart": Path(r"D:\Aseprite\palettes\Heart.png"),
    "spade": Path(r"D:\Aseprite\palettes\Spade.png"),
}

CATALOG_ALIASES = {
    "variant": {
        "extra extra small": "XXS",
        "extra small": "XS",
        "small": "S",
        "medium": "M",
        "med": "M",
        "large": "L",
        "extra large": "XL",
        "x large": "XL",
        "double extra large": "2XL",
        "xxl": "2XL",
        "triple extra large": "3XL",
        "xxxl": "3XL",
    },
    "category": {
        "blue": "BLUES",
        "service dress": "BLUES",
        "physical training": "PTG",
        "pt": "PTG",
        "pt gear": "PTG",
    },
    "item_type": {legacy.casefold(): canonical for legacy, canonical in ITEM_TYPE_ALIASES.items()},
}


class InventoryApp(tk.Tk):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.service = InventoryService(settings)
        self.current_admin: dict[str, Any] | None = None
        self.current_checkout_barcode: str | None = None
        self.current_return_barcode: str | None = None
        self.generator_preview_record: dict[str, Any] | None = None
        self.selected_cadet_id: int | None = None
        self.selected_admin_id: int | str | None = None
        self.report_columns: list[str] = []
        self.report_rows: list[dict[str, Any]] = []
        self.item_cache: dict[str, dict[str, Any]] = {}
        self.barcode_directory_cache: dict[str, dict[str, Any]] = {}
        self.cadet_cache: dict[int, dict[str, Any]] = {}
        self.admin_cache: dict[str, dict[str, Any]] = {}
        self.label_print_quantity_cache: dict[str, int] = {}
        self.checkout_queue: dict[str, dict[str, Any]] = {}
        self.return_queue: dict[str, dict[str, Any]] = {}
        self.category_combos: list[ttk.Combobox] = []
        self.variant_combos: list[ttk.Combobox] = []
        self.item_type_combos: list[ttk.Combobox] = []
        self.item_name_combos: list[ttk.Combobox] = []
        self.catalog_combo_values: dict[str, list[str]] = {}
        self.catalog_combo_kinds: dict[str, str] = {}
        self.window_icon_image: tk.PhotoImage | None = None
        self.window_icon_cache: dict[str, tk.PhotoImage] = {}
        self.current_window_icon_key: str | None = None
        self.alternate_icons_enabled = alternate_icons_enabled()
        self.startup_splash: tk.Toplevel | None = None
        self.startup_frame_label: tk.Label | None = None
        self.startup_frames: list[ImageTk.PhotoImage] = []
        self.startup_frame_durations: list[int] = []
        self.startup_frame_offsets: list[int] = []
        self.startup_finish_after_id: str | None = None
        self.startup_frame_after_id: str | None = None
        self.startup_started_at: float | None = None
        self.startup_total_runtime_ms = 0
        self.startup_current_frame_index = 0

        self.title(APP_TITLE)
        self.geometry("1500x920")
        self.minsize(1240, 760)
        self._configure_window_icon()
        self._configure_style()
        self._create_variables()
        self._build_layout()
        self._load_settings_into_form()
        self.refresh_all_views()
        self.withdraw()
        self.after(100, self._begin_startup_sequence)

    def _configure_window_icon(self) -> None:
        self._apply_window_icon_choice(self._random_window_icon_key())

    def _apply_window_icon_from_code(self, code: str) -> None:
        icon_key = self._icon_key_for_code(code)
        if icon_key is None:
            icon_key = self._random_window_icon_key()
        self._apply_window_icon_choice(icon_key)

    def _apply_window_icon_choice(self, icon_key: str) -> None:
        icon_path = self._window_icon_path(icon_key)
        if icon_path is None:
            return
        cached_image = self.window_icon_cache.get(icon_key)
        if cached_image is None:
            try:
                cached_image = tk.PhotoImage(file=str(icon_path))
            except tk.TclError:
                return
            self.window_icon_cache[icon_key] = cached_image

        self.window_icon_image = cached_image
        self.current_window_icon_key = icon_key
        self.iconphoto(True, cached_image)

    def _random_window_icon_key(self) -> str:
        available_normal_keys = [
            key for key in NORMAL_SUIT_ICON_KEYS if self._window_icon_path(key) is not None
        ]
        available_rare_keys = [
            key for key in RARE_SUIT_ICON_KEYS if self._window_icon_path(key) is not None
        ]
        rare_icon_odds = (
            ALTERNATE_RARE_ICON_ODDS
            if self.alternate_icons_enabled
            else NORMAL_RARE_ICON_ODDS
        )
        if available_rare_keys and random.randrange(rare_icon_odds) == 0:
            return random.choice(available_rare_keys)
        if available_normal_keys:
            return random.choice(available_normal_keys)
        if available_rare_keys:
            return random.choice(available_rare_keys)
        return "club"

    def _window_icon_path(self, icon_key: str) -> Path | None:
        self._ensure_suit_icon_assets()
        portable_icon = self._suit_icon_dir() / SUIT_ICON_FILENAMES[icon_key]
        if portable_icon.exists():
            return portable_icon

        source_icon = SUIT_ICON_SOURCE_PATHS.get(icon_key)
        if source_icon is not None and source_icon.exists():
            return source_icon

        if icon_key == "club":
            fallback = self.settings.database_path.parent / "window_icon.png"
            if fallback.exists():
                return fallback
        return None

    def _ensure_suit_icon_assets(self) -> None:
        icon_dir = self._suit_icon_dir()
        icon_dir.mkdir(parents=True, exist_ok=True)
        for icon_key, source_path in SUIT_ICON_SOURCE_PATHS.items():
            target_path = icon_dir / SUIT_ICON_FILENAMES[icon_key]
            if target_path.exists() or not source_path.exists():
                continue
            try:
                shutil.copy2(source_path, target_path)
            except OSError:
                continue

    def _suit_icon_dir(self) -> Path:
        return self.settings.database_path.parent / "suit_icons"

    @staticmethod
    def _icon_key_for_code(code: str) -> str | None:
        cleaned_code = code.strip().lower()
        return SUIT_ICON_CODE_MAP.get(cleaned_code)

    def _configure_style(self) -> None:
        auburn_navy = "#03244d"
        auburn_blue = "#1f4f82"
        auburn_light = "#eef4fb"
        auburn_tab = "#dce9f7"
        border_blue = "#b8d2ec"

        self.configure(bg=auburn_light)
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.style.configure(".", font=("Segoe UI", 10))
        self.style.configure("TFrame", background=auburn_light)
        self.style.configure("TLabelframe", background=auburn_light, bordercolor=border_blue, relief="solid")
        self.style.configure(
            "TLabelframe.Label",
            background=auburn_light,
            foreground=auburn_navy,
            font=("Segoe UI", 10, "bold"),
        )
        self.style.configure("TLabel", background=auburn_light, foreground=auburn_navy)
        self.style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"), background=auburn_light, foreground=auburn_navy)
        self.style.configure("Subtitle.TLabel", font=("Segoe UI", 10), background=auburn_light, foreground=auburn_blue)
        self.style.configure("SummaryValue.TLabel", font=("Segoe UI", 24, "bold"), background=auburn_light, foreground=auburn_navy)
        self.style.configure("SummaryLabel.TLabel", font=("Segoe UI", 10), background=auburn_light, foreground=auburn_blue)
        self.style.configure("TButton", background=auburn_blue, foreground="white", padding=6, borderwidth=0)
        self.style.map("TButton", background=[("active", auburn_navy), ("pressed", auburn_navy)])
        self.style.configure("Treeview", background="white", fieldbackground="white", foreground="#0f172a", rowheight=24)
        self.style.configure("Treeview.Heading", background=auburn_navy, foreground="white")
        self.style.map("Treeview.Heading", background=[("active", auburn_blue)])
        self.style.configure("TNotebook", background=auburn_light, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=auburn_tab, foreground=auburn_navy, padding=(14, 8))
        self.style.map("TNotebook.Tab", background=[("selected", auburn_blue)], foreground=[("selected", "white")])
        self.style.configure("Scan.TEntry", font=("Consolas", 16))

    def _create_variables(self) -> None:
        self.summary_vars = {
            "sku_count": tk.StringVar(value="0"),
            "total_units": tk.StringVar(value="0"),
            "available_units": tk.StringVar(value="0"),
            "checked_out_units": tk.StringVar(value="0"),
            "lost_rows": tk.StringVar(value="0"),
            "retired_rows": tk.StringVar(value="0"),
            "cadet_count": tk.StringVar(value="0"),
        }
        self.status_var = tk.StringVar(value="")

        self.item_search_var = tk.StringVar()
        self.item_status_filter_var = tk.StringVar(value="All")
        self.item_barcode_var = tk.StringVar()
        self.item_name_var = tk.StringVar()
        self.item_category_var = tk.StringVar()
        self.item_variant_var = tk.StringVar()
        self.item_type_var = tk.StringVar()
        self.item_quantity_var = tk.StringVar(value="1")
        self.item_form_status_var = tk.StringVar(value="Status: New item")

        self.generator_category_var = tk.StringVar(value="OCP")
        self.generator_quick_find_var = tk.StringVar(value="")
        self.generator_selected_item_var = tk.StringVar(value="No equipment selected")
        self.generator_wings_item_no_var = tk.StringVar(value="")
        self.generator_size_label_var = tk.StringVar(value="Size")
        self.generator_variant_var = tk.StringVar(value="")
        self.generator_item_type_var = tk.StringVar(value="")
        self.generator_item_name_var = tk.StringVar(value="Coat")
        self.generator_units_var = tk.StringVar(value="1")
        self.generator_preview_var = tk.StringVar(value="")
        self.generator_result_var = tk.StringVar(value="")
        self.quick_find_result_map: dict[str, tuple[str, str, str, str, str]] = {}
        self.index_search_var = tk.StringVar(value="")
        self.index_system_var = tk.StringVar(value="All")
        self.index_sort_var = tk.StringVar(value="Item Number")
        self.index_summary_var = tk.StringVar(value="Equipment index not loaded yet.")
        self.wings_export_summary_var = tk.StringVar(value="WINGS export preview not loaded yet.")
        self.index_custom_name_var = tk.StringVar()
        self.index_custom_system_var = tk.StringVar(value="OTHER")
        self.index_custom_configuration_var = tk.StringVar(value="Standard")
        self.index_custom_size_system_var = tk.StringVar(value="Apparel Size")
        self.index_custom_aliases_var = tk.StringVar()
        self.selected_custom_index_id: int | None = None
        self.custom_index_cache: dict[int, dict[str, Any]] = {}
        self.custom_index_size_by_name: dict[str, str] = {}
        self.label_search_var = tk.StringVar()
        self.label_status_filter_var = tk.StringVar(value="All")
        self.label_selected_copies_var = tk.StringVar(value="1")
        self.label_library_summary_var = tk.StringVar(value="Label library not loaded yet.")

        self.directory_search_var = tk.StringVar()
        self.directory_status_filter_var = tk.StringVar(value="All")
        self.barcode_directory_summary_var = tk.StringVar(value="Barcode directory not loaded yet.")

        self.checkout_scan_var = tk.StringVar()
        self.checkout_last_name_var = tk.StringVar()
        self.checkout_middle_initial_var = tk.StringVar()
        self.checkout_first_name_var = tk.StringVar()
        self.checkout_email_var = tk.StringVar()
        self.checkout_qty_var = tk.StringVar(value="1")
        self.checkout_summary_var = tk.StringVar(value="Scan or paste a barcode and press Enter to add it to the checkout list.")

        self.return_scan_var = tk.StringVar()
        self.return_qty_var = tk.StringVar(value="1")
        self.return_summary_var = tk.StringVar(value="Scan or paste a barcode and press Enter to add it to the return list.")

        self.report_type_var = tk.StringVar(value="Checked Out Items")
        self.report_summary_var = tk.StringVar(value="No report loaded yet.")
        self.cadet_search_var = tk.StringVar()
        self.cadet_sort_var = tk.StringVar(value="ID")
        self.cadet_last_name_var = tk.StringVar()
        self.cadet_middle_initial_var = tk.StringVar()
        self.cadet_first_name_var = tk.StringVar()
        self.cadet_form_email_var = tk.StringVar()
        self.cadet_summary_var = tk.StringVar(value="Select or save a cadet to view issued items.")

        self.settings_org_name_var = tk.StringVar()
        self.settings_db_path_var = tk.StringVar()
        self.settings_protected_backup_var = tk.StringVar()
        self.settings_backup_interval_var = tk.StringVar()
        self.settings_overdue_days_var = tk.StringVar()
        self.current_admin_var = tk.StringVar(value="Not authenticated")
        self.admin_display_name_var = tk.StringVar()
        self.admin_code_var = tk.StringVar()
        self.admin_code_visible_var = tk.BooleanVar(value=False)
        self.admin_code_toggle_text_var = tk.StringVar(value="Show")
        self.admin_summary_var = tk.StringVar(value="Cadre code Det005 always signs in as CADRE.")
        self.admin_sort_var = tk.StringVar(value="ID")

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.dashboard_tab = ttk.Frame(self.notebook, padding=12)
        self.items_tab = ttk.Frame(self.notebook, padding=12)
        self.generator_tab = ttk.Frame(self.notebook, padding=12)
        self.index_tab = ttk.Frame(self.notebook, padding=12)
        self.wings_export_tab = ttk.Frame(self.notebook, padding=12)
        self.checkout_tab = ttk.Frame(self.notebook, padding=12)
        self.barcode_directory_tab = ttk.Frame(self.notebook, padding=12)
        self.cadets_tab = ttk.Frame(self.notebook, padding=12)
        self.reports_tab = ttk.Frame(self.notebook, padding=12)
        self.settings_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.items_tab, text="Items")
        self.notebook.add(self.generator_tab, text="Barcode Generator")
        self.notebook.add(self.index_tab, text="Index")
        self.notebook.add(self.wings_export_tab, text="WINGS Export")
        self.notebook.add(self.checkout_tab, text="Checkout / Return")
        self.notebook.add(self.barcode_directory_tab, text="Barcode Directory")
        self.notebook.add(self.cadets_tab, text="Cadets")
        self.notebook.add(self.reports_tab, text="Reports")
        self.notebook.add(self.settings_tab, text="Settings")

        self._build_dashboard_tab()
        self._build_items_tab()
        self._build_generator_tab()
        self._build_index_tab()
        self._build_wings_export_tab()
        self._build_checkout_tab()
        self._build_barcode_directory_tab()
        self._build_cadets_tab()
        self._build_reports_tab()
        self._build_settings_tab()

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w")
        status_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(6, 10))

    def _build_dashboard_tab(self) -> None:
        self.dashboard_tab.columnconfigure(0, weight=1)
        self.dashboard_tab.rowconfigure(3, weight=1)

        ttk.Label(
            self.dashboard_tab,
            text=f"{APP_TITLE} Overview",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.dashboard_tab,
            text="Portable SQLite inventory, checkout history, and backup visibility for Auburn AFROTC Detachment 005.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        cards = ttk.Frame(self.dashboard_tab)
        cards.grid(row=2, column=0, sticky="ew")
        for index in range(4):
            cards.columnconfigure(index, weight=1)

        summary_definitions = [
            ("sku_count", "Inventory Lines"),
            ("total_units", "Total Units"),
            ("available_units", "Units Available"),
            ("checked_out_units", "Units Checked Out"),
            ("lost_rows", "Lost Barcodes"),
            ("retired_rows", "Retired Barcodes"),
            ("cadet_count", "Saved Cadets"),
        ]
        for index, (key, label) in enumerate(summary_definitions):
            row = index // 4
            column = index % 4
            frame = ttk.LabelFrame(cards, padding=12)
            frame.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            ttk.Label(frame, textvariable=self.summary_vars[key], style="SummaryValue.TLabel").pack(anchor="w")
            ttk.Label(frame, text=label, style="SummaryLabel.TLabel").pack(anchor="w", pady=(4, 0))

        activity_frame = ttk.LabelFrame(self.dashboard_tab, text="Recent Activity", padding=10)
        activity_frame.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        activity_frame.columnconfigure(0, weight=1)
        activity_frame.rowconfigure(0, weight=1)

        self.dashboard_activity_tree = self._create_tree(
            activity_frame,
            columns=["event_time", "action", "barcode_id", "item_name", "cadet_name", "cadet_email"],
        )
        self.dashboard_activity_tree.grid(row=0, column=0, sticky="nsew")

        ttk.Button(
            self.dashboard_tab,
            text="Refresh Dashboard",
            command=self.refresh_dashboard,
        ).grid(row=4, column=0, sticky="e", pady=(12, 0))

    def _build_items_tab(self) -> None:
        self.items_tab.columnconfigure(0, weight=2)
        self.items_tab.columnconfigure(1, weight=1)
        self.items_tab.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.items_tab)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Search").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(controls, textvariable=self.item_search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 12))
        search_entry.bind("<Return>", lambda _event: self.refresh_items_tree())

        ttk.Label(controls, text="Status").grid(row=0, column=2, sticky="w")
        status_combo = ttk.Combobox(
            controls,
            textvariable=self.item_status_filter_var,
            state="readonly",
            values=["All", "Available", "Checked Out", "Retired", "Lost"],
            width=16,
        )
        status_combo.grid(row=0, column=3, sticky="w", padx=(6, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_items_tree())

        ttk.Button(controls, text="Refresh", command=self.refresh_items_tree).grid(row=0, column=4, sticky="e")

        tree_frame = ttk.LabelFrame(self.items_tab, text="Inventory Items", padding=10)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.items_tree = self._create_tree(
            tree_frame,
            columns=[
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "status",
                "total_quantity",
                "available_quantity",
                "notes",
            ],
        )
        self.items_tree.grid(row=0, column=0, sticky="nsew")
        self.items_tree.bind("<<TreeviewSelect>>", self._on_item_selected)

        form = ttk.LabelFrame(self.items_tab, text="Inventory Editor", padding=12)
        form.grid(row=1, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, textvariable=self.item_form_status_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(form, text="Barcode").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.item_barcode_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(form, text="Item").grid(row=2, column=0, sticky="w")
        item_name_combo = ttk.Combobox(form, textvariable=self.item_name_var)
        item_name_combo.grid(row=2, column=1, sticky="ew", pady=3)
        self.item_name_combos.append(item_name_combo)

        ttk.Label(form, text="Category").grid(row=3, column=0, sticky="w")
        category_combo = ttk.Combobox(form, textvariable=self.item_category_var)
        category_combo.grid(row=3, column=1, sticky="ew", pady=3)
        self.category_combos.append(category_combo)

        ttk.Label(form, text="Variant").grid(row=4, column=0, sticky="w")
        variant_combo = ttk.Combobox(form, textvariable=self.item_variant_var)
        variant_combo.grid(row=4, column=1, sticky="ew", pady=3)
        self.variant_combos.append(variant_combo)

        ttk.Label(form, text="Quantity").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(form, from_=1, to=1000, textvariable=self.item_quantity_var, width=10).grid(
            row=5, column=1, sticky="w", pady=3
        )

        ttk.Label(form, text="Notes").grid(row=6, column=0, sticky="nw", pady=(6, 0))
        self.item_notes_text = tk.Text(form, height=8, wrap="word")
        self.item_notes_text.grid(row=6, column=1, sticky="nsew", pady=(6, 0))
        form.rowconfigure(6, weight=1)

        actions = ttk.Frame(form)
        actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for index in range(3):
            actions.columnconfigure(index, weight=1)

        ttk.Button(actions, text="Create Manual Item", command=self._create_manual_item).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(actions, text="Restock Barcode", command=self._restock_item).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(actions, text="Delete Permanently", command=self._delete_item).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )
        ttk.Button(actions, text="Set Available", command=lambda: self._set_item_status("Available")).grid(
            row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0)
        )
        ttk.Button(actions, text="Mark Lost", command=lambda: self._set_item_status("Lost")).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=(6, 0)
        )
        ttk.Button(actions, text="Retire", command=lambda: self._set_item_status("Retired")).grid(
            row=1, column=2, sticky="ew", padx=(4, 0), pady=(6, 0)
        )
        ttk.Button(actions, text="Clear Form", command=self._clear_item_form).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )
        ttk.Button(actions, text="Edit Selected Barcode", command=self._edit_selected_item).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )

    def _build_generator_tab(self) -> None:
        self.generator_tab.columnconfigure(0, weight=1)
        self.generator_tab.columnconfigure(1, weight=1)
        self.generator_tab.rowconfigure(2, weight=1)

        config_frame = ttk.LabelFrame(self.generator_tab, text="Generate Barcode Labels", padding=12)
        config_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Quick Find").grid(row=0, column=0, sticky="w")
        self.generator_quick_find_entry = ttk.Entry(
            config_frame,
            textvariable=self.generator_quick_find_var,
            font=("Segoe UI", 11),
        )
        self.generator_quick_find_entry.grid(row=0, column=1, sticky="ew", pady=3)
        self.generator_quick_find_entry.bind("<KeyRelease>", self._filter_quick_find)
        self.generator_quick_find_entry.bind("<Return>", self._apply_quick_find_result)
        self.generator_quick_find_entry.bind("<Down>", self._focus_quick_find_results)
        ttk.Label(
            config_frame,
            text='Start typing naturally, such as "medium PT shirt" or "OCP coat regular".',
            style="Subtitle.TLabel",
            wraplength=420,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        results_frame = ttk.Frame(config_frame)
        results_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        results_frame.columnconfigure(0, weight=1)
        self.generator_quick_find_results = tk.Listbox(
            results_frame,
            height=6,
            exportselection=False,
            activestyle="dotbox",
            font=("Segoe UI", 10),
        )
        self.generator_quick_find_results.grid(row=0, column=0, sticky="nsew")
        quick_scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.generator_quick_find_results.yview)
        quick_scroll.grid(row=0, column=1, sticky="ns")
        self.generator_quick_find_results.configure(yscrollcommand=quick_scroll.set)
        self.generator_quick_find_results.bind("<ButtonRelease-1>", self._apply_quick_find_result)
        self.generator_quick_find_results.bind("<Double-Button-1>", self._apply_quick_find_result)
        self.generator_quick_find_results.bind("<Return>", self._apply_quick_find_result)

        ttk.Label(config_frame, text="Selected Equipment").grid(row=3, column=0, sticky="w")
        ttk.Label(
            config_frame,
            textvariable=self.generator_selected_item_var,
            style="Accent.TLabel",
            wraplength=420,
        ).grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(config_frame, textvariable=self.generator_size_label_var).grid(row=4, column=0, sticky="w")
        self.generator_size_combo = ttk.Combobox(config_frame, textvariable=self.generator_variant_var)
        self.generator_size_combo.grid(row=4, column=1, sticky="ew", pady=3)

        ttk.Label(config_frame, text="Quantity to Add").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(config_frame, from_=1, to=1000, textvariable=self.generator_units_var, width=10).grid(
            row=5, column=1, sticky="w", pady=3
        )

        ttk.Label(config_frame, text="Notes").grid(row=6, column=0, sticky="nw", pady=(6, 0))
        self.generator_notes_text = tk.Text(config_frame, height=6, wrap="word")
        self.generator_notes_text.grid(row=6, column=1, sticky="nsew", pady=(6, 0))
        config_frame.rowconfigure(6, weight=1)

        ttk.Label(config_frame, text="Preview").grid(row=7, column=0, sticky="w", pady=(10, 0))
        ttk.Label(config_frame, textvariable=self.generator_preview_var, wraplength=380).grid(
            row=7, column=1, sticky="w", pady=(10, 0)
        )

        buttons = ttk.Frame(config_frame)
        buttons.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for index in range(4):
            buttons.columnconfigure(index, weight=1)
        ttk.Button(buttons, text="Preview Barcode", command=self._preview_generated_barcode).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(buttons, text="Save Barcode", command=self._save_generated_barcode).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(buttons, text="Export Full Label Book", command=self._export_all_labels).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )
        ttk.Button(buttons, text="Clear Generator", command=self._clear_generator_form).grid(
            row=0, column=3, sticky="ew", padx=(4, 0)
        )

        result_frame = ttk.LabelFrame(self.generator_tab, text="Preview / Last Saved Barcode", padding=10)
        result_frame.grid(row=0, column=1, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)

        ttk.Label(result_frame, textvariable=self.generator_result_var, wraplength=480).grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        result_tree_frame = ttk.Frame(result_frame)
        result_tree_frame.grid(row=1, column=0, sticky="nsew")
        result_tree_frame.columnconfigure(0, weight=1)
        result_tree_frame.rowconfigure(0, weight=1)
        self.generator_tree = self._create_tree(
            result_tree_frame,
            columns=["barcode_id", "item_name", "category", "variant", "item_type", "total_quantity"],
        )
        self.generator_tree.grid(row=0, column=0, sticky="nsew")

        library_frame = ttk.LabelFrame(self.generator_tab, text="Central Label Library", padding=10)
        library_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        library_frame.columnconfigure(1, weight=1)
        library_frame.rowconfigure(1, weight=1)

        ttk.Label(library_frame, text="Search").grid(row=0, column=0, sticky="w")
        label_search_entry = ttk.Entry(library_frame, textvariable=self.label_search_var)
        label_search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        label_search_entry.bind("<Return>", lambda _event: self.refresh_label_library())

        ttk.Label(library_frame, text="Status").grid(row=0, column=2, sticky="w")
        label_status_combo = ttk.Combobox(
            library_frame,
            textvariable=self.label_status_filter_var,
            state="readonly",
            values=["All", "Available", "Checked Out", "Retired", "Lost"],
            width=16,
        )
        label_status_combo.grid(row=0, column=3, sticky="w", padx=(6, 10))
        label_status_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_label_library())

        ttk.Button(library_frame, text="Refresh Labels", command=self.refresh_label_library).grid(row=0, column=4, padx=(0, 6))
        ttk.Button(library_frame, text="Select All Visible", command=self._select_all_visible_labels).grid(row=0, column=5, padx=(0, 6))
        ttk.Button(library_frame, text="Clear Selection", command=self._clear_label_selection).grid(row=0, column=6, padx=(0, 6))
        ttk.Button(library_frame, text="Export Selected PDF", command=self._export_selected_labels).grid(row=0, column=7, padx=(0, 6))
        ttk.Button(library_frame, text="Export Filtered PDF", command=self._export_filtered_labels).grid(row=0, column=8)

        copies_frame = ttk.Frame(library_frame)
        copies_frame.grid(row=1, column=0, columnspan=9, sticky="ew", pady=(10, 0))
        copies_frame.columnconfigure(5, weight=1)
        ttk.Label(copies_frame, text="Selected Print Copies").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(copies_frame, from_=1, to=1000, textvariable=self.label_selected_copies_var, width=10).grid(
            row=0, column=1, sticky="w", padx=(8, 10)
        )
        ttk.Button(copies_frame, text="Apply To Selected", command=self._apply_selected_label_copies).grid(
            row=0, column=2, padx=(0, 6)
        )
        ttk.Button(copies_frame, text="Reset Selected", command=self._reset_selected_label_copies).grid(
            row=0, column=3, padx=(0, 6)
        )
        ttk.Label(
            copies_frame,
            text="Use this to choose how many label stickers print for each selected barcode.",
            style="Subtitle.TLabel",
        ).grid(row=0, column=4, columnspan=2, sticky="w")

        label_tree_frame = ttk.Frame(library_frame)
        label_tree_frame.grid(row=2, column=0, columnspan=9, sticky="nsew", pady=(10, 0))
        label_tree_frame.columnconfigure(0, weight=1)
        label_tree_frame.rowconfigure(0, weight=1)
        self.label_library_tree = self._create_tree(
            label_tree_frame,
            columns=["barcode_id", "item_name", "category", "variant", "item_type", "status", "total_quantity", "print_copies"],
            selectmode="extended",
        )
        self.label_library_tree.grid(row=0, column=0, sticky="nsew")
        self.label_library_tree.bind("<<TreeviewSelect>>", self._on_label_library_selected)
        ttk.Label(library_frame, textvariable=self.label_library_summary_var, wraplength=1180).grid(
            row=3, column=0, columnspan=9, sticky="w", pady=(8, 0)
        )

        for variable in (
            self.generator_category_var,
            self.generator_variant_var,
            self.generator_item_name_var,
        ):
            variable.trace_add("write", self._update_generator_preview)
        self._update_generator_preview()

    def _build_index_tab(self) -> None:
        self.index_tab.columnconfigure(0, weight=1)
        self.index_tab.rowconfigure(3, weight=1)

        ttk.Label(self.index_tab, text="Equipment Index", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self.index_tab,
            text=(
                "Search every official WINGS item number plus local Index additions. Official item numbers "
                "use the full ten-digit WINGS format, and Source identifies where each row came from."
            ),
            style="Subtitle.TLabel",
            wraplength=1180,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        controls = ttk.Frame(self.index_tab)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Search").grid(row=0, column=0, sticky="w")
        index_search_entry = ttk.Entry(controls, textvariable=self.index_search_var)
        index_search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 14))
        index_search_entry.bind("<KeyRelease>", lambda _event: self.refresh_index())
        ttk.Label(controls, text="WINGS Category").grid(row=0, column=2, sticky="w")
        index_system_combo = ttk.Combobox(
            controls,
            textvariable=self.index_system_var,
            state="readonly",
            values=[
                "All", "Accessories", "Awards", "Curriculum", "Footwear", "Insignia",
                "Outerwear", "Pants/Skirt", "PT wear", "Shirts", "SROTC Specialty Items",
            ],
            width=18,
        )
        index_system_combo.grid(row=0, column=3, sticky="w", padx=(6, 14))
        index_system_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_index())
        ttk.Label(controls, text="Sort By").grid(row=0, column=4, sticky="w")
        index_sort_combo = ttk.Combobox(
            controls,
            textvariable=self.index_sort_var,
            state="readonly",
            values=["Item Number", "Category / Name"],
            width=18,
        )
        index_sort_combo.grid(row=0, column=5, sticky="w", padx=(6, 14))
        index_sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_index())
        ttk.Button(controls, text="Clear", command=self._clear_index_filters).grid(row=0, column=6)

        tree_frame = ttk.Frame(self.index_tab)
        tree_frame.grid(row=3, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.index_tree = self._create_tree(
            tree_frame,
            columns=[
                "item_no", "item_name", "size", "category", "subcategory",
                "sex", "stock_number", "uom", "source",
            ],
            selectmode="extended",
        )
        self.index_tree.grid(row=0, column=0, sticky="nsew")
        self.index_tree.bind("<<TreeviewSelect>>", self._on_index_selected)
        index_actions = ttk.Frame(self.index_tab)
        index_actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        index_actions.columnconfigure(0, weight=1)
        ttk.Label(index_actions, textvariable=self.index_summary_var).grid(row=0, column=0, sticky="w")
        ttk.Button(
            index_actions,
            text="Add WINGS Item",
            command=self._open_add_wings_item_dialog,
        ).grid(row=0, column=1, padx=(8, 6))
        ttk.Button(
            index_actions,
            text="Add Custom Item",
            command=self._open_add_custom_item_dialog,
        ).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(
            index_actions,
            text="Delete Selected from Index",
            command=self._delete_selected_index_items,
        ).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(
            index_actions,
            text="Restore Hidden Items",
            command=self._restore_hidden_index_items,
        ).grid(row=0, column=4)

        editor = ttk.LabelFrame(self.index_tab, text="Add or Edit Custom Index Item", padding=10)
        editor.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        editor.columnconfigure(1, weight=2)
        editor.columnconfigure(3, weight=1)
        editor.columnconfigure(5, weight=1)
        ttk.Label(editor, text="Equipment Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.index_custom_name_var).grid(row=0, column=1, sticky="ew", padx=(6, 14))
        ttk.Label(editor, text="Uniform / System").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            editor,
            textvariable=self.index_custom_system_var,
            state="readonly",
            values=["BLUES", "OCP", "PTG", "CADET RANK", "ACCOUTREMENTS", "OUTERWEAR", "FOOTWEAR", "OTHER"],
        ).grid(row=0, column=3, sticky="ew", padx=(6, 14))
        ttk.Label(editor, text="Configuration").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            editor,
            textvariable=self.index_custom_configuration_var,
            state="readonly",
            values=["Standard", "Men's", "Women's", "Unisex"],
        ).grid(row=0, column=5, sticky="ew", padx=(6, 0))

        ttk.Label(editor, text="Search Aliases").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(editor, textvariable=self.index_custom_aliases_var).grid(
            row=1, column=1, sticky="ew", padx=(6, 14), pady=(8, 0)
        )
        ttk.Label(editor, text="Size System").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Combobox(
            editor,
            textvariable=self.index_custom_size_system_var,
            state="readonly",
            values=[
                "Apparel Size", "OCP Garment Size", "Women's OCP Garment Size",
                "Unisex OCP Garment Size", "Women's Garment Size", "Shoe Size",
                "Coat Size", "Waist × Inseam", "Neck × Sleeve", "Headgear Size", "One Size",
            ],
        ).grid(row=1, column=3, sticky="ew", padx=(6, 14), pady=(8, 0))
        actions = ttk.Frame(editor)
        actions.grid(row=1, column=4, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Save to Index", command=self._save_custom_index_item).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(actions, text="New / Clear", command=self._clear_custom_index_form).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(actions, text="Delete Selected", command=self._delete_selected_index_items).grid(row=0, column=2)
        ttk.Label(
            editor,
            text="Aliases are optional comma-separated search terms. Saving here does not create inventory.",
            style="Subtitle.TLabel",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))
        editor.grid_remove()
        ttk.Label(
            self.index_tab,
            text=(
                "Custom items use the same detailed fields as WINGS records, receive a LOCAL number, "
                "and stay out of WINGS exports. Adding an Index item does not create inventory."
            ),
            style="Subtitle.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=(8, 0))

    def _build_wings_export_tab(self) -> None:
        self.wings_export_tab.columnconfigure(0, weight=1)
        self.wings_export_tab.rowconfigure(3, weight=1)

        ttk.Label(self.wings_export_tab, text="WINGS Excel Export", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self.wings_export_tab,
            text=(
                "This preview contains only stocked inventory mapped to official WINGS records. Local, "
                "custom, and zero-stock Index rows are excluded. Quantities come from the current A.C.E. inventory."
            ),
            style="Subtitle.TLabel",
            wraplength=1180,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        actions = ttk.Frame(self.wings_export_tab)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, textvariable=self.wings_export_summary_var).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Refresh Preview", command=self.refresh_wings_export).grid(
            row=0, column=1, padx=(8, 6)
        )
        ttk.Button(actions, text="Import WINGS Inventory", command=self._import_wings_inventory).grid(
            row=0, column=2, padx=(0, 6)
        )
        ttk.Button(actions, text="Generate WINGS Excel Spreadsheet", command=self._export_inventory_spreadsheet).grid(
            row=0, column=3
        )

        tree_frame = ttk.Frame(self.wings_export_tab)
        tree_frame.grid(row=3, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.wings_export_tree = self._create_tree(
            tree_frame,
            columns=list(WINGS_COLUMNS),
        )
        self.wings_export_tree.grid(row=0, column=0, sticky="nsew")

    def _build_checkout_tab(self) -> None:
        self.checkout_tab.columnconfigure(0, weight=1)
        self.checkout_tab.columnconfigure(1, weight=1)
        self.checkout_tab.rowconfigure(0, weight=1)

        checkout_frame = ttk.LabelFrame(self.checkout_tab, text="Checkout", padding=12)
        checkout_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        checkout_frame.columnconfigure(0, weight=1)
        checkout_frame.rowconfigure(3, weight=1)

        ttk.Label(checkout_frame, text="Scan Barcode").grid(row=0, column=0, sticky="w")
        checkout_scan_row = ttk.Frame(checkout_frame)
        checkout_scan_row.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        checkout_scan_row.columnconfigure(0, weight=1)
        self.checkout_scan_entry = ttk.Entry(checkout_scan_row, textvariable=self.checkout_scan_var, style="Scan.TEntry")
        self.checkout_scan_entry.grid(row=0, column=0, sticky="ew")
        self.checkout_scan_entry.bind("<Return>", self._queue_checkout_barcode)
        ttk.Label(checkout_scan_row, text="Units To Add").grid(row=0, column=1, padx=(10, 6))
        ttk.Spinbox(checkout_scan_row, from_=1, to=1000, textvariable=self.checkout_qty_var, width=8).grid(
            row=0, column=2, sticky="w"
        )
        ttk.Button(checkout_scan_row, text="Add To List", command=self._queue_checkout_barcode).grid(
            row=0, column=3, padx=(10, 0)
        )

        ttk.Label(checkout_frame, textvariable=self.checkout_summary_var, wraplength=560, justify="left").grid(
            row=2, column=0, sticky="w", pady=(0, 12)
        )

        checkout_queue_frame = ttk.LabelFrame(checkout_frame, text="Checkout List", padding=8)
        checkout_queue_frame.grid(row=3, column=0, sticky="nsew")
        checkout_queue_frame.columnconfigure(0, weight=1)
        checkout_queue_frame.rowconfigure(0, weight=1)
        self.checkout_queue_tree = self._create_tree(
            checkout_queue_frame,
            columns=["barcode_id", "item_name", "category", "variant", "item_type", "available_quantity", "quantity"],
            selectmode="extended",
        )
        self.checkout_queue_tree.grid(row=0, column=0, sticky="nsew")

        checkout_queue_actions = ttk.Frame(checkout_frame)
        checkout_queue_actions.grid(row=4, column=0, sticky="ew", pady=(8, 10))
        for index in range(3):
            checkout_queue_actions.columnconfigure(index, weight=1)
        ttk.Button(checkout_queue_actions, text="Select All", command=lambda: self._select_all_tree_rows(self.checkout_queue_tree)).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(checkout_queue_actions, text="Remove Selected", command=self._remove_selected_checkout_queue).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(checkout_queue_actions, text="Clear List", command=self._clear_checkout_queue).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )

        ttk.Label(checkout_frame, text="Cadet Name").grid(row=5, column=0, sticky="w")
        name_frame = ttk.Frame(checkout_frame)
        name_frame.grid(row=6, column=0, sticky="ew", pady=3)
        name_frame.columnconfigure(0, weight=2)
        name_frame.columnconfigure(1, weight=1)
        name_frame.columnconfigure(2, weight=2)
        ttk.Entry(name_frame, textvariable=self.checkout_last_name_var).grid(row=0, column=0, sticky="ew")
        ttk.Entry(name_frame, textvariable=self.checkout_middle_initial_var, width=5).grid(row=0, column=1, sticky="ew", padx=6)
        self.checkout_first_name_entry = ttk.Entry(name_frame, textvariable=self.checkout_first_name_var)
        self.checkout_first_name_entry.grid(row=0, column=2, sticky="ew")
        ttk.Label(name_frame, text="Last").grid(row=1, column=0, sticky="w")
        ttk.Label(name_frame, text="MI").grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(name_frame, text="First").grid(row=1, column=2, sticky="w")

        ttk.Label(checkout_frame, text="Cadet Email").grid(row=7, column=0, sticky="w")
        ttk.Entry(checkout_frame, textvariable=self.checkout_email_var).grid(row=8, column=0, sticky="ew", pady=3)

        ttk.Label(checkout_frame, text="Checkout Notes").grid(row=9, column=0, sticky="nw", pady=(8, 0))
        self.checkout_notes_text = tk.Text(checkout_frame, height=8, wrap="word")
        self.checkout_notes_text.grid(row=10, column=0, sticky="ew", pady=(6, 0))

        checkout_actions = ttk.Frame(checkout_frame)
        checkout_actions.grid(row=11, column=0, sticky="ew", pady=(12, 0))
        for index in range(3):
            checkout_actions.columnconfigure(index, weight=1)
        ttk.Button(checkout_actions, text="Check Out Queued Items", command=self._submit_checkout).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(checkout_actions, text="Save Cadet", command=self._save_checkout_cadet).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(checkout_actions, text="Reset Checkout", command=self._clear_checkout_form).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )

        return_frame = ttk.LabelFrame(self.checkout_tab, text="Return", padding=12)
        return_frame.grid(row=0, column=1, sticky="nsew")
        return_frame.columnconfigure(0, weight=1)
        return_frame.rowconfigure(3, weight=1)

        ttk.Label(return_frame, text="Scan Barcode").grid(row=0, column=0, sticky="w")
        return_scan_row = ttk.Frame(return_frame)
        return_scan_row.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        return_scan_row.columnconfigure(0, weight=1)
        self.return_scan_entry = ttk.Entry(return_scan_row, textvariable=self.return_scan_var, style="Scan.TEntry")
        self.return_scan_entry.grid(row=0, column=0, sticky="ew")
        self.return_scan_entry.bind("<Return>", self._queue_return_barcode)
        ttk.Label(return_scan_row, text="Units To Add").grid(row=0, column=1, padx=(10, 6))
        ttk.Spinbox(return_scan_row, from_=1, to=1000, textvariable=self.return_qty_var, width=8).grid(
            row=0, column=2, sticky="w"
        )
        ttk.Button(return_scan_row, text="Add To List", command=self._queue_return_barcode).grid(
            row=0, column=3, padx=(10, 0)
        )

        ttk.Label(return_frame, textvariable=self.return_summary_var, wraplength=560, justify="left").grid(
            row=2, column=0, sticky="w", pady=(0, 12)
        )

        return_queue_frame = ttk.LabelFrame(return_frame, text="Return List", padding=8)
        return_queue_frame.grid(row=3, column=0, sticky="nsew")
        return_queue_frame.columnconfigure(0, weight=1)
        return_queue_frame.rowconfigure(0, weight=1)
        self.return_queue_tree = self._create_tree(
            return_queue_frame,
            columns=["barcode_id", "item_name", "open_units", "quantity", "current_holder", "oldest_checkout"],
            selectmode="extended",
        )
        self.return_queue_tree.grid(row=0, column=0, sticky="nsew")

        return_queue_actions = ttk.Frame(return_frame)
        return_queue_actions.grid(row=4, column=0, sticky="ew", pady=(8, 10))
        for index in range(3):
            return_queue_actions.columnconfigure(index, weight=1)
        ttk.Button(return_queue_actions, text="Select All", command=lambda: self._select_all_tree_rows(self.return_queue_tree)).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(return_queue_actions, text="Remove Selected", command=self._remove_selected_return_queue).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(return_queue_actions, text="Clear List", command=self._clear_return_queue).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )

        ttk.Label(return_frame, text="Return / Condition Notes").grid(row=5, column=0, sticky="nw", pady=(8, 0))
        self.return_notes_text = tk.Text(return_frame, height=8, wrap="word")
        self.return_notes_text.grid(row=6, column=0, sticky="ew", pady=(6, 0))

        return_actions = ttk.Frame(return_frame)
        return_actions.grid(row=7, column=0, sticky="ew", pady=(12, 0))
        for index in range(2):
            return_actions.columnconfigure(index, weight=1)
        ttk.Button(return_actions, text="Return Queued Items", command=self._submit_return).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(return_actions, text="Reset Return", command=self._clear_return_form).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )

    def _build_barcode_directory_tab(self) -> None:
        self.barcode_directory_tab.columnconfigure(0, weight=1)
        self.barcode_directory_tab.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.barcode_directory_tab)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Search").grid(row=0, column=0, sticky="w")
        directory_search_entry = ttk.Entry(controls, textvariable=self.directory_search_var)
        directory_search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        directory_search_entry.bind("<Return>", lambda _event: self.refresh_barcode_directory())

        ttk.Label(controls, text="Status").grid(row=0, column=2, sticky="w")
        directory_status_combo = ttk.Combobox(
            controls,
            textvariable=self.directory_status_filter_var,
            state="readonly",
            values=["All", "Available", "Checked Out", "Retired", "Lost"],
            width=16,
        )
        directory_status_combo.grid(row=0, column=3, sticky="w", padx=(6, 10))
        directory_status_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_barcode_directory())

        ttk.Button(controls, text="Refresh", command=self.refresh_barcode_directory).grid(row=0, column=4, padx=(0, 6))
        ttk.Button(controls, text="Copy Selected Barcode(s)", command=self._copy_selected_directory_barcodes).grid(
            row=0, column=5, padx=(0, 6)
        )
        ttk.Button(controls, text="Copy All Visible", command=self._copy_all_visible_directory_barcodes).grid(
            row=0, column=6, padx=(0, 6)
        )
        ttk.Button(controls, text="Export WINGS Spreadsheet", command=self._export_inventory_spreadsheet).grid(
            row=0, column=7
        )

        tree_frame = ttk.LabelFrame(self.barcode_directory_tab, text="All Current Barcode IDs", padding=10)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.barcode_directory_tree = self._create_tree(
            tree_frame,
            columns=[
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "status",
                "total_quantity",
                "available_quantity",
            ],
            selectmode="extended",
        )
        self.barcode_directory_tree.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            self.barcode_directory_tab,
            textvariable=self.barcode_directory_summary_var,
            wraplength=1180,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_cadets_tab(self) -> None:
        self.cadets_tab.columnconfigure(0, weight=1)
        self.cadets_tab.columnconfigure(1, weight=2)
        self.cadets_tab.rowconfigure(1, weight=1)

        form_frame = ttk.LabelFrame(self.cadets_tab, text="Save / Update Cadet", padding=12)
        form_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Cadet Name").grid(row=0, column=0, sticky="w")
        cadet_name_frame = ttk.Frame(form_frame)
        cadet_name_frame.grid(row=0, column=1, sticky="ew", pady=3, padx=(8, 12))
        cadet_name_frame.columnconfigure(0, weight=2)
        cadet_name_frame.columnconfigure(1, weight=1)
        cadet_name_frame.columnconfigure(2, weight=2)
        ttk.Entry(cadet_name_frame, textvariable=self.cadet_last_name_var).grid(row=0, column=0, sticky="ew")
        ttk.Entry(cadet_name_frame, textvariable=self.cadet_middle_initial_var, width=5).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Entry(cadet_name_frame, textvariable=self.cadet_first_name_var).grid(row=0, column=2, sticky="ew")
        ttk.Label(cadet_name_frame, text="Last").grid(row=1, column=0, sticky="w")
        ttk.Label(cadet_name_frame, text="MI").grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(cadet_name_frame, text="First").grid(row=1, column=2, sticky="w")

        ttk.Label(form_frame, text="Email").grid(row=0, column=2, sticky="w")
        ttk.Entry(form_frame, textvariable=self.cadet_form_email_var).grid(row=0, column=3, sticky="ew", pady=3, padx=(8, 12))
        form_frame.columnconfigure(1, weight=2)
        form_frame.columnconfigure(3, weight=1)

        ttk.Button(form_frame, text="Save / Update Cadet", command=self._save_cadet).grid(row=0, column=4, padx=(0, 6))
        ttk.Button(form_frame, text="Load Into Checkout", command=self._load_selected_cadet_into_checkout).grid(row=0, column=5, padx=(0, 6))
        ttk.Button(form_frame, text="Delete Cadet", command=self._delete_selected_cadet).grid(row=0, column=6, padx=(0, 6))
        ttk.Button(form_frame, text="Export Cadet History", command=self._export_selected_cadet_history).grid(row=0, column=7, padx=(0, 6))
        ttk.Button(form_frame, text="Clear Cadet Form", command=self._clear_cadet_form).grid(row=0, column=8)

        left_frame = ttk.LabelFrame(self.cadets_tab, text="Saved Cadets", padding=10)
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left_frame.columnconfigure(1, weight=1)
        left_frame.rowconfigure(1, weight=1)

        ttk.Label(left_frame, text="Search").grid(row=0, column=0, sticky="w")
        cadet_search_entry = ttk.Entry(left_frame, textvariable=self.cadet_search_var)
        cadet_search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        cadet_search_entry.bind("<Return>", lambda _event: self.refresh_cadets())
        ttk.Label(left_frame, text="Sort By").grid(row=0, column=2, sticky="w")
        cadet_sort_combo = ttk.Combobox(
            left_frame,
            textvariable=self.cadet_sort_var,
            state="readonly",
            values=["ID", "Alphabetical"],
            width=14,
        )
        cadet_sort_combo.grid(row=0, column=3, sticky="w", padx=(6, 10))
        cadet_sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_cadets())
        ttk.Button(left_frame, text="Refresh", command=self.refresh_cadets).grid(row=0, column=4)

        cadet_tree_frame = ttk.Frame(left_frame)
        cadet_tree_frame.grid(row=1, column=0, columnspan=5, sticky="nsew", pady=(10, 0))
        cadet_tree_frame.columnconfigure(0, weight=1)
        cadet_tree_frame.rowconfigure(0, weight=1)
        self.cadet_tree = self._create_tree(
            cadet_tree_frame,
            columns=["cadet_id", "full_name", "email", "open_items", "total_transactions", "last_checkout_time"],
        )
        self.cadet_tree.grid(row=0, column=0, sticky="nsew")
        self.cadet_tree.bind("<<TreeviewSelect>>", self._on_cadet_selected)

        right_frame = ttk.LabelFrame(self.cadets_tab, text="Cadet Issue History", padding=10)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        right_frame.rowconfigure(3, weight=1)

        ttk.Label(right_frame, textvariable=self.cadet_summary_var, wraplength=760, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        current_frame = ttk.LabelFrame(right_frame, text="Currently Checked Out", padding=8)
        current_frame.grid(row=1, column=0, sticky="nsew")
        current_frame.columnconfigure(0, weight=1)
        current_frame.rowconfigure(0, weight=1)
        self.cadet_current_tree = self._create_tree(
            current_frame,
            columns=[
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "approved_by_role",
                "approved_by_name",
                "checkout_time",
            ],
        )
        self.cadet_current_tree.grid(row=0, column=0, sticky="nsew")

        history_actions = ttk.Frame(right_frame)
        history_actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        history_actions.columnconfigure(1, weight=1)
        ttk.Button(
            history_actions,
            text="View Selected Transaction",
            command=self._view_selected_cadet_history_entry,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            history_actions,
            text="Use the bottom scroll bar to read across long transaction rows.",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

        history_frame = ttk.LabelFrame(right_frame, text="Full Transaction History", padding=8)
        history_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        self.cadet_history_tree = self._create_tree(
            history_frame,
            columns=[
                "transaction_id",
                "barcode_id",
                "item_name",
                "approved_by_role",
                "approved_by_name",
                "checkout_time",
                "return_time",
                "return_approved_by_role",
                "return_approved_by_name",
                "condition_notes",
            ],
        )
        self.cadet_history_tree.grid(row=0, column=0, sticky="nsew")
        self.cadet_history_tree.bind("<Double-1>", lambda _event: self._view_selected_cadet_history_entry())

    def _build_reports_tab(self) -> None:
        self.reports_tab.columnconfigure(0, weight=1)
        self.reports_tab.rowconfigure(1, weight=1)

        top = ttk.Frame(self.reports_tab)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Report").grid(row=0, column=0, sticky="w")
        report_combo = ttk.Combobox(
            top,
            textvariable=self.report_type_var,
            state="readonly",
            values=["Checked Out Items", "Transaction History"],
            width=24,
        )
        report_combo.grid(row=0, column=1, sticky="w", padx=(6, 12))
        report_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_report())

        ttk.Button(top, text="Refresh Report", command=self.refresh_report).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(top, text="Export CSV", command=self._export_report).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(top, text="Export WINGS Spreadsheet", command=self._export_inventory_spreadsheet).grid(row=0, column=4)

        report_frame = ttk.LabelFrame(self.reports_tab, text="Report Results", padding=10)
        report_frame.grid(row=1, column=0, sticky="nsew")
        report_frame.columnconfigure(0, weight=1)
        report_frame.rowconfigure(0, weight=1)

        self.report_tree = self._create_tree(report_frame, columns=[])
        self.report_tree.grid(row=0, column=0, sticky="nsew")
        ttk.Label(report_frame, textvariable=self.report_summary_var, wraplength=960).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

    def _build_settings_tab(self) -> None:
        self.settings_tab.columnconfigure(0, weight=1)
        self.settings_tab.rowconfigure(2, weight=1)

        frame = ttk.LabelFrame(self.settings_tab, text="Application Settings", padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Keep the database on the flash drive path you want to carry between laptops.",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Organization Name").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.settings_org_name_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frame, text="Database File").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.settings_db_path_var).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Browse", command=self._choose_database_path).grid(row=2, column=2, padx=(8, 0))

        ttk.Label(frame, text="Protected Backup Folder").grid(row=3, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.settings_protected_backup_var).grid(
            row=3, column=1, sticky="ew", pady=3
        )
        ttk.Button(frame, text="Choose or Create", command=self._choose_protected_backup_for_settings).grid(
            row=3, column=2, padx=(8, 0)
        )
        ttk.Label(
            frame,
            text="Recommended: choose a folder on a different drive, this computer, or OneDrive so backups survive USB failure.",
            style="Subtitle.TLabel",
            wraplength=780,
        ).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 4))

        ttk.Label(frame, text="Backup Every X Writes").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(frame, from_=1, to=1000, textvariable=self.settings_backup_interval_var, width=10).grid(
            row=5, column=1, sticky="w", pady=3
        )
        ttk.Label(
            frame,
            text="A.C.E. keeps the newest 10 compressed copies in both the portable and protected locations.",
            style="Subtitle.TLabel",
        ).grid(row=5, column=2, sticky="w", padx=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for index in range(4):
            buttons.columnconfigure(index, weight=1)
        ttk.Button(buttons, text="Save Settings", command=self._save_settings).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(buttons, text="Create Backup Now", command=self._manual_backup).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(buttons, text="Instructions Manual", command=self._show_instructions_manual).grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )
        ttk.Button(buttons, text="Credits", command=self._show_credits).grid(
            row=0, column=3, sticky="ew", padx=(4, 0)
        )

        security_frame = ttk.LabelFrame(self.settings_tab, text="Admin Security", padding=12)
        security_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        security_frame.columnconfigure(1, weight=1)
        security_frame.columnconfigure(3, weight=1)

        ttk.Label(security_frame, text="Current Session").grid(row=0, column=0, sticky="w")
        ttk.Label(security_frame, textvariable=self.current_admin_var, style="Subtitle.TLabel").grid(
            row=0, column=1, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(security_frame, text="Sort By").grid(row=0, column=3, sticky="e", pady=(0, 8))
        admin_sort_combo = ttk.Combobox(
            security_frame,
            textvariable=self.admin_sort_var,
            state="readonly",
            values=["ID", "Alphabetical"],
            width=14,
        )
        admin_sort_combo.grid(row=0, column=4, sticky="w", pady=(0, 8))
        admin_sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_admin_codes())

        ttk.Label(security_frame, text="Admin Name").grid(row=1, column=0, sticky="w")
        ttk.Entry(security_frame, textvariable=self.admin_display_name_var).grid(row=1, column=1, sticky="ew", padx=(8, 12), pady=3)

        ttk.Label(security_frame, text="Admin Code").grid(row=1, column=2, sticky="w")
        admin_code_frame = ttk.Frame(security_frame)
        admin_code_frame.grid(row=1, column=3, sticky="ew", padx=(8, 12), pady=3)
        admin_code_frame.columnconfigure(0, weight=1)
        self.admin_code_entry = ttk.Entry(admin_code_frame, textvariable=self.admin_code_var, show="*")
        self.admin_code_entry.grid(row=0, column=0, sticky="ew")
        self.admin_code_toggle_button = ttk.Button(
            admin_code_frame,
            textvariable=self.admin_code_toggle_text_var,
            command=self._toggle_settings_admin_code_visibility,
            width=7,
        )
        self.admin_code_toggle_button.grid(row=0, column=1, padx=(6, 0))

        admin_buttons = ttk.Frame(security_frame)
        admin_buttons.grid(row=1, column=4, sticky="e")
        for index in range(4):
            admin_buttons.columnconfigure(index, weight=1)
        ttk.Button(admin_buttons, text="Save Admin", command=self._save_admin_code).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(admin_buttons, text="Deactivate", command=self._deactivate_selected_admin_code).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(admin_buttons, text="Delete Admin", command=self._delete_selected_admin_code).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(admin_buttons, text="Switch Admin", command=self._switch_admin).grid(row=0, column=3)

        admin_tree_frame = ttk.Frame(security_frame)
        admin_tree_frame.grid(row=2, column=0, columnspan=5, sticky="nsew", pady=(10, 0))
        admin_tree_frame.columnconfigure(0, weight=1)
        admin_tree_frame.rowconfigure(0, weight=1)
        security_frame.rowconfigure(2, weight=1)

        self.admin_tree = self._create_tree(
            admin_tree_frame,
            columns=["admin_id", "display_name", "role", "is_active", "updated_at"],
        )
        self.admin_tree.grid(row=0, column=0, sticky="nsew")
        self.admin_tree.bind("<<TreeviewSelect>>", self._on_admin_selected)
        ttk.Label(security_frame, textvariable=self.admin_summary_var, wraplength=1180).grid(
            row=3, column=0, columnspan=5, sticky="w", pady=(8, 0)
        )

        transfer_frame = ttk.LabelFrame(self.settings_tab, text="Transfer Device", padding=12)
        transfer_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        transfer_frame.columnconfigure(0, weight=1)
        ttk.Label(
            transfer_frame,
            text="Build a single transfer EXE that carries the current app snapshot, settings, and inventory database to another Windows device.",
            wraplength=1180,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(transfer_frame, text="Create Transfer Device EXE", command=self._create_transfer_device).grid(
            row=1, column=0, sticky="e", pady=(10, 0)
        )

    def refresh_all_views(self) -> None:
        self._populate_catalog_values()
        self.refresh_dashboard()
        self.refresh_items_tree()
        self.refresh_label_library()
        self.refresh_index()
        self.refresh_wings_export()
        self.refresh_barcode_directory()
        self.refresh_cadets()
        self.refresh_report()
        self.refresh_admin_codes()
        self._update_generator_preview()
        self._set_status(f"Database: {self.settings.database_path}")

    def refresh_index(self) -> None:
        selected_category = self.index_system_var.get().strip() or "All"
        rows = self.service.list_wings_catalog(
            search=self.index_search_var.get(),
            category=selected_category,
            sort_by=self.index_sort_var.get(),
        )

        custom_items = self.service.list_custom_index_items()
        self.custom_index_cache = {int(row["index_item_id"]): row for row in custom_items}
        for custom in custom_items:
            if selected_category != "All":
                continue
            configuration = str(custom["configuration"])
            equipment_name = str(custom["equipment_name"])
            if configuration != "Standard":
                equipment_name = f"{equipment_name} - {configuration}"
            query_words = [word for word in self.index_search_var.get().casefold().split() if word]
            search_text = " ".join(
                [
                    equipment_name,
                    str(custom["uniform_system"]),
                    str(custom["size_system"]),
                    str(custom["search_aliases"]),
                ]
            ).casefold()
            if not all(word in search_text for word in query_words):
                continue
            rows.append(
                {
                    "item_no": "",
                    "item_name": equipment_name,
                    "size": str(custom["size_system"]),
                    "category": str(custom["uniform_system"]),
                    "subcategory": "Custom",
                    "sex": configuration,
                    "stock_number": "",
                    "uom": "",
                    "source": "Custom",
                }
            )

        if self.index_sort_var.get() == "Item Number":
            rows.sort(
                key=lambda row: (
                    not str(row.get("item_no", "")).isdigit(),
                    int(row["item_no"]) if str(row.get("item_no", "")).isdigit() else 0,
                    str(row.get("item_name", "")),
                )
            )
        else:
            rows.sort(
                key=lambda row: (
                    str(row.get("category", "")),
                    str(row.get("subcategory", "")),
                    str(row.get("item_name", "")),
                    str(row.get("size", "")),
                )
            )

        self._populate_tree(
            self.index_tree,
            [
                "item_no", "item_name", "size", "category", "subcategory",
                "sex", "stock_number", "uom", "source",
            ],
            rows,
        )
        hidden_count = self.service.count_hidden_index_items()
        official_count = self.service.count_wings_catalog_items()
        self.index_summary_var.set(
            f"Showing {len(rows)} records | {hidden_count} hidden | "
            f"{official_count} official WINGS items available for compliant exports."
        )

    def refresh_wings_export(self) -> None:
        rows = self.service.list_wings_export_rows()
        self._populate_tree(self.wings_export_tree, list(WINGS_COLUMNS), rows)
        total_units = sum(int(row["Total in Inventory"]) for row in rows)
        issued_units = sum(int(row["Qty Issued"]) for row in rows)
        available_units = sum(int(row["Qty Available"]) for row in rows)
        self.wings_export_summary_var.set(
            f"{len(rows)} official WINGS rows | Total {total_units} | "
            f"Issued {issued_units} | Available {available_units}"
        )


    def _clear_index_filters(self) -> None:
        self.index_search_var.set("")
        self.index_system_var.set("All")
        self.index_sort_var.set("Item Number")
        self.refresh_index()

    def _on_index_selected(self, _event: tk.Event | None = None) -> None:
        selected = self._selected_tree_row(self.index_tree)
        if not selected or selected.get("source") != "Custom":
            self._clear_custom_index_form()
            return
        display_name = selected.get("item_name", "")
        for index_id, row in self.custom_index_cache.items():
            configuration = str(row["configuration"])
            candidate = str(row["equipment_name"])
            if configuration != "Standard":
                candidate = f"{candidate} - {configuration}"
            if candidate == display_name:
                self.selected_custom_index_id = index_id
                self.index_custom_name_var.set(str(row["equipment_name"]))
                self.index_custom_system_var.set(str(row["uniform_system"]))
                self.index_custom_configuration_var.set(configuration)
                self.index_custom_size_system_var.set(str(row["size_system"]))
                self.index_custom_aliases_var.set(str(row["search_aliases"]))
                return

    def _save_custom_index_item(self) -> None:
        self._run_action(
            lambda: self.service.save_custom_index_item(
                equipment_name=self.index_custom_name_var.get(),
                uniform_system=self.index_custom_system_var.get(),
                configuration=self.index_custom_configuration_var.get(),
                size_system=self.index_custom_size_system_var.get(),
                search_aliases=self.index_custom_aliases_var.get(),
                index_item_id=self.selected_custom_index_id,
            ),
            success_message="Custom equipment saved to the Index and Smart Search.",
            on_success=lambda _result: (self._clear_custom_index_form(), self.refresh_index()),
        )

    def _delete_custom_index_item(self) -> None:
        if self.selected_custom_index_id is None:
            self._show_error("Select a custom Index item first. Built-in items cannot be deleted.")
            return
        if not messagebox.askyesno(
            "Delete Custom Index Item",
            "Delete this custom item from the Index and Smart Search? Existing inventory is not affected.",
            parent=self,
        ):
            return
        index_id = self.selected_custom_index_id
        self._run_action(
            lambda: self.service.delete_custom_index_item(index_id),
            success_message="Custom Index item deleted.",
            on_success=lambda _result: (self._clear_custom_index_form(), self.refresh_index()),
        )

    def _open_add_custom_item_dialog(self) -> None:
        self._open_add_wings_item_dialog(custom=True)

    def _open_add_wings_item_dialog(self, *, custom: bool = False) -> None:
        window = tk.Toplevel(self)
        window.title("Add Custom Catalog Item" if custom else "Add WINGS Catalog Item")
        window.transient(self)
        window.grab_set()
        window.minsize(820, 360)
        self.update_idletasks()
        dialog_width = 940
        dialog_height = 390
        dialog_x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog_width) // 2)
        dialog_y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog_height) // 2)
        window.geometry(f"{dialog_width}x{dialog_height}+{dialog_x}+{dialog_y}")
        if self.window_icon_image is not None:
            window.iconphoto(True, self.window_icon_image)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        self._apply_window_icon_choice(self.current_window_icon_key or self._random_window_icon_key())

        form = ttk.LabelFrame(
            window,
            text="Detailed Custom Item" if custom else "Official WINGS Item Details",
            padding=14,
        )
        form.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        item_no_var = tk.StringVar(window, value="Assigned automatically" if custom else "")
        item_name_var = tk.StringVar(window)
        size_var = tk.StringVar(window)
        category_var = tk.StringVar(window)
        subcategory_var = tk.StringVar(window)
        sex_var = tk.StringVar(window)
        stock_number_var = tk.StringVar(window)
        uom_var = tk.StringVar(window, value="EA")
        source_var = tk.StringVar(window, value="Local Custom Item" if custom else "WINGS Manual Entry")

        ttk.Label(form, text="Item Number").grid(row=0, column=0, sticky="w")
        item_no_entry = ttk.Entry(form, textvariable=item_no_var, state="disabled" if custom else "normal")
        item_no_entry.grid(row=0, column=1, sticky="ew", padx=(8, 18), pady=4)
        ttk.Label(form, text="Item Name").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=item_name_var).grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(form, text="Size").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=size_var).grid(row=1, column=1, sticky="ew", padx=(8, 18), pady=4)
        ttk.Label(form, text="Category").grid(row=1, column=2, sticky="w")
        category_combo = ttk.Combobox(
            form,
            textvariable=category_var,
            values=self.service.list_catalog_field_values("category"),
        )
        category_combo.grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(form, text="Subcategory").grid(row=2, column=0, sticky="w")
        subcategory_combo = ttk.Combobox(
            form,
            textvariable=subcategory_var,
            values=self.service.list_catalog_field_values("subcategory"),
        )
        subcategory_combo.grid(row=2, column=1, sticky="ew", padx=(8, 18), pady=4)

        def filter_combo_values(combo: ttk.Combobox, values: list[str]) -> None:
            typed = combo.get().strip().casefold()
            matches = [value for value in values if typed in value.casefold()]
            combo.configure(values=matches or values)

        def refresh_category_values(_event: tk.Event | None = None) -> None:
            filter_combo_values(
                category_combo,
                self.service.list_catalog_field_values("category"),
            )

        def refresh_subcategory_values(_event: tk.Event | None = None) -> None:
            filter_combo_values(
                subcategory_combo,
                self.service.list_catalog_field_values(
                    "subcategory", category=category_var.get()
                ),
            )

        category_combo.bind("<FocusIn>", refresh_category_values)
        category_combo.bind("<KeyRelease>", refresh_category_values)
        category_combo.bind("<<ComboboxSelected>>", refresh_subcategory_values)
        subcategory_combo.bind("<FocusIn>", refresh_subcategory_values)
        subcategory_combo.bind("<KeyRelease>", refresh_subcategory_values)
        ttk.Label(form, text="Sex").grid(row=2, column=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=sex_var,
            state="readonly",
            values=["", "M", "F", "U"],
        ).grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(form, text="Stock Number").grid(row=3, column=0, sticky="w")
        ttk.Entry(form, textvariable=stock_number_var).grid(row=3, column=1, sticky="ew", padx=(8, 18), pady=4)
        ttk.Label(form, text="UoM").grid(row=3, column=2, sticky="w")
        ttk.Combobox(
            form,
            textvariable=uom_var,
            values=["EA", "PR"],
        ).grid(row=3, column=3, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(form, text="Source").grid(row=4, column=0, sticky="w")
        ttk.Entry(form, textvariable=source_var).grid(
            row=4, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4
        )
        ttk.Label(
            form,
            text=(
                (
                    "A.C.E. assigns a LOCAL number so this item cannot be mistaken for an official WINGS record. "
                    "Category and subcategory suggestions come from values already in use. New values are also allowed. "
                    "The item remains excluded from WINGS exports."
                )
                if custom
                else (
                    "Enter the WINGS item number with or without leading zeros. Size, sex, and stock number "
                    "may be blank only when WINGS does not provide them. Go to Writeoffs is added automatically."
                )
            ),
            style="Subtitle.TLabel",
            wraplength=850,
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 8))

        buttons = ttk.Frame(form)
        buttons.grid(row=6, column=0, columnspan=4, sticky="e", pady=(8, 0))

        def save_wings_item() -> None:
            try:
                fields = {
                    "item_name": item_name_var.get(),
                    "size": size_var.get(),
                    "category": category_var.get(),
                    "subcategory": subcategory_var.get(),
                    "sex": sex_var.get(),
                    "stock_number": stock_number_var.get(),
                    "uom": uom_var.get(),
                    "source": source_var.get(),
                }
                if custom:
                    saved_item_no = self.service.add_custom_catalog_item(**fields)
                else:
                    saved_item_no = self.service.add_wings_catalog_item(item_no=item_no_var.get(), **fields)
            except InventoryError as exc:
                messagebox.showerror("WINGS Item Error", str(exc), parent=window)
                return
            except Exception as exc:  # pragma: no cover - defensive GUI handling
                messagebox.showerror("WINGS Item Error", f"Unexpected error: {exc}", parent=window)
                return
            window.destroy()
            self.refresh_index()
            item_kind = "custom" if custom else "WINGS"
            self._set_status(f"Added {item_kind} catalog item {saved_item_no}.")
            self._show_info(f"{item_kind.title()} item {saved_item_no} was added to the Index and Quick Find.")

        ttk.Button(buttons, text="Cancel", command=window.destroy).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(
            buttons,
            text="Add Custom Item" if custom else "Add WINGS Item",
            command=save_wings_item,
        ).grid(row=0, column=1)
        window.lift()
        window.after(50, window.focus_force if custom else item_no_entry.focus_force)

    def _delete_selected_index_items(self) -> None:
        selections = self.index_tree.selection()
        if not selections:
            self._show_error("Select one or more Index rows first.")
            return

        item_nos: list[str] = []
        custom_ids: list[int] = []
        for item_id in selections:
            values = self.index_tree.item(item_id, "values")
            columns = list(self.index_tree["columns"])
            row = {
                str(column): str(values[index]) if index < len(values) else ""
                for index, column in enumerate(columns)
            }
            if row.get("source") == "Custom":
                display_name = row.get("item_name", "")
                for index_id, custom in self.custom_index_cache.items():
                    configuration = str(custom["configuration"])
                    candidate = str(custom["equipment_name"])
                    if configuration != "Standard":
                        candidate = f"{candidate} - {configuration}"
                    if candidate == display_name:
                        custom_ids.append(index_id)
                        break
            elif row.get("item_no"):
                item_nos.append(row["item_no"])

        selected_count = len(set(item_nos)) + len(set(custom_ids))
        if not selected_count:
            self._show_error("The selected Index rows could not be identified.")
            return
        if not messagebox.askyesno(
            "Delete Selected Index Items",
            (
                f"Remove {selected_count} selected item(s) from the Index?\n\n"
                "Official WINGS items will be hidden, not destroyed, and can be restored. "
                "Local and legacy custom items will be deleted. Existing inventory and WINGS exports are not affected."
            ),
            parent=self,
        ):
            return

        self._run_action(
            lambda: self.service.remove_index_entries(
                item_nos=item_nos,
                custom_index_ids=custom_ids,
            ),
            success_message=f"Removed {selected_count} selected item(s) from the Index.",
            on_success=lambda _result: (self._clear_custom_index_form(), self.refresh_index()),
        )

    def _restore_hidden_index_items(self) -> None:
        hidden_count = self.service.count_hidden_index_items()
        if hidden_count == 0:
            self._show_info("There are no hidden Index items to restore.")
            return
        if not messagebox.askyesno(
            "Restore Hidden Index Items",
            f"Restore all {hidden_count} hidden catalog item(s) to the Index?",
            parent=self,
        ):
            return
        self._run_action(
            self.service.restore_hidden_index_items,
            success_message=f"Restored {hidden_count} hidden item(s) to the Index.",
            on_success=lambda _result: self.refresh_index(),
        )

    def _clear_custom_index_form(self) -> None:
        self.selected_custom_index_id = None
        self.index_custom_name_var.set("")
        self.index_custom_system_var.set("OTHER")
        self.index_custom_configuration_var.set("Standard")
        self.index_custom_size_system_var.set("Apparel Size")
        self.index_custom_aliases_var.set("")

    def refresh_dashboard(self) -> None:
        summary = self.service.dashboard_summary()
        for key, variable in self.summary_vars.items():
            variable.set(str(summary[key]))
        self._populate_tree(
            self.dashboard_activity_tree,
            ["event_time", "action", "barcode_id", "item_name", "cadet_name", "cadet_email"],
            summary["recent_activity"],
        )

    def refresh_items_tree(self) -> None:
        rows = self.service.list_items(
            search=self.item_search_var.get(),
            status_filter=self.item_status_filter_var.get(),
        )
        self.item_cache = {row["barcode_id"]: row for row in rows}
        self._populate_tree(
            self.items_tree,
            [
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "status",
                "total_quantity",
                "available_quantity",
                "notes",
            ],
            rows,
        )

    def refresh_report(self) -> None:
        columns, rows = self.service.get_report(self.report_type_var.get())
        self.report_columns = columns
        self.report_rows = rows
        self._populate_tree(self.report_tree, columns, rows)
        self.report_summary_var.set(f"Showing {len(rows)} row(s) for {self.report_type_var.get()}.")

    def refresh_label_library(self) -> None:
        selected_ids = self._selected_label_barcode_ids() if hasattr(self, "label_library_tree") else []
        rows = self.service.list_label_records(
            search=self.label_search_var.get(),
            status_filter=self.label_status_filter_var.get(),
        )
        for row in rows:
            barcode_id = str(row["barcode_id"]).upper()
            row["print_copies"] = self.label_print_quantity_cache.get(barcode_id, 1)
        self._populate_tree(
            self.label_library_tree,
            ["barcode_id", "item_name", "category", "variant", "item_type", "status", "total_quantity", "print_copies"],
            rows,
        )
        if selected_ids:
            surviving_ids = [barcode_id for barcode_id in selected_ids if barcode_id in {str(row["barcode_id"]) for row in rows}]
            if surviving_ids:
                self.label_library_tree.selection_set(surviving_ids)
        self._on_label_library_selected()

    def _selected_label_barcode_ids(self) -> list[str]:
        if not hasattr(self, "label_library_tree"):
            return []
        return [item_id for item_id in self.label_library_tree.selection() if item_id]

    def _on_label_library_selected(self, _event: tk.Event | None = None) -> None:
        rows = len(self.label_library_tree.get_children()) if hasattr(self, "label_library_tree") else 0
        selected_ids = self._selected_label_barcode_ids()
        selected = len(selected_ids)
        total_labels = sum(self.label_print_quantity_cache.get(barcode_id.upper(), 1) for barcode_id in selected_ids)
        if selected_ids:
            first_selected = selected_ids[0].upper()
            self.label_selected_copies_var.set(str(self.label_print_quantity_cache.get(first_selected, 1)))
        if selected:
            self.label_library_summary_var.set(
                f"Showing {rows} label record(s). {selected} selected for targeted PDF export, totaling {total_labels} label(s). Files are stored in {self.settings.label_dir}"
            )
        else:
            self.label_selected_copies_var.set("1")
            self.label_library_summary_var.set(
                f"Showing {rows} label record(s). Set print copies, select specific rows, or export the full filtered sheet from {self.settings.label_dir}."
            )

    def refresh_barcode_directory(self) -> None:
        rows = self.service.list_items(
            search=self.directory_search_var.get(),
            status_filter=self.directory_status_filter_var.get(),
        )
        self.barcode_directory_cache = {str(row["barcode_id"]).upper(): row for row in rows}
        self._populate_tree(
            self.barcode_directory_tree,
            [
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "status",
                "total_quantity",
                "available_quantity",
            ],
            rows,
        )
        self.barcode_directory_summary_var.set(
            f"Showing {len(rows)} barcode line(s). Select rows to copy barcodes for manual checkout or return entry."
        )

    def _selected_label_quantity_map(self) -> dict[str, int]:
        return {
            barcode_id.upper(): self.label_print_quantity_cache.get(barcode_id.upper(), 1)
            for barcode_id in self._selected_label_barcode_ids()
        }

    def _apply_selected_label_copies(self) -> None:
        selected_ids = self._selected_label_barcode_ids()
        if not selected_ids:
            self._show_error("Select one or more barcode rows in the central label library first.")
            return
        try:
            copies = max(1, int(self.label_selected_copies_var.get()))
        except ValueError:
            self._show_error("Selected print copies must be a whole number.")
            return

        for barcode_id in selected_ids:
            self.label_print_quantity_cache[barcode_id.upper()] = copies
        self.refresh_label_library()

    def _reset_selected_label_copies(self) -> None:
        selected_ids = self._selected_label_barcode_ids()
        if not selected_ids:
            self._show_error("Select one or more barcode rows in the central label library first.")
            return
        for barcode_id in selected_ids:
            self.label_print_quantity_cache[barcode_id.upper()] = 1
        self.label_selected_copies_var.set("1")
        self.refresh_label_library()

    def refresh_cadets(self) -> None:
        rows = self.service.list_cadets(search=self.cadet_search_var.get())
        rows = self._sort_cadet_rows(rows)
        self.cadet_cache = {int(row["cadet_id"]): row for row in rows}
        self._populate_tree(
            self.cadet_tree,
            ["cadet_id", "full_name", "email", "open_items", "total_transactions", "last_checkout_time"],
            rows,
        )
        if self.selected_cadet_id and self.selected_cadet_id in self.cadet_cache:
            self._load_cadet_details(self.selected_cadet_id)
        elif self.selected_cadet_id and self.selected_cadet_id not in self.cadet_cache:
            self._clear_cadet_form()
        elif not rows:
            self.selected_cadet_id = None
            self.cadet_summary_var.set("Select or save a cadet to view issued items.")
            self._populate_tree(
                self.cadet_current_tree,
                [
                    "barcode_id",
                    "item_name",
                    "category",
                    "variant",
                    "item_type",
                    "approved_by_role",
                    "approved_by_name",
                    "checkout_time",
                ],
                [],
            )
            self._populate_tree(
                self.cadet_history_tree,
                [
                    "transaction_id",
                    "barcode_id",
                    "item_name",
                    "approved_by_role",
                    "approved_by_name",
                    "checkout_time",
                    "return_time",
                    "return_approved_by_role",
                    "return_approved_by_name",
                    "condition_notes",
                ],
                [],
            )

    def refresh_admin_codes(self) -> None:
        rows = self.service.list_admin_codes()
        rows = self._sort_admin_rows(rows)
        self.admin_cache = {str(row["admin_id"]): row for row in rows}
        if hasattr(self, "admin_tree"):
            self._populate_tree(
                self.admin_tree,
                ["admin_id", "display_name", "role", "is_active", "updated_at"],
                rows,
            )
            if self.selected_admin_id is not None and str(self.selected_admin_id) in self.admin_cache:
                self.admin_tree.selection_set(str(self.selected_admin_id))
                self._load_selected_admin_code_if_authorized(show_error=False)
        active_count = sum(1 for row in rows if str(row.get("is_active", 1)) in {"1", "True", "true"} and str(row["admin_id"]) != "MASTER")
        if self.selected_admin_id is None or str(self.selected_admin_id) not in self.admin_cache:
            self.admin_summary_var.set(
            f"Cadre code Det005 signs in as CADRE. {active_count} custom admin code(s) are currently active."
            )

    def _sort_cadet_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sort_mode = self.cadet_sort_var.get().strip() or "ID"
        if sort_mode == "Alphabetical":
            return sorted(
                rows,
                key=lambda row: (
                    str(row.get("full_name") or "").lower(),
                    str(row.get("email") or "").lower(),
                    int(row.get("cadet_id") or 0),
                ),
            )
        return sorted(rows, key=lambda row: int(row.get("cadet_id") or 0))

    def _sort_admin_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sort_mode = self.admin_sort_var.get().strip() or "ID"
        master_rows = [row for row in rows if str(row.get("admin_id")) == "MASTER"]
        normal_rows = [row for row in rows if str(row.get("admin_id")) != "MASTER"]
        if sort_mode == "Alphabetical":
            normal_rows = sorted(
                normal_rows,
                key=lambda row: (
                    str(row.get("display_name") or "").lower(),
                    str(row.get("role") or "").lower(),
                    int(row.get("admin_id") or 0),
                ),
            )
        else:
            normal_rows = sorted(normal_rows, key=lambda row: int(row.get("admin_id") or 0))
        return master_rows + normal_rows

    def _begin_startup_sequence(self) -> None:
        if not self._play_startup_splash():
            self._authenticate_admin_startup()

    def _play_startup_splash(self) -> bool:
        gif_path = self._startup_animation_path()
        sound_path = self._startup_sound_path()
        if gif_path is None or sound_path is None:
            return False

        try:
            self.startup_frames, raw_frame_durations = self._load_startup_animation(gif_path)
            sound_duration_ms = self._wav_duration_ms(sound_path)
        except Exception:
            self.startup_frames = []
            self.startup_frame_durations = []
            self.startup_frame_offsets = []
            return False

        if not self.startup_frames:
            return False
        self.startup_frame_durations = self._sync_frame_durations_to_audio(raw_frame_durations, sound_duration_ms)
        self.startup_frame_offsets = self._build_frame_offsets(self.startup_frame_durations)
        self.startup_total_runtime_ms = max(sum(self.startup_frame_durations), sound_duration_ms, 1000)
        self.startup_current_frame_index = 0
        self.startup_started_at = None

        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        splash.configure(bg="black")
        splash.attributes("-topmost", True)
        splash.bind("<Button-1>", self._finish_startup_splash)
        splash.bind("<Escape>", self._finish_startup_splash)
        splash.bind("<Return>", self._finish_startup_splash)

        self.startup_splash = splash
        first_frame = self.startup_frames[0]
        width = first_frame.width()
        height = first_frame.height()
        screen_width = splash.winfo_screenwidth()
        screen_height = splash.winfo_screenheight()
        pos_x = max((screen_width - width) // 2, 0)
        pos_y = max((screen_height - height) // 2, 0)
        splash.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

        self.startup_frame_label = tk.Label(
            splash,
            image=first_frame,
            bg="black",
            borderwidth=0,
            highlightthickness=0,
        )
        self.startup_frame_label.pack(fill="both", expand=True)
        splash.update_idletasks()
        splash.update()

        self.after(1, lambda: self._start_startup_media(sound_path))
        return True

    def _start_startup_media(self, sound_path: Path) -> None:
        if self.startup_splash is None or self.startup_frame_label is None or not self.startup_frames:
            return

        if winsound is not None:
            try:
                winsound.PlaySound(
                    str(sound_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except RuntimeError:
                pass

        self.startup_started_at = time.perf_counter()
        self.startup_current_frame_index = 0
        self.startup_frame_label.configure(image=self.startup_frames[0])
        self._tick_startup_splash()

    def _tick_startup_splash(self) -> None:
        if (
            self.startup_splash is None
            or self.startup_frame_label is None
            or not self.startup_frames
            or self.startup_started_at is None
        ):
            return

        elapsed_ms = int((time.perf_counter() - self.startup_started_at) * 1000)
        if elapsed_ms >= self.startup_total_runtime_ms:
            self._finish_startup_splash()
            return

        frame_index = self._frame_index_for_elapsed(elapsed_ms)
        if frame_index != self.startup_current_frame_index:
            self.startup_current_frame_index = frame_index
            self.startup_frame_label.configure(image=self.startup_frames[frame_index])

        self.startup_frame_after_id = self.after(10, self._tick_startup_splash)

    def _finish_startup_splash(self, _event: tk.Event | None = None) -> None:
        if self.startup_frame_after_id is not None:
            self.after_cancel(self.startup_frame_after_id)
            self.startup_frame_after_id = None
        if self.startup_finish_after_id is not None:
            self.after_cancel(self.startup_finish_after_id)
            self.startup_finish_after_id = None
        if winsound is not None:
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass

        splash = self.startup_splash
        self.startup_splash = None
        self.startup_frame_label = None
        self.startup_frames = []
        self.startup_frame_durations = []
        self.startup_frame_offsets = []
        self.startup_started_at = None
        self.startup_total_runtime_ms = 0
        self.startup_current_frame_index = 0
        if splash is not None and splash.winfo_exists():
            splash.destroy()

        self._authenticate_admin_startup()

    def _startup_asset_dir(self) -> Path:
        return self.settings.database_path.parent / "startup_assets"

    def _startup_animation_path(self) -> Path | None:
        candidates = [
            self._startup_asset_dir() / "startup_animation.gif",
            Path(r"D:\Aseprite\palettes\Teamshapesanimiamtion.gif"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _startup_sound_path(self) -> Path | None:
        approved_sound = self._startup_asset_dir() / "startup_sound.wav"
        original_sound = self._startup_asset_dir() / "startup_sound_original.wav"
        if approved_sound.exists():
            if original_sound.exists() and random.randrange(10) == 0:
                return original_sound
            return approved_sound

        candidates = [
            Path(r"C:\Users\ethan_202ogfg\Downloads\8_Bit_Shapes (3).wav"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _load_startup_animation(path: Path) -> tuple[list[ImageTk.PhotoImage], list[int]]:
        frames: list[ImageTk.PhotoImage] = []
        durations: list[int] = []
        with Image.open(path) as image:
            for frame in ImageSequence.Iterator(image):
                converted = frame.convert("RGBA")
                frames.append(ImageTk.PhotoImage(converted))
                durations.append(int(frame.info.get("duration", image.info.get("duration", 100))))
        return frames, durations

    @staticmethod
    def _sync_frame_durations_to_audio(frame_durations: list[int], sound_duration_ms: int) -> list[int]:
        if not frame_durations:
            return []
        total_animation_ms = sum(frame_durations)
        if total_animation_ms <= 0 or sound_duration_ms <= 0:
            return [max(20, int(duration)) for duration in frame_durations]

        scale = sound_duration_ms / float(total_animation_ms)
        adjusted = [max(20, int(round(duration * scale))) for duration in frame_durations]
        difference = sound_duration_ms - sum(adjusted)
        adjusted[-1] = max(20, adjusted[-1] + difference)
        return adjusted

    @staticmethod
    def _build_frame_offsets(frame_durations: list[int]) -> list[int]:
        offsets: list[int] = []
        elapsed = 0
        for duration in frame_durations:
            offsets.append(elapsed)
            elapsed += max(20, int(duration))
        return offsets

    def _frame_index_for_elapsed(self, elapsed_ms: int) -> int:
        if not self.startup_frame_offsets:
            return 0
        index = bisect.bisect_right(self.startup_frame_offsets, elapsed_ms) - 1
        return max(0, min(index, len(self.startup_frames) - 1))

    @staticmethod
    def _wav_duration_ms(path: Path) -> int:
        with wave.open(str(path), "rb") as audio_file:
            frame_count = audio_file.getnframes()
            frame_rate = audio_file.getframerate()
        if frame_rate <= 0:
            return 0
        return int((frame_count / float(frame_rate)) * 1000)

    def _authenticate_admin_startup(self) -> None:
        authenticated = self._prompt_and_authenticate_admin(
            title="Admin Code Required",
            prompt=f"Enter the admin code to open {APP_TITLE}.",
            allow_cancel=False,
        )
        if not authenticated:
            if self.winfo_exists():
                self.destroy()
            return
        if not device_backup_setup_completed():
            self._prompt_for_backup_location()
        self.deiconify()
        self.lift()
        self.after(100, self._focus_checkout_scan)

    def _prompt_for_backup_location(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Protect A.C.E. Backups")
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg="#eef4fb")

        container = ttk.Frame(dialog, padding=20)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Where should A.C.E. protect its backups?", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            container,
            text=(
                "Your live inventory stays with A.C.E. on the portable drive. "
                "Choose a second location for compressed recovery copies so a failed or lost USB does not erase everything."
            ),
            wraplength=610,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 14))

        current_path = self.settings.protected_backup_dir
        protection_status = self.service.backup_protection_status()
        if current_path is None:
            current_text = "Not configured - backups are currently USB-only"
        elif protection_status["last_error"]:
            current_text = f"Unavailable this session: {current_path}\n{protection_status['last_error']}"
        else:
            current_text = f"Ready: {current_path}"
        current_frame = ttk.LabelFrame(container, text="Current Protected Location", padding=10)
        current_frame.grid(row=2, column=0, sticky="ew")
        current_frame.columnconfigure(0, weight=1)
        ttk.Label(current_frame, text=current_text, wraplength=580).grid(row=0, column=0, sticky="w")

        recommended_frame = ttk.LabelFrame(container, text="Recommended", padding=10)
        recommended_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        recommended_frame.columnconfigure(0, weight=1)
        ttk.Label(
            recommended_frame,
            text="Choose or create a folder on this computer, another drive, or a synced OneDrive folder.",
            wraplength=500,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            recommended_frame,
            text="Choose or Create Protected Folder",
            command=lambda: self._choose_protected_backup_from_prompt(dialog),
        ).grid(row=0, column=1, padx=(12, 0))

        usb_roots = self._detect_removable_drive_roots()
        usb_var = tk.StringVar(value=str(usb_roots[0]) if usb_roots else "No removable USB drive detected")
        usb_frame = ttk.LabelFrame(container, text="USB Drive Option", padding=10)
        usb_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        usb_frame.columnconfigure(0, weight=1)
        ttk.Combobox(
            usb_frame,
            textvariable=usb_var,
            values=[str(path) for path in usb_roots],
            state="readonly" if usb_roots else "disabled",
        ).grid(row=0, column=0, sticky="ew")
        usb_button = ttk.Button(
            usb_frame,
            text="Use Selected USB",
            command=lambda: self._use_usb_backup_from_prompt(dialog, usb_var.get()),
        )
        usb_button.grid(row=0, column=1, padx=(12, 0))
        if not usb_roots:
            usb_button.state(["disabled"])
        ttk.Label(
            usb_frame,
            text="A second USB can protect against failure of the A.C.E. USB. The same USB does not provide failure protection.",
            style="Subtitle.TLabel",
            wraplength=590,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        button_row = ttk.Frame(container)
        button_row.grid(row=5, column=0, sticky="e", pady=(16, 0))
        continue_text = "Keep Current Location" if current_path is not None else "USB Only for This Session"
        ttk.Button(
            button_row,
            text=continue_text,
            command=lambda: self._continue_from_backup_prompt(dialog),
        ).grid(row=0, column=0)

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._continue_from_backup_prompt(dialog))
        dialog.bind("<Escape>", lambda _event: self._continue_from_backup_prompt(dialog))
        dialog.update_idletasks()
        pos_x = max((dialog.winfo_screenwidth() - dialog.winfo_width()) // 2, 0)
        pos_y = max((dialog.winfo_screenheight() - dialog.winfo_height()) // 2, 0)
        dialog.geometry(f"+{pos_x}+{pos_y}")
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.after(200, lambda: dialog.attributes("-topmost", False) if dialog.winfo_exists() else None)
        dialog.wait_window()

    def _choose_protected_backup_from_prompt(self, dialog: tk.Toplevel) -> None:
        initial_dir = self.settings.protected_backup_dir or Path.home()
        selected = filedialog.askdirectory(
            title="Choose or Create A.C.E. Protected Backup Folder",
            initialdir=str(initial_dir),
            mustexist=False,
            parent=dialog,
        )
        if selected and self._activate_protected_backup_location(Path(selected), parent=dialog):
            dialog.destroy()

    def _use_usb_backup_from_prompt(self, dialog: tk.Toplevel, selected_root: str) -> None:
        if not selected_root or selected_root.startswith("No removable"):
            messagebox.showerror("USB Drive Not Found", "Connect a USB drive or choose another folder.", parent=dialog)
            return
        target_dir = Path(selected_root) / "A.C.E. Backups"
        if self._activate_protected_backup_location(target_dir, parent=dialog):
            dialog.destroy()

    def _continue_from_backup_prompt(self, dialog: tk.Toplevel) -> None:
        protection_status = self.service.backup_protection_status()
        protected_location_unavailable = bool(protection_status["last_error"])
        if self.settings.protected_backup_dir is None or protected_location_unavailable:
            unavailable_note = (
                f"\n\nSaved location error: {protection_status['last_error']}"
                if protected_location_unavailable
                else ""
            )
            confirmed = messagebox.askyesno(
                "Continue With USB-Only Backups?",
                (
                    "Without a protected folder, all backups remain on the same portable drive as the live inventory. "
                    "If that USB fails or is lost, those backups may be lost too."
                    f"{unavailable_note}\n\nContinue for this session?"
                ),
                parent=dialog,
            )
            if not confirmed:
                return
        save_device_backup_settings(
            protected_backup_path=(
                str(self.settings.protected_backup_dir)
                if self.settings.protected_backup_dir is not None
                else ""
            ),
            setup_completed=True,
        )
        dialog.destroy()

    def _activate_protected_backup_location(self, directory: Path, *, parent: tk.Misc) -> bool:
        try:
            target_dir = directory.expanduser().resolve()
        except OSError as exc:
            messagebox.showerror("Invalid Backup Folder", str(exc), parent=parent)
            return False

        live_drive = self.settings.database_path.anchor.casefold()
        target_drive = target_dir.anchor.casefold()
        if live_drive and target_drive and live_drive == target_drive:
            confirmed = messagebox.askyesno(
                "Same Drive Warning",
                (
                    "This folder appears to be on the same drive as the live A.C.E. database. "
                    "It will provide another backup folder, but it may not survive failure of that drive.\n\nUse it anyway?"
                ),
                parent=parent,
            )
            if not confirmed:
                return False

        validation_file = target_dir / ".ace_backup_write_test"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            validation_file.write_text("A.C.E. backup location test", encoding="utf-8")
            validation_file.unlink(missing_ok=True)
        except OSError as exc:
            try:
                validation_file.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror(
                "Backup Folder Unavailable",
                f"A.C.E. could not write to this folder:\n{target_dir}\n\n{exc}",
                parent=parent,
            )
            return False

        previous_path = self.settings.protected_backup_path
        self.settings.protected_backup_path = str(target_dir)
        save_settings(self.settings)
        self.service.create_manual_backup()
        status = self.service.backup_protection_status()
        if status["last_error"] or not status["last_copy_path"]:
            self.settings.protected_backup_path = previous_path
            save_settings(self.settings)
            messagebox.showerror(
                "Protected Backup Failed",
                status["last_error"] or "A.C.E. could not verify the protected backup copy.",
                parent=parent,
            )
            return False

        self.settings_protected_backup_var.set(str(target_dir))
        save_device_backup_settings(
            protected_backup_path=str(target_dir),
            setup_completed=True,
        )
        self._set_status(f"Protected backups: {target_dir}")
        messagebox.showinfo(
            "Protected Backups Ready",
            f"A compressed recovery backup was verified at:\n{status['last_copy_path']}",
            parent=parent,
        )
        return True

    @staticmethod
    def _detect_removable_drive_roots() -> list[Path]:
        try:
            get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
        except (AttributeError, OSError):
            return []

        removable_drive_type = 2
        roots: list[Path] = []
        for letter in string.ascii_uppercase:
            root_text = f"{letter}:\\"
            try:
                if get_drive_type(root_text) == removable_drive_type and Path(root_text).exists():
                    roots.append(Path(root_text))
            except OSError:
                continue
        return roots

    def _prompt_and_authenticate_admin(self, *, title: str, prompt: str, allow_cancel: bool) -> bool:
        while True:
            code = self._prompt_admin_code(title=title, prompt=prompt)
            if code is None:
                if allow_cancel:
                    return False
                if self._confirm_exit_from_admin_prompt():
                    continue
                return False
            try:
                admin_record = self.service.authenticate_admin_code(code)
            except InventoryError as exc:
                messagebox.showerror("Invalid Admin Code", str(exc), parent=self._dialog_parent())
                continue
            self._apply_window_icon_from_code(code)
            self._set_current_admin(admin_record)
            return True

    def _prompt_admin_code(self, *, title: str, prompt: str) -> str | None:
        dialog = tk.Toplevel(self._dialog_parent())
        dialog.title(title)
        dialog.transient(self._dialog_parent())
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg="#eef4fb")

        result: dict[str, str | None] = {"code": None}
        code_var = tk.StringVar()
        visible_var = tk.BooleanVar(value=False)
        toggle_text_var = tk.StringVar(value="Show")

        container = ttk.Frame(dialog, padding=16)
        container.grid(row=0, column=0, sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text=prompt, wraplength=360, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")

        code_entry = ttk.Entry(container, textvariable=code_var, show="*")
        code_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        toggle_button = ttk.Button(
            container,
            textvariable=toggle_text_var,
            width=7,
            command=lambda: self._toggle_dialog_password_visibility(code_entry, visible_var, toggle_text_var),
        )
        toggle_button.grid(row=1, column=1, padx=(8, 0), pady=(10, 0))

        button_row = ttk.Frame(container)
        button_row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="Cancel", command=lambda: self._close_admin_code_dialog(dialog, result, None)).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(button_row, text="OK", command=lambda: self._close_admin_code_dialog(dialog, result, code_var.get())).grid(
            row=0, column=1
        )

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_admin_code_dialog(dialog, result, None))
        dialog.bind("<Escape>", lambda _event: self._close_admin_code_dialog(dialog, result, None))
        dialog.bind("<Return>", lambda _event: self._close_admin_code_dialog(dialog, result, code_var.get()))

        dialog.update_idletasks()
        parent = self._dialog_parent()
        if parent is not None and parent.winfo_exists():
            pos_x = parent.winfo_rootx() + max((parent.winfo_width() - dialog.winfo_width()) // 2, 0)
            pos_y = parent.winfo_rooty() + max((parent.winfo_height() - dialog.winfo_height()) // 2, 0)
        else:
            pos_x = max((dialog.winfo_screenwidth() - dialog.winfo_width()) // 2, 0)
            pos_y = max((dialog.winfo_screenheight() - dialog.winfo_height()) // 2, 0)
        dialog.geometry(f"+{pos_x}+{pos_y}")

        code_entry.focus_set()
        dialog.wait_window()
        return result["code"]

    @staticmethod
    def _close_admin_code_dialog(dialog: tk.Toplevel, result: dict[str, str | None], value: str | None) -> None:
        result["code"] = value
        dialog.destroy()

    def _toggle_dialog_password_visibility(
        self,
        entry: ttk.Entry,
        visible_var: tk.BooleanVar,
        toggle_text_var: tk.StringVar,
    ) -> None:
        visible = not visible_var.get()
        visible_var.set(visible)
        self._apply_password_visibility(entry, visible=visible, toggle_text_var=toggle_text_var)

    def _confirm_exit_from_admin_prompt(self) -> bool:
        should_retry = messagebox.askyesno(
            "Admin Code Required",
            "An admin code is required to open the app.\n\nDo you want to try again?",
            parent=self._dialog_parent(),
        )
        return should_retry

    def _set_current_admin(self, admin_record: dict[str, Any]) -> None:
        self.current_admin = admin_record
        label = str(admin_record.get("label") or "").strip()
        if not label:
            role = str(admin_record.get("role") or "").strip()
            display_name = str(admin_record.get("display_name") or "").strip()
            label = f"{role} {display_name}".strip()
        self.current_admin_var.set(label or "Authenticated")
        self._reset_settings_admin_code_visibility()
        self._load_selected_admin_code_if_authorized(show_error=False)
        self._set_status(f"Active admin session: {self.current_admin_var.get()}")

    def _current_admin_is_cadre(self) -> bool:
        if not self.current_admin:
            return False
        return str(self.current_admin.get("role") or "").strip().upper() == "CADRE"

    def _load_selected_admin_code_if_authorized(self, *, show_error: bool) -> None:
        if self.selected_admin_id is None:
            self.admin_code_var.set("")
            return

        if not self._current_admin_is_cadre():
            self.admin_code_var.set("")
            if self.selected_admin_id == "MASTER":
                self.admin_summary_var.set(
                    "The cadre Det005 code is reserved for CADRE. Only a CADRE session can reveal stored admin codes."
                )
            else:
                row = self.admin_cache.get(str(self.selected_admin_id))
                if row:
                    self.admin_summary_var.set(
                        f"Selected admin: {row['role']} {row['display_name']}. Only a CADRE session can reveal stored admin codes."
                    )
            return

        try:
            code_value = self.service.get_admin_code_value(admin_id=self.selected_admin_id)
        except InventoryError as exc:
            self.admin_code_var.set("")
            if show_error:
                self._show_error(str(exc))
            else:
                row = self.admin_cache.get(str(self.selected_admin_id))
                if row:
                    self.admin_summary_var.set(
                        f"Selected admin: {row['role']} {row['display_name']}. {exc}"
                    )
            return

        self.admin_code_var.set(code_value)

    def _save_admin_code(self) -> None:
        def on_success(admin_row: dict[str, Any]) -> None:
            self.selected_admin_id = int(admin_row["admin_id"])
            self.admin_display_name_var.set(admin_row["display_name"])
            self.admin_code_var.set("")
            self._reset_settings_admin_code_visibility()
            self.refresh_admin_codes()

        self._run_action(
            lambda: self.service.save_admin_code(
                display_name=self.admin_display_name_var.get(),
                code=self.admin_code_var.get(),
            ),
            success_message="Admin code saved.",
            on_success=on_success,
        )

    def _toggle_settings_admin_code_visibility(self) -> None:
        visible = not self.admin_code_visible_var.get()
        self.admin_code_visible_var.set(visible)
        self._apply_password_visibility(
            self.admin_code_entry,
            visible=visible,
            toggle_text_var=self.admin_code_toggle_text_var,
        )

    def _reset_settings_admin_code_visibility(self) -> None:
        self.admin_code_visible_var.set(False)
        self._apply_password_visibility(
            self.admin_code_entry,
            visible=False,
            toggle_text_var=self.admin_code_toggle_text_var,
        )

    def _deactivate_selected_admin_code(self) -> None:
        if self.selected_admin_id is None:
            self._show_error("Select a custom admin code to deactivate.")
            return
        if str(self.selected_admin_id) == "MASTER":
            self._show_error("The cadre Det005 code cannot be deactivated.")
            return

        confirmed = messagebox.askyesno(
            "Deactivate Admin Code",
            "Deactivate the selected admin code? Existing checkout history will stay intact.",
            parent=self,
        )
        if not confirmed:
            return

        def on_success(_result: object) -> None:
            self.selected_admin_id = None
            self.admin_display_name_var.set("")
            self.admin_code_var.set("")
            self._reset_settings_admin_code_visibility()
            self.refresh_admin_codes()

        self._run_action(
            lambda: self.service.deactivate_admin_code(admin_id=int(self.selected_admin_id)),
            success_message="Admin code deactivated.",
            on_success=on_success,
        )

    def _delete_selected_admin_code(self) -> None:
        if self.selected_admin_id is None:
            self._show_error("Select a custom admin code to delete.")
            return
        if str(self.selected_admin_id) == "MASTER":
            self._show_error("The cadre Det005 code cannot be deleted.")
            return
        if self.current_admin and self.current_admin.get("admin_id") == self.selected_admin_id:
            self._show_error("Switch to a different admin session before deleting the currently active admin code.")
            return

        row = self.admin_cache.get(str(self.selected_admin_id))
        admin_label = (
            f"{row['role']} {row['display_name']}".strip()
            if row
            else f"Admin ID {self.selected_admin_id}"
        )
        confirmed = messagebox.askyesno(
            "Delete Admin Code Permanently",
            (
                f"Permanently delete {admin_label}?\n\n"
                "This removes the saved admin code from the app. Existing approval history will stay readable."
            ),
            parent=self,
        )
        if not confirmed:
            return

        deleted_admin_id = int(self.selected_admin_id)

        def on_success(_result: object) -> None:
            self.selected_admin_id = None
            self.admin_display_name_var.set("")
            self.admin_code_var.set("")
            self._reset_settings_admin_code_visibility()
            self.refresh_admin_codes()

        self._run_action(
            lambda: self.service.delete_admin_code(admin_id=deleted_admin_id),
            success_message="Admin code deleted permanently.",
            on_success=on_success,
        )

    def _switch_admin(self) -> None:
        switched = self._prompt_and_authenticate_admin(
            title="Switch Admin Session",
            prompt="Enter the admin code for the new active session.",
            allow_cancel=True,
        )
        if switched:
            self._show_info(f"Active admin switched to {self.current_admin_var.get()}.")

    def _on_admin_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.admin_tree.selection()
        if not selection:
            self.selected_admin_id = None
            self.admin_code_var.set("")
            self._reset_settings_admin_code_visibility()
            return
        selected_key = str(selection[0])
        row = self.admin_cache.get(selected_key)
        if not row:
            return
        self.selected_admin_id = row["admin_id"]
        self.admin_display_name_var.set(str(row.get("display_name", "")))
        self._reset_settings_admin_code_visibility()
        if selected_key == "MASTER":
            if self._current_admin_is_cadre():
                self.admin_summary_var.set(
                "Cadre code Det005 signs in as CADRE. It is permanent and cannot be edited or deactivated."
                )
            else:
                self.admin_summary_var.set(
                "Cadre code Det005 signs in as CADRE. Only a CADRE session can reveal stored admin codes."
                )
        else:
            base_summary = f"Selected admin: {row['role']} {row['display_name']}."
            if self._current_admin_is_cadre():
                self.admin_summary_var.set(f"{base_summary} CADRE can review the saved code below.")
            else:
                self.admin_summary_var.set(f"{base_summary} Use Switch Admin to sign in with that code.")
        self._load_selected_admin_code_if_authorized(show_error=False)

    def _create_transfer_device(self) -> None:
        default_icon_png = Path(r"D:\Aseprite\palettes\aceinv.png")
        icon_source: Path | None = default_icon_png if default_icon_png.exists() else None

        def on_success(installer_path: Path) -> None:
            self._show_info(
                f"Transfer device EXE created at:\n{installer_path}\n\nCopy that EXE to another Windows device and run it there."
            )

        self._run_action(
            lambda: self.service.create_transfer_installer(icon_source=icon_source),
            success_message=None,
            on_success=on_success,
        )

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str, str]:
        parts = [part.strip() for part in full_name.split(",")]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        return "", "", ""

    def _compose_checkout_name(self) -> str:
        return self._compose_name(
            self.checkout_last_name_var.get(),
            self.checkout_middle_initial_var.get(),
            self.checkout_first_name_var.get(),
        )

    def _compose_cadet_form_name(self) -> str:
        return self._compose_name(
            self.cadet_last_name_var.get(),
            self.cadet_middle_initial_var.get(),
            self.cadet_first_name_var.get(),
        )

    @staticmethod
    def _compose_name(last_name: str, middle_initial: str, first_name: str) -> str:
        return f"{last_name.strip()}, {middle_initial.strip()}, {first_name.strip()}"

    def _load_cadet_details(self, cadet_id: int) -> None:
        details = self.service.get_cadet_details(cadet_id)
        cadet = details["cadet"]
        self.selected_cadet_id = cadet_id
        last_name, middle_initial, first_name = self._split_name(cadet["full_name"])
        self.cadet_last_name_var.set(last_name)
        self.cadet_middle_initial_var.set(middle_initial)
        self.cadet_first_name_var.set(first_name)
        self.cadet_form_email_var.set(cadet["email"])
        self.cadet_summary_var.set(
            f"{cadet['full_name']} | {cadet['email']}\n"
            f"Saved: {cadet['created_at']} | Last Updated: {cadet['updated_at']}\n"
            f"Currently checked out: {len(details['current_items'])} | Total history records: {len(details['history'])}"
        )
        self._populate_tree(
            self.cadet_current_tree,
            [
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "approved_by_role",
                "approved_by_name",
                "checkout_time",
            ],
            details["current_items"],
        )
        self._populate_tree(
            self.cadet_history_tree,
            [
                "transaction_id",
                "barcode_id",
                "item_name",
                "approved_by_role",
                "approved_by_name",
                "checkout_time",
                "return_time",
                "return_approved_by_role",
                "return_approved_by_name",
                "condition_notes",
            ],
            details["history"],
        )

    def _save_cadet(self) -> None:
        def on_success(cadet: dict[str, Any]) -> None:
            self.selected_cadet_id = int(cadet["cadet_id"])
            self.refresh_cadets()
            self._load_cadet_details(self.selected_cadet_id)

        is_update = self.selected_cadet_id is not None
        action = (
            lambda: self.service.update_cadet(
                cadet_id=int(self.selected_cadet_id or 0),
                cadet_name=self._compose_cadet_form_name(),
                cadet_email=self.cadet_form_email_var.get(),
            )
            if is_update
            else self.service.save_cadet(
                cadet_name=self._compose_cadet_form_name(),
                cadet_email=self.cadet_form_email_var.get(),
            )
        )
        self._run_action(
            action,
            success_message="Cadet record updated." if is_update else "Cadet record saved.",
            on_success=on_success,
        )

    def _on_cadet_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.cadet_tree.selection()
        if not selection:
            return
        try:
            cadet_id = int(selection[0])
        except ValueError:
            return
        self._run_action(lambda: self._load_cadet_details(cadet_id), success_message=None)

    def _clear_cadet_form(self) -> None:
        self.selected_cadet_id = None
        self.cadet_last_name_var.set("")
        self.cadet_middle_initial_var.set("")
        self.cadet_first_name_var.set("")
        self.cadet_form_email_var.set("")
        self.cadet_summary_var.set("Select or save a cadet to view issued items.")
        self._populate_tree(
            self.cadet_current_tree,
            [
                "barcode_id",
                "item_name",
                "category",
                "variant",
                "item_type",
                "approved_by_role",
                "approved_by_name",
                "checkout_time",
            ],
            [],
        )
        self._populate_tree(
            self.cadet_history_tree,
            [
                "transaction_id",
                "barcode_id",
                "item_name",
                "approved_by_role",
                "approved_by_name",
                "checkout_time",
                "return_time",
                "return_approved_by_role",
                "return_approved_by_name",
                "condition_notes",
            ],
            [],
        )

    def _delete_selected_cadet(self) -> None:
        if not self.selected_cadet_id:
            self._show_error("Select a saved cadet first.")
            return

        row = self.cadet_cache.get(self.selected_cadet_id)
        cadet_label = row["full_name"] if row else f"Cadet ID {self.selected_cadet_id}"
        confirmed = messagebox.askyesno(
            "Delete Cadet Permanently",
            (
                f"Permanently delete the saved cadet record for {cadet_label}?\n\n"
                "This removes the cadet from the saved cadet list only. Transaction history is preserved."
            ),
            parent=self,
        )
        if not confirmed:
            return

        deleted_cadet_id = int(self.selected_cadet_id)

        def on_success(_result: object) -> None:
            self.selected_cadet_id = None
            self.refresh_cadets()
            self._clear_cadet_form()

        self._run_action(
            lambda: self.service.delete_cadet(cadet_id=deleted_cadet_id),
            success_message="Cadet record deleted permanently.",
            on_success=on_success,
        )

    def _export_selected_cadet_history(self) -> None:
        if not self.selected_cadet_id:
            self._show_error("Select a saved cadet first.")
            return

        def on_success(export_path: Path) -> None:
            self._set_status(f"Cadet history workbook exported to {export_path.name}.")

        self._run_action(
            lambda: self.service.export_cadet_history_spreadsheet(
                cadet_id=int(self.selected_cadet_id or 0),
                open_after=True,
            ),
            success_message="Cadet history spreadsheet exported.",
            on_success=on_success,
        )

    def _view_selected_cadet_history_entry(self) -> None:
        selected_row = self._selected_tree_row(self.cadet_history_tree)
        if selected_row is None:
            self._show_error("Select a cadet transaction row first.")
            return

        window = tk.Toplevel(self)
        window.title("Cadet Transaction Detail")
        window.transient(self)
        window.grab_set()
        window.geometry("920x560")
        window.configure(bg="#eef4fb")

        container = ttk.Frame(window, padding=16)
        container.grid(row=0, column=0, sticky="nsew")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        heading = f"Transaction {selected_row.get('transaction_id', '')} | {selected_row.get('barcode_id', '')}"
        ttk.Label(container, text=heading.strip(" |"), style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        detail_text = tk.Text(
            container,
            wrap="word",
            font=("Segoe UI", 11),
            bg="white",
            fg="#0f172a",
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=12,
        )
        detail_text.grid(row=1, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(container, orient="vertical", command=detail_text.yview)
        detail_scroll.grid(row=1, column=1, sticky="ns")
        detail_text.configure(yscrollcommand=detail_scroll.set)

        detail_lines = [
            f"Transaction ID: {selected_row.get('transaction_id', '')}",
            f"Barcode: {selected_row.get('barcode_id', '')}",
            f"Item: {selected_row.get('item_name', '')}",
            f"Approved By Role: {selected_row.get('approved_by_role', '')}",
            f"Approved By Name: {selected_row.get('approved_by_name', '')}",
            f"Checkout Time: {selected_row.get('checkout_time', '')}",
            f"Return Time: {selected_row.get('return_time', '') or 'Still checked out'}",
            f"Return Approved By Role: {selected_row.get('return_approved_by_role', '')}",
            f"Return Approved By Name: {selected_row.get('return_approved_by_name', '')}",
            "",
            "Condition Notes:",
            str(selected_row.get("condition_notes", "") or "(none)"),
        ]
        detail_text.insert("1.0", "\n".join(detail_lines))
        detail_text.configure(state="disabled")

        ttk.Button(container, text="Close", command=window.destroy).grid(row=2, column=0, sticky="e", pady=(12, 0))

    def _load_selected_cadet_into_checkout(self) -> None:
        if not self.selected_cadet_id:
            self._show_error("Select a saved cadet first.")
            return
        row = self.cadet_cache.get(self.selected_cadet_id)
        if not row:
            self._show_error("Selected cadet is no longer available.")
            return
        last_name, middle_initial, first_name = self._split_name(row["full_name"])
        self.checkout_last_name_var.set(last_name)
        self.checkout_middle_initial_var.set(middle_initial)
        self.checkout_first_name_var.set(first_name)
        self.checkout_email_var.set(row["email"])
        self.notebook.select(self.checkout_tab)
        self.after(100, self._focus_checkout_scan)
        self._set_status(f"Loaded {row['full_name']} into checkout.")

    def _populate_catalog_values(self) -> None:
        categories = self.service.list_catalog_values("category")
        variants = self.service.list_catalog_values("variant")
        item_types = self.service.list_catalog_values("item_type")
        item_names = self.service.list_catalog_values("item_name")
        for combo in self.category_combos:
            self._configure_catalog_autocomplete(combo, "category", categories)
        for combo in self.variant_combos:
            self._configure_catalog_autocomplete(combo, "variant", variants)
        for combo in self.item_type_combos:
            self._configure_catalog_autocomplete(combo, "item_type", item_types)
        for combo in self.item_name_combos:
            self._configure_catalog_autocomplete(combo, "item_name", item_names)

    def _configure_catalog_autocomplete(self, combo: ttk.Combobox, kind: str, values: list[str]) -> None:
        widget_id = str(combo)
        self.catalog_combo_values[widget_id] = list(values)
        self.catalog_combo_kinds[widget_id] = kind
        combo["values"] = values
        if getattr(combo, "_ace_autocomplete_bound", False):
            return
        combo._ace_autocomplete_bound = True
        combo.bind("<KeyRelease>", self._filter_catalog_combo, add="+")
        combo.bind("<FocusIn>", self._restore_catalog_combo_values, add="+")
        combo.bind("<FocusOut>", self._finish_catalog_entry, add="+")
        combo.bind("<<ComboboxSelected>>", self._finish_catalog_entry, add="+")

    def _restore_catalog_combo_values(self, event: tk.Event) -> None:
        combo = event.widget
        values = self.catalog_combo_values.get(str(combo), [])
        combo["values"] = values

    def _filter_catalog_combo(self, event: tk.Event) -> None:
        combo = event.widget
        if event.keysym in {"Up", "Down", "Left", "Right", "Return", "Escape", "Tab"}:
            return
        values = self.catalog_combo_values.get(str(combo), [])
        typed = combo.get().strip().casefold()
        if not typed:
            matches = values
        else:
            words = typed.split()
            matches = [value for value in values if all(word in value.casefold() for word in words)]
            matches.sort(key=lambda value: (not value.casefold().startswith(typed), len(value), value))
        combo["values"] = matches or values
        if matches:
            try:
                combo.event_generate("<Down>")
            except tk.TclError:
                pass

    def _finish_catalog_entry(self, event: tk.Event) -> None:
        combo = event.widget
        raw_value = combo.get().strip()
        if not raw_value:
            return
        values = self.catalog_combo_values.get(str(combo), [])
        kind = self.catalog_combo_kinds.get(str(combo), "")
        folded = raw_value.casefold()
        aliases = CATALOG_ALIASES.get(kind, {})
        canonical = aliases.get(folded)
        if canonical is None:
            canonical = next((value for value in values if value.casefold() == folded), None)
        if canonical is None:
            prefix_matches = [value for value in values if value.casefold().startswith(folded)]
            if len(prefix_matches) == 1:
                canonical = prefix_matches[0]
        if canonical is not None:
            combo.set(canonical)
        combo["values"] = values

    def _filter_quick_find(self, event: tk.Event) -> None:
        if event.keysym in {"Up", "Down", "Left", "Right", "Return", "Escape", "Tab"}:
            return
        query = self.generator_quick_find_var.get().strip()
        results = self._quick_find_matches(query)
        self.quick_find_result_map = {label: payload for label, payload in results}
        self.generator_quick_find_results.delete(0, tk.END)
        for label, _payload in results:
            self.generator_quick_find_results.insert(tk.END, label)

    def _focus_quick_find_results(self, _event: tk.Event | None = None) -> str:
        if self.generator_quick_find_results.size():
            self.generator_quick_find_results.selection_clear(0, tk.END)
            self.generator_quick_find_results.selection_set(0)
            self.generator_quick_find_results.activate(0)
            self.generator_quick_find_results.focus_set()
        return "break"

    def _apply_quick_find_result(self, _event: tk.Event | None = None) -> None:
        selection = self.generator_quick_find_results.curselection()
        if selection:
            selected = str(self.generator_quick_find_results.get(selection[0]))
            payload = self.quick_find_result_map.get(selected)
        elif self.quick_find_result_map:
            selected, payload = next(iter(self.quick_find_result_map.items()))
        else:
            payload = None
        if payload is None:
            return
        category, item_name, official_name, requested_size, wings_item_no = payload
        self.generator_quick_find_var.set(official_name)
        self.generator_wings_item_no_var.set(wings_item_no)
        self.generator_category_var.set(category)
        self.generator_item_name_var.set(item_name)
        self.generator_selected_item_var.set(official_name)
        self.generator_size_label_var.set("WINGS Size")
        self.generator_size_combo["values"] = [requested_size]
        self.generator_variant_var.set(requested_size)
        self._set_status(f"Selected WINGS item {wings_item_no}. Enter the quantity to add.")

    def _quick_find_matches(self, query: str) -> list[tuple[str, tuple[str, str, str, str, str]]]:
        query_text = " ".join(
            query.casefold().replace("’", "'").replace("'s", "").replace("_", " ").split()
        )
        query_text = re.sub(r"\bwomens\b", "women", query_text)
        query_text = re.sub(r"\bmens\b", "men", query_text)
        if not query_text:
            return []

        results: list[tuple[str, tuple[str, str, str, str, str]]] = []
        for row in self.service.list_wings_catalog(search=query_text)[:100]:
            sex = f" | {row['sex']}" if row["sex"] else ""
            stock = f" | Stock {row['stock_number']}" if row["stock_number"] else ""
            label = (
                f"WINGS {row['item_no']} | {row['item_name']} | {row['size']}"
                f"{sex}{stock}"
            )
            official_name = f"{row['item_name']} ({row['size']})"
            results.append(
                (
                    label,
                    (
                        str(row["category"]),
                        str(row["item_name"]),
                        official_name,
                        str(row["size"]),
                        str(row["item_no"]),
                    ),
                )
            )
        return results

        category_aliases = [
            ("cadet rank", "CADET RANK"),
            ("accoutrements", "ACCOUTREMENTS"),
            ("accoutrement", "ACCOUTREMENTS"),
            ("accessories", "ACCOUTREMENTS"),
            ("accessory", "ACCOUTREMENTS"),
            ("service dress", "BLUES"),
            ("blues", "BLUES"),
            ("blue", "BLUES"),
            ("ocp", "OCP"),
            ("ptg", "PTG"),
            ("pt gear", "PTG"),
            ("pt", "PTG"),
        ]
        category = ""
        consumed_phrases: list[str] = []
        for phrase, value in category_aliases:
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", query_text):
                category = value
                consumed_phrases.append(phrase)
                break

        variant, variant_phrases = self._variant_from_search(query_text)
        consumed_phrases.extend(variant_phrases)
        searchable_query = query_text
        for phrase in consumed_phrases:
            searchable_query = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", searchable_query)
        ignored_words = {"a", "an", "the", "item", "gear", "uniform", "size", "rank"}
        search_words = [word for word in searchable_query.split() if word not in ignored_words]

        item_names = self.service.list_catalog_values("item_name")
        matches: list[tuple[tuple[int, int, str], str, tuple[str, str, str, str]]] = []
        for item_name in item_names:
            legacy_names = [
                legacy for legacy, canonical in ITEM_NAME_ALIASES.items() if canonical.casefold() == item_name.casefold()
            ]
            inferred_category = self._category_for_catalog_item(item_name, legacy_names)
            if category and inferred_category != category:
                continue
            chosen_category = category or inferred_category
            base_official_name = self._official_equipment_name(chosen_category, item_name, legacy_names)
            for inventory_name, official_name in self._sex_specific_equipment_variants(
                chosen_category, item_name, base_official_name
            ):
                synonyms = self._equipment_search_synonyms(official_name)
                corpus = " ".join([official_name, item_name, *legacy_names, synonyms]).casefold().replace("-", " ")
                corpus_words = re.findall(r"[a-z0-9/]+", corpus)
                if not all(any(candidate.startswith(word) for candidate in corpus_words) for word in search_words):
                    continue
                if inferred_category == "CADET RANK" and variant.startswith("C/") and variant.casefold() not in corpus:
                    continue
                label = official_name
                starts = int(bool(search_words) and not corpus.startswith(search_words[0]))
                matches.append(
                    ((starts, len(official_name), label), label, (chosen_category, inventory_name, official_name, variant))
                )

        self.custom_index_size_by_name.clear()
        for custom in self.service.list_custom_index_items():
            custom_system = str(custom["uniform_system"])
            if category and custom_system != category:
                continue
            configuration = str(custom["configuration"])
            base_name = str(custom["equipment_name"])
            label = base_name if configuration == "Standard" else f"{base_name} – {configuration}"
            corpus = " ".join(
                [label, custom_system, configuration, str(custom["search_aliases"])]
            ).casefold().replace("-", " ")
            corpus_words = re.findall(r"[a-z0-9/]+", corpus)
            if not all(any(candidate.startswith(word) for candidate in corpus_words) for word in search_words):
                continue
            self.custom_index_size_by_name[label] = str(custom["size_system"])
            starts = int(bool(search_words) and not corpus.startswith(search_words[0]))
            matches.append(
                ((starts, len(label), label), label, (custom_system, label, label, variant))
            )

        matches.sort(key=lambda entry: entry[0])
        unique_results: list[tuple[str, tuple[str, str, str, str]]] = []
        seen_labels: set[str] = set()
        for _score, label, payload in matches:
            if label in seen_labels:
                continue
            seen_labels.add(label)
            unique_results.append((label, payload))
            if len(unique_results) == 20:
                break
        return unique_results

    @staticmethod
    def _sex_specific_equipment_variants(
        category: str,
        item_name: str,
        official_name: str,
    ) -> list[tuple[str, str]]:
        ocp_cut_items = {
            "Coat",
            "Trousers",
            "Coat - Improved Hot Weather Combat Uniform",
            "Trousers - Improved Hot Weather Combat Uniform",
        }
        if category == "OCP" and item_name in ocp_cut_items:
            return [
                (f"{official_name} - Unisex", f"{official_name} – Unisex"),
                (f"{official_name} - Women's", f"{official_name} – Women's"),
            ]
        sex_specific_items = {
            "Lightweight Blue Jacket": ("Men's Lightweight Blue Jacket", "Women's Lightweight Blue Jacket"),
            "Flight Cap - Enlisted Style": ("Men's Enlisted Flight Cap", "Women's Enlisted Flight Cap"),
            "Flight Cap - Officer Style": ("Men's Officer Flight Cap", "Women's Officer Flight Cap"),
            "Coyote Brown Combat Boots": ("Men's Coyote Brown Combat Boots", "Women's Coyote Brown Combat Boots"),
            "Athletic Shoes": ("Men's PTG Running Shoes", "Women's PTG Running Shoes"),
        }
        if item_name in sex_specific_items:
            mens_name, womens_name = sex_specific_items[item_name]
            return [(mens_name, mens_name), (womens_name, womens_name)]
        return [(item_name, official_name)]

    @staticmethod
    def _official_equipment_name(category: str, item_name: str, legacy_names: list[str]) -> str:
        official_names = {
            "Service Dress Coat - Male": "Men's Service Dress Coat",
            "Service Dress Coat - Female": "Women's Service Dress Coat",
            "Shirt - Male - Short Sleeve": "Men's Short-Sleeve Blue Shirt",
            "Shirt - Male - Long Sleeve": "Men's Long-Sleeve Blue Shirt",
            "Blouse - Female - Short Sleeve - Tuck-In": "Women's Short-Sleeve Blue Blouse (Tuck-In)",
            "Blouse - Female - Long Sleeve - Tuck-In": "Women's Long-Sleeve Blue Blouse (Tuck-In)",
            "Blouse - Female - Short Sleeve - Semi-Form Fitting": "Women's Short-Sleeve Blue Blouse (Semi-Form Fitting)",
            "Blouse - Female - Long Sleeve - Semi-Form Fitting": "Women's Long-Sleeve Blue Blouse (Semi-Form Fitting)",
            "Trousers - Male": "Men's Blue Trousers",
            "Slacks - Female": "Women's Blue Slacks",
            "Skirt - Female": "Women's Blue Skirt",
            "Neck Tie": "Men's Blue Necktie",
            "Tie Tab": "Women's Blue Tie Tab",
            "Black Low-Quarter Shoes - Male": "Men's Black Low-Quarter Shoes",
            "Black Low-Quarter Shoes - Female": "Women's Black Low-Quarter Shoes",
            "Black Pumps - Female": "Women's Black Pumps",
            "Black Flats - Female": "Women's Black Flats",
            "Coat": "OCP Coat",
            "Coat - Improved Hot Weather Combat Uniform": "Improved Hot Weather Combat Uniform (IHWCU) Coat",
            "Trousers": "OCP Trousers",
            "Trousers - Improved Hot Weather Combat Uniform": "Improved Hot Weather Combat Uniform (IHWCU) Trousers",
            "Patrol Cap": "OCP Patrol Cap",
            "Short-Sleeve Shirt": "Physical Training Gear (PTG) Short-Sleeve T-Shirt",
            "Long-Sleeve Shirt": "Physical Training Gear (PTG) Long-Sleeve T-Shirt",
            "Shirt - Dry-Wicking": "AFROTC PTG Dry-Wicking T-Shirt",
            "Shirt - Cotton": "AFROTC PTG Cotton T-Shirt",
            "Shorts - Reflective": "PTG Reflective Shorts",
            "Running Shorts - Non-Reflective": "PTG Non-Reflective Running Shorts",
            "Running Pants": "PTG Running Pants",
        }
        if category == "OCP" and item_name.endswith((" - Unisex", " - Women's")):
            return item_name.replace(" - Unisex", " – Unisex").replace(" - Women's", " – Women's")
        if item_name in official_names:
            return official_names[item_name]
        if legacy_names:
            return legacy_names[0]
        if category in {"OCP", "PTG"} and not item_name.upper().startswith(category):
            return f"{category} {item_name}"
        return item_name

    @staticmethod
    def _equipment_search_synonyms(official_name: str) -> str:
        name = official_name.casefold()
        synonyms: list[str] = []
        if "ocp coat" in name or "ihwcu) coat" in name:
            synonyms.extend(["blouse", "top", "jacket"])
        if "trousers" in name or "slacks" in name:
            synonyms.extend(["pants", "bottoms"])
        if "t-shirt" in name or "blouse" in name:
            synonyms.append("shirt")
        if "combat boots" in name:
            synonyms.extend(["footwear", "shoes"])
        if "patrol cap" in name or "flight cap" in name:
            synonyms.extend(["hat", "cover"])
        if "rank" in name:
            synonyms.append("grade insignia")
        if "service dress coat" in name:
            synonyms.append("jacket")
        if "unisex" in name:
            synonyms.extend(["male", "men", "men's", "standard"])
        if "men's" in name and "women's" not in name:
            synonyms.extend(["male", "men", "mens"])
        if "women's" in name:
            synonyms.extend(["female", "women", "womens"])
        return " ".join(synonyms)

    @staticmethod
    def _size_choices_for_equipment(category: str, official_name: str) -> tuple[str, list[str]]:
        name = official_name.casefold()
        alpha_sizes = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
        ocp_sizes = [
            f"{size}-{length}"
            for size in ("XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL")
            for length in ("SHORT", "REGULAR", "LONG")
        ]
        shoe_sizes = [
            f"{size} {width}"
            for size in ("4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12", "12.5", "13", "14", "15", "16")
            for width in ("REGULAR", "WIDE")
        ]
        if any(word in name for word in ("shoe", "boot", "pump", "flat")):
            return "Shoe Size", shoe_sizes
        if "women's" in name and any(word in name for word in ("blouse", "slacks", "skirt", "service dress coat")):
            return "Women's Garment Size", [str(size) for size in range(2, 28, 2)]
        if category == "OCP" and any(word in name for word in ("coat", "trousers")):
            label = "Women's OCP Garment Size" if "women's" in name else "Unisex OCP Garment Size"
            return label, ocp_sizes
        if "men's service dress coat" in name:
            return "Coat Size", [f"{chest}{length}" for chest in range(32, 55, 2) for length in ("S", "R", "L", "XL")]
        if "men's" in name and "blue trousers" in name:
            return "Waist × Inseam", [f"{waist}-{inseam}" for waist in range(26, 51, 2) for inseam in range(28, 37, 2)]
        if "men's" in name and "blue shirt" in name:
            return "Neck × Sleeve", [
                f"{neck:g} × {sleeve}"
                for neck in (13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 18, 18.5)
                for sleeve in (30, 32, 34, 36)
            ]
        if any(word in name for word in ("cap", "headgear")):
            return "Headgear Size", ["6 1/2", "6 5/8", "6 3/4", "6 7/8", "7", "7 1/8", "7 1/4", "7 3/8", "7 1/2", "7 5/8", "7 3/4", "7 7/8", "8"]
        if category in {"CADET RANK", "ACCOUTREMENTS"} or any(
            word in name for word in ("tape", "patch", "insignia", "badge", "cord", "belt buckle", "belt tip")
        ):
            return "Size", ["ONE SIZE"]
        return "Apparel Size", alpha_sizes

    @staticmethod
    def _choices_for_size_system(size_system: str) -> tuple[str, list[str]]:
        profiles = {
            "One Size": ["ONE SIZE"],
            "Apparel Size": ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
            "OCP Garment Size": [f"{s}-{length}" for s in ("XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL") for length in ("SHORT", "REGULAR", "LONG")],
            "Unisex OCP Garment Size": [f"{s}-{length}" for s in ("XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL") for length in ("SHORT", "REGULAR", "LONG")],
            "Women's OCP Garment Size": [f"{s}-{length}" for s in ("XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL") for length in ("SHORT", "REGULAR", "LONG")],
            "Women's Garment Size": [str(size) for size in range(2, 28, 2)],
            "Shoe Size": [f"{size} {width}" for size in ("4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12", "12.5", "13", "14", "15", "16") for width in ("REGULAR", "WIDE")],
            "Coat Size": [f"{chest}{length}" for chest in range(32, 55, 2) for length in ("S", "R", "L", "XL")],
            "Waist × Inseam": [f"{waist}-{inseam}" for waist in range(26, 51, 2) for inseam in range(28, 37, 2)],
            "Neck × Sleeve": [f"{neck:g} × {sleeve}" for neck in (13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 18, 18.5) for sleeve in (30, 32, 34, 36)],
            "Headgear Size": ["6 1/2", "6 5/8", "6 3/4", "6 7/8", "7", "7 1/8", "7 1/4", "7 3/8", "7 1/2", "7 5/8", "7 3/4", "7 7/8", "8"],
        }
        return size_system, profiles.get(size_system, profiles["Apparel Size"])

    def _variant_from_search(self, query: str) -> tuple[str, list[str]]:
        variants = set(self.service.list_catalog_values("variant"))
        rank_matches = sorted(
            (value for value in variants if value.startswith("C/")),
            key=len,
            reverse=True,
        )
        for value in rank_matches:
            phrase = value.casefold()
            if phrase in query:
                return value, [phrase]

        size_aliases = [
            ("extra extra large", "2XL"), ("double extra large", "2XL"),
            ("extra large", "XL"), ("x large", "XL"),
            ("medium", "M"), ("small", "S"), ("large", "L"),
            ("xxxl", "3XL"), ("3xl", "3XL"), ("xxl", "2XL"), ("2xl", "2XL"),
            ("xl", "XL"), ("xs", "XS"),
        ]
        size = ""
        consumed: list[str] = []
        for phrase, value in size_aliases:
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", query):
                size = value
                consumed.append(phrase)
                break

        length = ""
        for phrase, value in (("extra long", "X-LONG"), ("x long", "X-LONG"), ("regular", "REGULAR")):
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", query):
                length = value
                consumed.append(phrase)
                break
        if size and length and f"{size}-{length}" in variants:
            return f"{size}-{length}", consumed
        if size and size in variants:
            return size, consumed
        if length and length in variants:
            return length, consumed
        return "", consumed

    @staticmethod
    def _category_for_catalog_item(item_name: str, legacy_names: list[str]) -> str:
        source_names = legacy_names or [item_name]
        joined = " ".join(source_names).casefold()
        if any(marker in joined for marker in ("cadet rank", "shoulder mark rank", "velcro cadet rank")):
            return "CADET RANK"
        ocp_markers = (
            "coyote brown t-shirt", "coyote brown combat boots", "coyote brown socks",
            "dla green socks", "coyote brown rigger belt", "coyote brown fleece jacket",
            "coyote brown watch cap",
        )
        if any(marker in joined for marker in ocp_markers):
            return "OCP"
        if any(name.startswith(("OCP ",)) for name in source_names):
            return "OCP"
        if any(name.startswith(("PTG ", "AFROTC PT ")) for name in source_names):
            return "PTG"
        accoutrement_markers = (
            "badge", "shoulder cord", "candidate pin", "rank pin", "rank shield",
            "cap insignia", "medical insignia", "ceremonial", "parachutist",
        )
        if any(marker in joined for marker in accoutrement_markers):
            return "ACCOUTREMENTS"
        return "BLUES"

    def _edit_selected_item(self) -> None:
        selection = self.items_tree.selection()
        if not selection:
            self._show_error("Select an inventory barcode to edit first.")
            return

        barcode_id = str(selection[0]).upper()
        row = self.item_cache.get(barcode_id) or self.service.get_item(barcode_id)
        if not row:
            self._show_error("The selected barcode could not be loaded.")
            return

        window = tk.Toplevel(self)
        window.title(f"Edit Barcode {barcode_id}")
        window.transient(self)
        window.grab_set()
        window.minsize(600, 470)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        if self.window_icon_image is not None:
            window.iconphoto(True, self.window_icon_image)

        form = ttk.LabelFrame(window, text="Barcode and Inventory Details", padding=14)
        form.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(7, weight=1)

        item_name_var = tk.StringVar(window, value=str(row["item_name"]))
        category_var = tk.StringVar(window, value=str(row["category"]))
        variant_var = tk.StringVar(window, value=str(row["variant"]))
        item_type_var = tk.StringVar(window, value=str(row["item_type"]))
        total_var = tk.StringVar(window, value=str(row["total_quantity"]))

        ttk.Label(form, text="Barcode").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(form, text=barcode_id, style="Accent.TLabel").grid(
            row=0, column=1, sticky="w", padx=(10, 0), pady=4
        )
        ttk.Label(form, text="Item Name").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=item_name_var).grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=4
        )
        ttk.Label(form, text="Category").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form,
            textvariable=category_var,
            values=self.service.list_catalog_values("category"),
        ).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(form, text="Variant / Size").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form,
            textvariable=variant_var,
            values=self.service.list_catalog_values("variant"),
        ).grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(form, text="Item Type / Subcategory").grid(
            row=4, column=0, sticky="w", pady=4
        )
        ttk.Combobox(
            form,
            textvariable=item_type_var,
            values=self.service.list_catalog_values("item_type"),
        ).grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(form, text="New Total Quantity").grid(
            row=5, column=0, sticky="w", pady=4
        )
        ttk.Spinbox(form, from_=1, to=100000, textvariable=total_var, width=12).grid(
            row=5, column=1, sticky="w", padx=(10, 0), pady=4
        )
        ttk.Label(
            form,
            text=(
                f"Currently available: {row['available_quantity']} of {row['total_quantity']}. "
                "The new total cannot be below the number currently checked out."
            ),
            style="Subtitle.TLabel",
            wraplength=500,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 8))
        ttk.Label(form, text="Notes").grid(row=7, column=0, sticky="nw", pady=4)
        notes_text = tk.Text(form, height=7, wrap="word")
        notes_text.grid(row=7, column=1, sticky="nsew", padx=(10, 0), pady=4)
        notes_text.insert("1.0", str(row.get("notes", "")))

        def save_changes() -> None:
            def on_success(result: dict[str, Any]) -> None:
                window.destroy()
                self._after_inventory_write(result)

            self._run_action(
                lambda: self.service.update_item(
                    barcode_id=barcode_id,
                    item_name=item_name_var.get(),
                    category=category_var.get(),
                    variant=variant_var.get(),
                    item_type=item_type_var.get(),
                    total_quantity=total_var.get(),
                    notes=notes_text.get("1.0", "end-1c"),
                ),
                success_message=f"Barcode {barcode_id} was updated.",
                on_success=on_success,
            )

        buttons = ttk.Frame(form)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=window.destroy).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(buttons, text="Save Changes", command=save_changes).grid(
            row=0, column=1
        )

    def _create_manual_item(self) -> None:
        self._run_action(
            lambda: self.service.create_manual_item(
                barcode_id=self.item_barcode_var.get(),
                item_name=self.item_name_var.get(),
                category=self.item_category_var.get(),
                variant=self.item_variant_var.get(),
                item_type=self.item_name_var.get(),
                quantity=self.item_quantity_var.get(),
                notes=self._get_text(self.item_notes_text),
            ),
            success_message="Manual inventory item created.",
            on_success=self._after_inventory_write,
        )

    def _restock_item(self) -> None:
        self._run_action(
            lambda: self.service.restock_item(
                barcode_id=self.item_barcode_var.get(),
                quantity=self.item_quantity_var.get(),
                notes=self._get_text(self.item_notes_text),
            ),
            success_message="Inventory restocked.",
            on_success=self._after_inventory_write,
        )

    def _set_item_status(self, status: str) -> None:
        self._run_action(
            lambda: self.service.set_item_status(
                barcode_id=self.item_barcode_var.get(),
                status=status,
                notes=self._get_text(self.item_notes_text),
            ),
            success_message=f"Item status updated to {status}.",
            on_success=self._after_inventory_write,
        )

    def _delete_item(self) -> None:
        barcode = self.item_barcode_var.get().strip().upper()
        if not barcode:
            self._show_error("Select or enter a barcode to delete.")
            return
        confirmed = messagebox.askyesno(
            "Delete Inventory Item",
            (
                f"Permanently delete {barcode} from inventory?\n\n"
                "This will remove the item and all related checkout history for that barcode."
            ),
            parent=self,
        )
        if not confirmed:
            return
        self._run_action(
            lambda: self.service.delete_item(barcode_id=barcode),
            success_message="Inventory item deleted permanently.",
            on_success=self._after_inventory_write,
        )

    def _after_inventory_write(self, _result: object = None) -> None:
        self.refresh_all_views()
        self._clear_item_form()

    def _on_item_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.items_tree.selection()
        if not selection:
            return
        barcode_id = selection[0]
        row = self.item_cache.get(barcode_id)
        if not row:
            return
        self.item_barcode_var.set(row["barcode_id"])
        self.item_name_var.set(row["item_name"])
        self.item_category_var.set(row["category"])
        self.item_variant_var.set(row["variant"])
        self.item_type_var.set(row["item_type"])
        self.item_quantity_var.set("1")
        self._set_text(self.item_notes_text, row["notes"])
        self.item_form_status_var.set(
            f"Status: {row['status']} | Available {row['available_quantity']} / Total {row['total_quantity']}"
        )

    def _clear_item_form(self) -> None:
        self.item_barcode_var.set("")
        self.item_name_var.set("")
        self.item_category_var.set("")
        self.item_variant_var.set("")
        self.item_type_var.set("")
        self.item_quantity_var.set("1")
        self._set_text(self.item_notes_text, "")
        self.item_form_status_var.set("Status: New item")

    def _preview_generated_barcode(self) -> None:
        if not self._generator_selection_is_ready():
            return

        def on_success(result: dict[str, Any]) -> None:
            self.generator_preview_record = dict(result)
            quantity_text = (
                f"Available {result.get('available_quantity', 0)} / Total {result.get('total_quantity', 0)}"
                if result.get("action") == "restock"
                else "This inventory line is new and will start once you save it."
            )
            self.generator_result_var.set(f"{result['summary']}\n{quantity_text}")
            self._populate_tree(
                self.generator_tree,
                ["barcode_id", "item_name", "category", "variant", "item_type", "total_quantity"],
                [result],
            )

        self._run_action(
            lambda: self.service.preview_generated_barcode(
                category=self.generator_category_var.get(),
                variant=self.generator_variant_var.get(),
                item_type=self.generator_item_name_var.get(),
                item_name=self.generator_item_name_var.get(),
                wings_item_no=self.generator_wings_item_no_var.get(),
            ),
            success_message="Barcode preview generated.",
            on_success=on_success,
        )

    def _save_generated_barcode(self) -> None:
        if not self._generator_selection_is_ready():
            return

        def on_success(record: dict[str, Any]) -> None:
            action_label = "restocked" if record.get("action") == "restocked" else "created"
            self.generator_preview_record = dict(record)
            self.generator_result_var.set(
                f"Barcode {record['barcode_id']} {action_label}. "
                f"Available {record.get('available_quantity', 0)} / Total {record.get('total_quantity', 0)}."
            )
            self._populate_tree(
                self.generator_tree,
                ["barcode_id", "item_name", "category", "variant", "item_type", "total_quantity"],
                [record],
            )
            self.refresh_all_views()
            self._select_barcode_in_label_library(str(record["barcode_id"]))

        self._run_action(
            lambda: self.service.save_generated_barcode(
                category=self.generator_category_var.get(),
                variant=self.generator_variant_var.get(),
                item_type=self.generator_item_name_var.get(),
                units_per_barcode=self.generator_units_var.get(),
                item_name=self.generator_item_name_var.get(),
                notes=self._get_text(self.generator_notes_text),
                wings_item_no=self.generator_wings_item_no_var.get(),
            ),
            success_message="Barcode saved to inventory.",
            on_success=on_success,
        )

    def _clear_generator_form(self) -> None:
        self.generator_preview_record = None
        self.generator_quick_find_var.set("")
        self.generator_selected_item_var.set("No equipment selected")
        self.generator_size_label_var.set("Size")
        self.generator_size_combo["values"] = []
        self.generator_variant_var.set("")
        self.generator_units_var.set("1")
        self.generator_item_name_var.set("")
        self.generator_wings_item_no_var.set("")
        self.quick_find_result_map.clear()
        self.generator_quick_find_results.delete(0, tk.END)
        self._set_text(self.generator_notes_text, "")
        self.generator_result_var.set("")
        self._populate_tree(
            self.generator_tree,
            ["barcode_id", "item_name", "category", "variant", "item_type", "total_quantity"],
            [],
        )
        self._update_generator_preview()

    def _update_generator_preview(self, *_args: object) -> None:
        category = self.generator_category_var.get().strip().upper() or "CATEGORY"
        variant = self.generator_variant_var.get().strip().upper() or "SELECT SIZE"
        item_name = self.generator_item_name_var.get().strip() or "ITEM"
        display_name = self.generator_selected_item_var.get()
        item_token = "-".join(item_name.upper().replace("/", " ").split())
        self.generator_preview_var.set(
            f"{display_name}\nWINGS Item: {self.generator_wings_item_no_var.get() or 'Not selected'}\nSize: {variant}\n"
            f"Example barcode: {category}-{variant}-{item_token}-0001"
        )

    def _generator_selection_is_ready(self) -> bool:
        if (
            self.generator_selected_item_var.get() == "No equipment selected"
            or not self.generator_item_name_var.get().strip()
            or not self.generator_wings_item_no_var.get().strip()
        ):
            self._show_error("Use Quick Find and select an official WINGS catalog result first.")
            self.generator_quick_find_entry.focus_set()
            return False
        if not self.generator_variant_var.get().strip():
            self._show_error(f"Select or enter the {self.generator_size_label_var.get().lower()}.")
            self.generator_size_combo.focus_set()
            return False
        return True

    def _export_all_labels(self) -> None:
        self._run_action(
            lambda: self.service.export_label_book(
                barcode_quantities=dict(self.label_print_quantity_cache),
                filename_stem="all_inventory_labels",
                open_after=True,
            ),
            success_message="Full label book exported to PDF using the current print-copy settings.",
        )

    def _export_filtered_labels(self) -> None:
        self._run_action(
            lambda: self.service.export_label_book(
                search=self.label_search_var.get(),
                status_filter=self.label_status_filter_var.get(),
                barcode_quantities=self._visible_label_quantity_map(),
                filename_stem="filtered_inventory_labels",
                open_after=True,
            ),
            success_message="Filtered label PDF exported using the visible rows and their print-copy settings.",
        )

    def _export_selected_labels(self) -> None:
        selected_ids = self._selected_label_barcode_ids()
        if not selected_ids:
            self._show_error("Select one or more barcode rows in the central label library first.")
            return
        quantity_map = self._selected_label_quantity_map()
        total_labels = sum(quantity_map.values())

        self._run_action(
            lambda: self.service.export_label_book(
                barcode_ids=selected_ids,
                barcode_quantities=quantity_map,
                filename_stem="selected_inventory_labels",
                open_after=True,
            ),
            success_message=f"Selected label PDF exported for {len(selected_ids)} barcode(s) and {total_labels} total label(s).",
        )

    def _visible_label_barcode_ids(self) -> list[str]:
        if not hasattr(self, "label_library_tree"):
            return []
        return [str(item_id) for item_id in self.label_library_tree.get_children()]

    def _visible_label_quantity_map(self) -> dict[str, int]:
        barcode_ids = self._visible_label_barcode_ids()
        return {barcode_id.upper(): self.label_print_quantity_cache.get(barcode_id.upper(), 1) for barcode_id in barcode_ids}

    def _select_all_visible_labels(self) -> None:
        if not hasattr(self, "label_library_tree"):
            return
        visible_ids = self._visible_label_barcode_ids()
        if not visible_ids:
            self._show_error("There are no visible barcode rows to select.")
            return
        self.label_library_tree.selection_set(visible_ids)
        self._on_label_library_selected()

    def _clear_label_selection(self) -> None:
        if not hasattr(self, "label_library_tree"):
            return
        self.label_library_tree.selection_remove(self.label_library_tree.selection())
        self._on_label_library_selected()

    def _queue_checkout_barcode(self, _event: tk.Event | None = None) -> None:
        raw_scan = self.checkout_scan_var.get()
        if not raw_scan.strip():
            return
        try:
            barcode = extract_scanned_barcode(raw_scan)
        except ValueError as exc:
            self.checkout_scan_var.set("")
            self._show_error(str(exc))
            self._focus_checkout_scan()
            return
        try:
            quantity = max(1, int(self.checkout_qty_var.get()))
        except ValueError:
            self._show_error("Units To Add must be a whole number.")
            return

        try:
            item = self.service.get_barcode_context(barcode)
        except InventoryError as exc:
            self._show_error(str(exc))
            return

        if item["status"] in {"Retired", "Lost"}:
            self._show_error(f"{item['status']} items cannot be checked out.")
            return

        existing_quantity = int(self.checkout_queue.get(barcode, {}).get("quantity", 0))
        if int(item["available_quantity"]) < existing_quantity + quantity:
            self._show_error(
                f"Only {item['available_quantity']} unit(s) of {barcode} are currently available. "
                "Reduce the requested quantity or restock first."
            )
            return

        self.checkout_queue[barcode] = {
            "barcode_id": item["barcode_id"],
            "item_name": item["item_name"],
            "category": item["category"],
            "variant": item["variant"],
            "item_type": item["item_type"],
            "available_quantity": item["available_quantity"],
            "quantity": existing_quantity + quantity,
        }
        self._update_checkout_queue_tree()
        queue_units = sum(int(row["quantity"]) for row in self.checkout_queue.values())
        self.checkout_summary_var.set(
            f"Added {quantity} unit(s) of {item['barcode_id']} to the checkout list. "
            f"The list now contains {len(self.checkout_queue)} barcode line(s) and {queue_units} total unit(s)."
        )
        self.checkout_scan_var.set("")
        self.checkout_qty_var.set("1")
        self._focus_checkout_scan()

    def _update_checkout_queue_tree(self) -> None:
        self._populate_tree(
            self.checkout_queue_tree,
            ["barcode_id", "item_name", "category", "variant", "item_type", "available_quantity", "quantity"],
            list(self.checkout_queue.values()),
        )

    def _remove_selected_checkout_queue(self) -> None:
        selected_ids = self.checkout_queue_tree.selection()
        if not selected_ids:
            self._show_error("Select one or more checkout rows to remove.")
            return
        for barcode_id in selected_ids:
            self.checkout_queue.pop(str(barcode_id).upper(), None)
        self._update_checkout_queue_tree()
        self.checkout_summary_var.set(
            f"Checkout list updated. {len(self.checkout_queue)} barcode line(s) remain queued."
        )
        self._focus_checkout_scan()

    def _clear_checkout_queue(self) -> None:
        self.checkout_queue.clear()
        self._update_checkout_queue_tree()
        self.checkout_summary_var.set("Checkout list cleared. Scan or paste a barcode and press Enter to add it again.")
        self._focus_checkout_scan()

    def _submit_checkout(self) -> None:
        if not self.checkout_queue:
            self._show_error("Scan or paste at least one barcode into the checkout list first.")
            return

        line_items = [
            {"barcode_id": row["barcode_id"], "quantity": row["quantity"]}
            for row in self.checkout_queue.values()
        ]

        def on_success(processed_items: list[dict[str, Any]]) -> None:
            total_units = sum(int(row["quantity"]) for row in processed_items)
            self.refresh_all_views()
            self._clear_checkout_form(clear_identity=False)
            self._show_info(
                f"Checked out {total_units} unit(s) across {len(processed_items)} barcode line(s)."
            )

        self._run_action(
            lambda: self.service.checkout_items_bulk(
                line_items=line_items,
                cadet_name=self._compose_checkout_name(),
                cadet_email=self.checkout_email_var.get(),
                approved_by=self.current_admin,
                condition_notes=self._get_text(self.checkout_notes_text),
            ),
            success_message=None,
            on_success=on_success,
        )

    def _save_checkout_cadet(self) -> None:
        def on_success(cadet: dict[str, Any]) -> None:
            self.selected_cadet_id = int(cadet["cadet_id"])
            self.refresh_cadets()

        self._run_action(
            lambda: self.service.save_cadet(
                cadet_name=self._compose_checkout_name(),
                cadet_email=self.checkout_email_var.get(),
            ),
            success_message="Cadet saved for future checkout searches.",
            on_success=on_success,
        )

    def _clear_checkout_form(self, *, clear_identity: bool = True) -> None:
        self.current_checkout_barcode = None
        self.checkout_queue.clear()
        self.checkout_scan_var.set("")
        if clear_identity:
            self.checkout_last_name_var.set("")
            self.checkout_middle_initial_var.set("")
            self.checkout_first_name_var.set("")
            self.checkout_email_var.set("")
        self.checkout_qty_var.set("1")
        self.checkout_summary_var.set("Scan or paste a barcode and press Enter to add it to the checkout list.")
        self._set_text(self.checkout_notes_text, "")
        self._update_checkout_queue_tree()
        self._focus_checkout_scan()

    def _queue_return_barcode(self, _event: tk.Event | None = None) -> None:
        raw_scan = self.return_scan_var.get()
        if not raw_scan.strip():
            return
        try:
            barcode = extract_scanned_barcode(raw_scan)
        except ValueError as exc:
            self.return_scan_var.set("")
            self._show_error(str(exc))
            self.return_scan_entry.focus_set()
            return
        try:
            quantity = max(1, int(self.return_qty_var.get()))
        except ValueError:
            self._show_error("Units To Add must be a whole number.")
            return
        try:
            item = self.service.get_barcode_context(barcode)
        except InventoryError as exc:
            self._show_error(str(exc))
            return

        open_transactions = item["open_transactions"]
        if not open_transactions:
            self._show_error("This barcode has no open checkout records.")
            return

        existing_quantity = int(self.return_queue.get(barcode, {}).get("quantity", 0))
        open_units = len(open_transactions)
        if open_units < existing_quantity + quantity:
            self._show_error(
                f"Only {open_units} unit(s) of {barcode} are currently checked out. Reduce the return quantity."
            )
            return

        first_holder = open_transactions[0]
        holder_text = first_holder["cadet_name"]
        if open_units > 1:
            holder_text = f"{holder_text} (+{open_units - 1} more)"

        self.return_queue[barcode] = {
            "barcode_id": item["barcode_id"],
            "item_name": item["item_name"],
            "open_units": open_units,
            "quantity": existing_quantity + quantity,
            "current_holder": holder_text,
            "oldest_checkout": first_holder["checkout_time"],
        }
        self._update_return_queue_tree()
        queue_units = sum(int(row["quantity"]) for row in self.return_queue.values())
        self.return_summary_var.set(
            f"Added {quantity} unit(s) of {item['barcode_id']} to the return list. "
            f"The list now contains {len(self.return_queue)} barcode line(s) and {queue_units} total unit(s)."
        )
        self.return_scan_var.set("")
        self.return_qty_var.set("1")
        self.return_scan_entry.focus_set()

    def _update_return_queue_tree(self) -> None:
        self._populate_tree(
            self.return_queue_tree,
            ["barcode_id", "item_name", "open_units", "quantity", "current_holder", "oldest_checkout"],
            list(self.return_queue.values()),
        )

    def _remove_selected_return_queue(self) -> None:
        selected_ids = self.return_queue_tree.selection()
        if not selected_ids:
            self._show_error("Select one or more return rows to remove.")
            return
        for barcode_id in selected_ids:
            self.return_queue.pop(str(barcode_id).upper(), None)
        self._update_return_queue_tree()
        self.return_summary_var.set(f"Return list updated. {len(self.return_queue)} barcode line(s) remain queued.")
        self.return_scan_entry.focus_set()

    def _clear_return_queue(self) -> None:
        self.return_queue.clear()
        self._update_return_queue_tree()
        self.return_summary_var.set("Return list cleared. Scan or paste a barcode and press Enter to add it again.")
        self.return_scan_entry.focus_set()

    def _submit_return(self) -> None:
        if not self.return_queue:
            self._show_error("Scan or paste at least one barcode into the return list first.")
            return

        line_items = [
            {"barcode_id": row["barcode_id"], "quantity": row["quantity"]}
            for row in self.return_queue.values()
        ]

        def on_success(returned_rows: list[dict[str, Any]]) -> None:
            total_units = len(returned_rows)
            self.refresh_all_views()
            self._clear_return_form()
            self._show_info(
                f"Returned {total_units} unit(s) across {len(line_items)} barcode line(s)."
            )

        self._run_action(
            lambda: self.service.return_items_bulk(
                line_items=line_items,
                approved_by=self.current_admin,
                condition_notes=self._get_text(self.return_notes_text),
            ),
            success_message=None,
            on_success=on_success,
        )

    def _clear_return_form(self) -> None:
        self.current_return_barcode = None
        self.return_queue.clear()
        self.return_scan_var.set("")
        self.return_qty_var.set("1")
        self.return_summary_var.set("Scan or paste a barcode and press Enter to add it to the return list.")
        self._set_text(self.return_notes_text, "")
        self._update_return_queue_tree()
        self.return_scan_entry.focus_set()

    def _export_report(self) -> None:
        if not self.report_columns:
            self._show_error("Load a report before exporting.")
            return
        filename = filedialog.asksaveasfilename(
            title="Export Report To CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"{self.report_type_var.get().replace(' ', '_').lower()}.csv",
        )
        if not filename:
            return
        self._run_action(
            lambda: self.service.export_rows_to_csv(Path(filename), self.report_columns, self.report_rows),
            success_message=f"Report exported to {filename}",
        )

    def _export_inventory_spreadsheet(self) -> None:
        self._run_action(
            lambda: self.service.export_inventory_spreadsheet(open_after=True),
            success_message="Inventory spreadsheet exported.",
        )

    def _import_wings_inventory(self) -> None:
        filename = filedialog.askopenfilename(
            title="Import WINGS Inventory Report",
            filetypes=[
                ("WINGS Reports", "*.xls *.xlsx *.csv *.tsv"),
                ("Excel Files", "*.xls *.xlsx"),
                ("CSV Files", "*.csv *.tsv"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return
        try:
            preview = self.service.preview_wings_inventory_import(Path(filename))
        except InventoryError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive GUI handling
            self._show_error(f"Unexpected error while reading the report: {exc}")
            return

        skipped_text = ""
        if preview["skipped"]:
            examples = "\n".join(f"  - {message}" for message in preview["skipped"][:5])
            more = len(preview["skipped"]) - 5
            skipped_text = f"\n\nSkipped rows: {len(preview['skipped'])}\n{examples}"
            if more > 0:
                skipped_text += f"\n  - and {more} more"
        confirmed = messagebox.askyesno(
            "Replace Inventory from WINGS",
            (
                f"File: {Path(filename).name}\n\n"
                f"Valid WINGS rows: {preview['row_count']}\n"
                f"Total units: {preview['total_units']}\n"
                f"Issued: {preview['issued_units']}\n"
                f"Available: {preview['available_units']}"
                f"{skipped_text}\n\n"
                "This will replace all current inventory items and checkout history. "
                "Admins, cadets, and the Index will remain. A backup will be created first.\n\n"
                "If the report contains issued quantities, they will be imported under "
                "'WINGS Import - Holder Not Listed' because this summary report does not name the cadet.\n\n"
                "Continue?"
            ),
            parent=self,
        )
        if not confirmed:
            return

        def on_success(result: dict[str, Any]) -> None:
            self.refresh_all_views()
            self._set_status(
                f"Imported {result['row_count']} WINGS rows and {result['total_units']} total units."
            )

        self._run_action(
            lambda: self.service.replace_inventory_from_wings_report(Path(filename)),
            success_message="WINGS inventory imported successfully. A pre-import backup was saved.",
            on_success=on_success,
        )

    def _copy_selected_directory_barcodes(self) -> None:
        selected_ids = [str(item_id) for item_id in self.barcode_directory_tree.selection() if item_id]
        if not selected_ids:
            self._show_error("Select one or more barcode rows in the barcode directory first.")
            return
        self._copy_text_to_clipboard("\n".join(selected_ids))
        self._show_info(f"Copied {len(selected_ids)} barcode(s) to the clipboard.")

    def _copy_all_visible_directory_barcodes(self) -> None:
        visible_ids = [str(item_id) for item_id in self.barcode_directory_tree.get_children()]
        if not visible_ids:
            self._show_error("There are no visible barcode rows to copy.")
            return
        self._copy_text_to_clipboard("\n".join(visible_ids))
        self._show_info(f"Copied {len(visible_ids)} visible barcode(s) to the clipboard.")

    def _copy_text_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()

    @staticmethod
    def _select_all_tree_rows(tree: ttk.Treeview) -> None:
        row_ids = tree.get_children()
        if row_ids:
            tree.selection_set(row_ids)

    def _select_barcode_in_label_library(self, barcode_id: str) -> None:
        if not hasattr(self, "label_library_tree"):
            return
        cleaned_barcode = barcode_id.strip().upper()
        if cleaned_barcode not in self.label_library_tree.get_children():
            return
        self.label_library_tree.selection_set(cleaned_barcode)
        self.label_library_tree.focus(cleaned_barcode)
        self.label_library_tree.see(cleaned_barcode)
        self._on_label_library_selected()

    def _choose_database_path(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Select Inventory Database File",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
            initialdir=str(Path(self.settings_db_path_var.get() or self.settings.database_path).parent),
            initialfile=Path(self.settings_db_path_var.get() or self.settings.database_path).name,
        )
        if filename:
            self.settings_db_path_var.set(filename)

    def _choose_protected_backup_for_settings(self) -> None:
        current_value = self.settings_protected_backup_var.get().strip()
        initial_dir = Path(current_value).expanduser() if current_value else Path.home()
        selected = filedialog.askdirectory(
            title="Choose or Create A.C.E. Protected Backup Folder",
            initialdir=str(initial_dir),
            mustexist=False,
            parent=self,
        )
        if selected:
            self.settings_protected_backup_var.set(str(Path(selected).expanduser()))

    def _save_settings(self) -> None:
        try:
            new_settings = AppSettings(
                org_name=self.settings_org_name_var.get().strip() or self.settings.org_name,
                db_path=str(Path((self.settings_db_path_var.get().strip() or str(self.settings.database_path))).expanduser()),
                backup_interval_ops=max(1, int(self.settings_backup_interval_var.get())),
                overdue_days=self.settings.overdue_days,
                protected_backup_path=self.settings_protected_backup_var.get().strip(),
            )
        except ValueError:
            self._show_error("Backup interval must be a whole number.")
            return

        old_db_path = self.settings.database_path
        new_db_path = new_settings.database_path
        protected_dir = new_settings.protected_backup_dir
        if protected_dir is not None:
            validation_file = protected_dir / ".ace_backup_write_test"
            try:
                protected_dir.mkdir(parents=True, exist_ok=True)
                validation_file.write_text("A.C.E. backup location test", encoding="utf-8")
                validation_file.unlink(missing_ok=True)
            except OSError as exc:
                try:
                    validation_file.unlink(missing_ok=True)
                except OSError:
                    pass
                self._show_error(f"A.C.E. cannot write to the protected backup folder:\n{protected_dir}\n\n{exc}")
                return

        if new_db_path != old_db_path and not new_db_path.exists():
            copy_current = messagebox.askyesno(
                "Create Database",
                "The selected database file does not exist yet. Copy the current inventory database to that location?",
                parent=self,
            )
            if copy_current:
                self.service.clone_database(new_db_path)

        save_settings(new_settings)
        save_device_backup_settings(
            protected_backup_path=(str(protected_dir) if protected_dir is not None else ""),
            setup_completed=True,
        )
        self.settings = new_settings
        self.service.replace_settings(new_settings)
        self._load_settings_into_form()
        self.refresh_all_views()
        self._show_info("Settings saved.")

    def _manual_backup(self) -> None:
        def on_success(primary_path: Path) -> None:
            status = self.service.backup_protection_status()
            if status["last_copy_path"]:
                self._show_info(
                    "Compressed backup created in both locations.\n\n"
                    f"Portable: {primary_path}\n"
                    f"Protected: {status['last_copy_path']}"
                )
            elif status["configured_path"]:
                self._show_info(
                    "Portable backup created, but the protected location was unavailable.\n\n"
                    f"Portable: {primary_path}\n"
                    f"Protected error: {status['last_error'] or 'Unknown error'}"
                )
            else:
                self._show_info(
                    "Compressed portable backup created. No separate protected folder is configured.\n\n"
                    f"Portable: {primary_path}"
                )

        self._run_action(
            self.service.create_manual_backup,
            success_message=None,
            on_success=on_success,
        )

    def _show_credits(self) -> None:
        quote_entry = random.choice(CREDIT_QUOTES)
        quote_text = str(quote_entry.get("text") or "")
        quote_author = str(quote_entry.get("author") or "Ethan Williams")
        quote_action = str(quote_entry.get("action") or "").strip()

        window = tk.Toplevel(self)
        window.title("Credits")
        window.transient(self)
        window.grab_set()
        window.configure(bg="#eef4fb")
        window.resizable(False, False)

        container = ttk.Frame(window, padding=24)
        container.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            container,
            text=quote_text,
            style="Title.TLabel",
            wraplength=420,
            justify="center",
        ).grid(row=0, column=0, pady=(0, 18))
        author_label = tk.Label(
            container,
            text=f"{quote_author} (@pixelatedclub)",
            font=("Segoe UI", 18, "bold"),
            fg="#1f4f82",
            bg="#eef4fb",
            cursor="hand2",
        )
        author_label.grid(row=1, column=0, pady=(0, 8))
        author_label.bind(
            "<Button-1>",
            lambda _event: self._toggle_alternate_icons(window),
        )
        if quote_action == "open_hidden_easter_egg_export":
            # Diamo is the sweet one but she still scares me :D
            author_label.bind(
                "<Shift-Button-1>",
                lambda _event: self._open_hidden_easter_egg_export(),
            )
        ttk.Button(container, text="Close", command=window.destroy).grid(row=2, column=0)

    def _toggle_alternate_icons(self, parent: tk.Misc) -> None:
        enabled = not self.alternate_icons_enabled
        if not save_alternate_icons_enabled(enabled):
            messagebox.showerror(
                "Alternate Icons",
                "A.C.E. could not save the alternate-icon setting on this device.",
                parent=parent,
            )
            return

        self.alternate_icons_enabled = enabled
        self._apply_window_icon_choice(self._random_window_icon_key())
        odds = ALTERNATE_RARE_ICON_ODDS if enabled else NORMAL_RARE_ICON_ODDS
        mode = "enabled" if enabled else "disabled"
        messagebox.showinfo(
            "Alternate Icons",
            f"Alternate icons are {mode}. The rare icon chance is now 1 in {odds:,} per launch.",
            parent=parent,
        )
        parent.destroy()

    def _open_hidden_easter_egg_export(self) -> None:
        self._run_action(
            lambda: self.service.export_hidden_easter_egg_spreadsheet(open_after=True),
            success_message="Hidden easter egg spreadsheet exported.",
        )

    def _show_instructions_manual(self) -> None:
        manual_text = textwrap.dedent("""
A.C.E. Manual

1. Dashboard
- Shows live totals for inventory lines, units, checked-out units, lost items, retired items, and saved cadets.
- Recent Activity lists the newest checkout and return events.

2. Items Tab
- Create Manual Item adds a barcode record directly.
- Edit Selected Barcode changes the selected item's description, classification, notes, or total quantity without replacing its barcode.
- Restock Barcode increases quantity for an existing barcode.
- Set Available, Mark Lost, and Retire update status.
- Delete Permanently removes the barcode and its checkout history from the program.

3. Barcode Generator
- Type the complete equipment description in Quick Find; the results update without interrupting typing.
- Select the correctly named equipment result. Internal category and classification are filled automatically.
- Choose from sizes specific to that equipment, enter the quantity, and save.
- OCP tops use the official term OCP Coat. Searches for "OCP blouse" still work.
- OCP and IHWCU coats/trousers distinguish Unisex and Women's configurations.
- Preview Barcode checks for the same category + item + variant. An exact match is restocked automatically.
- Save Barcode writes that inventory line into the database.
- Export Full Label Book uses the current print-copy settings for the entire label library.
- Export Filtered PDF uses the visible filtered rows and their print-copy settings.
- Export Selected PDF uses only the label-library rows you selected.
- Use Selected Print Copies to choose how many stickers print for each selected barcode.

4. Index
- Lists the available official WINGS records plus detailed local additions.
- Search by WINGS item number, official name, size, category, sex, stock number, or unit.
- Sort by full ten-digit WINGS item number or by category and name.
- Source identifies the official WINGS reference, local Index records, and custom additions.
- Add WINGS Item creates a complete official record with item number, name, size, category,
  subcategory, sex, stock number, UoM, and source.
- Manually added WINGS items become available in Index search, Quick Find, and compliant exports.
- Add Custom Item collects the same descriptive fields but assigns a LOCAL number and excludes it from WINGS exports.
- Category and subcategory fields suggest values already used in the catalog or inventory while still allowing new values.
- The local rank catalog includes Soft Blues, Hard Blues, and OCP patches from GMC 100 through C/Col.
- WINGS rows are reference records and do not mean an item is currently stocked.
- Click a row to select it, or use Ctrl-click and Shift-click to select multiple rows.
- Delete Selected from Index hides official catalog rows and permanently deletes selected custom rows.
- Restore Hidden Items returns all hidden official catalog rows to the Index.
- Hiding an official row never removes inventory and never removes it from a compliant WINGS export.
- Custom entries become available in Quick Find immediately but do not create inventory.

5. WINGS Export
- Shows only stocked inventory mapped to an official WINGS item number.
- Excludes local, custom, and zero-stock Index records.
- Import WINGS Inventory reads a WINGS .xls, .xlsx, or CSV report and replaces current inventory after making a backup.
- Generate WINGS Excel Spreadsheet creates the exact 13-column WINGS workbook with Source last.
- Item numbers are sorted numerically and preserved in ten-digit WINGS format.

6. Checkout / Return
- The app opens with an admin code prompt before anyone can use checkout or return.
- Det005 is the cadre administrator code and signs in as CADRE.
- On the first login on each Windows device, choose a protected backup folder. A folder on another drive, this computer, or OneDrive is recommended.
- The device remembers this setup, so the prompt does not appear on every launch. Change the location later in Settings.
- The live inventory remains with A.C.E. on the portable drive. The protected folder receives separate compressed recovery copies.
- Scan by typing or pasting a barcode and pressing Enter.
- Scanner-added timestamps or other prefix/suffix text are removed automatically when one valid barcode is present.
- Each scan adds the barcode to a checkout list or return list instead of processing immediately.
- Enter the cadet name using three boxes: Last, MI, First.
- Cadet email only needs to be a valid email address with an @ symbol.
- Save Cadet stores the cadet for future lookups.
- Check Out Queued Items issues the full queued list and logs which admin approved it.
- Return Queued Items brings back the full queued list and also logs the approving admin.

7. Barcode Directory
- Shows every barcode currently in the system in one place.
- Search or filter the list, then copy selected or all visible barcodes to the clipboard.
- Use this tab when the scanner is unavailable and you need to paste barcodes manually.

8. Cadets Tab
- Save cadets manually or let checkout save them.
- Search by name or email.
- Select a cadet to see currently checked-out items and full transaction history.
- Export Cadet History creates a dated Excel workbook for the selected cadet.
- Use the bottom scroll bar in the cadet history tables or open View Selected Transaction for a readable full-detail window.
- Delete Cadet removes the saved cadet record while preserving all checkout history snapshots.
- Load Into Checkout copies that cadet into the checkout screen.

9. Reports
- Checked Out Items shows open issues.
- Transaction History shows all checkout and return records.
- Export CSV saves the current report.
- Export WINGS Spreadsheet creates the same official-stock-only workbook as the WINGS Export tab.

10. Settings
- Set the portable SQLite database location.
- Set or change the protected backup folder.
- Configure backup frequency. Backups are compressed ZIP files.
- A.C.E. keeps the newest 10 backups in the portable and protected locations and removes older copies automatically.
- Create Backup Now makes an extra compressed database backup and verifies the protected copy when configured.
- Admin Security lets you add custom admin codes, deactivate them, delete them permanently, and switch the active admin session.
- When signed in as CADRE, selecting an admin in Admin Security also reveals that saved code.
- Transfer Device builds a single Windows EXE containing the current app snapshot and data for another device.
- Credits opens the project credit screen.
- In Credits, click @pixelatedclub to toggle alternate icon mode. Rare icons use 1-in-4 odds in alternate mode and 1-in-4,000 odds normally.

11. Printing Labels
- PDFs are stored in the labels folder next to the database.
- The PDF layout uses the Premium Label Supply PLS892 template: 2" x 1" labels on letter paper, 40 labels per sheet.
- Print at Actual Size or 100% scale with Fit To Page disabled for best barcode accuracy.
- The scanner acceptance PDF fills one complete PLS892 sheet so all four columns and ten rows can be checked.

12. Data Notes
- Identical items can share one barcode by increasing quantity.
- New generated barcodes use the lowest currently unused A-number.
- The system blocks negative inventory.
- Deleting an item permanently removes that barcode and its transactions.
""").strip()

        window = tk.Toplevel(self)
        window.title("Instructions Manual")
        window.transient(self)
        window.grab_set()
        window.geometry("900x700")
        window.configure(bg="#eef4fb")

        container = ttk.Frame(window, padding=16)
        container.grid(row=0, column=0, sticky="nsew")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(container, text="Instructions Manual", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        text_frame = ttk.Frame(container)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        manual_box = tk.Text(
            text_frame,
            wrap="word",
            font=("Segoe UI", 11),
            bg="white",
            fg="#0f172a",
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=12,
        )
        manual_box.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=manual_box.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        manual_box.configure(yscrollcommand=scroll.set)
        manual_box.insert("1.0", manual_text)
        manual_box.configure(state="disabled")

        ttk.Button(container, text="Close", command=window.destroy).grid(row=2, column=0, sticky="e", pady=(10, 0))

    def _load_settings_into_form(self) -> None:
        self.settings_org_name_var.set(self.settings.org_name)
        self.settings_db_path_var.set(str(self.settings.database_path))
        self.settings_protected_backup_var.set(
            str(self.settings.protected_backup_dir) if self.settings.protected_backup_dir is not None else ""
        )
        self.settings_backup_interval_var.set(str(self.settings.backup_interval_ops))
        self.settings_overdue_days_var.set(str(self.settings.overdue_days))

    def _run_action(
        self,
        action: Callable[[], Any],
        *,
        success_message: str | None,
        on_success: Callable[[Any], None] | None = None,
    ) -> None:
        try:
            result = action()
        except InventoryError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive GUI handling
            self._show_error(f"Unexpected error: {exc}")
            return

        if on_success is not None:
            on_success(result)
        if success_message:
            self._show_info(success_message)

    def _populate_tree(self, tree: ttk.Treeview, columns: list[str], rows: list[dict[str, Any]]) -> None:
        tree.delete(*tree.get_children())
        tree["columns"] = columns
        for column in columns:
            heading_text = column if column in WINGS_COLUMNS else column.replace("_", " ").title()
            tree.heading(column, text=heading_text)
            width = 130
            if column in {"notes", "condition_notes"}:
                width = 340
            elif column in {"item_name", "cadet_email", "equipment_name"}:
                width = 240
            elif column in {"current_holder"}:
                width = 240
            elif column in {"oldest_checkout", "checkout_time", "return_time", "last_checkout_time", "created_at", "updated_at"}:
                width = 180
            elif column in {"barcode_id", "email"}:
                width = 185
            elif column in {"full_name", "cadet_name"}:
                width = 240
            elif column in {"approved_by_name", "return_approved_by_name"}:
                width = 210
            elif column in {"approved_by_role", "return_approved_by_role"}:
                width = 150
            elif column in {"category", "variant", "item_type"}:
                width = 145
            elif column in {"transaction_id", "cadet_id", "admin_id"}:
                width = 95
            elif column in {"print_copies"}:
                width = 95
            elif column in {"Item No", "Stock #"}:
                width = 125
            elif column in {"Item Name"}:
                width = 240
            elif column in {"Qty Issued", "Qty Available", "Total in Inventory"}:
                width = 115
            elif column in {"Size", "Sex", "UoM", "Source"}:
                width = 95
            tree.column(column, width=width, minwidth=90, anchor="w")

        for index, row in enumerate(rows):
            values = [row.get(column, "") for column in columns]
            if hasattr(self, "cadet_tree") and tree is self.cadet_tree:
                item_id = str(row.get("cadet_id", f"row-{index}"))
            elif hasattr(self, "admin_tree") and tree is self.admin_tree:
                item_id = str(row.get("admin_id", f"row-{index}"))
            elif (
                hasattr(self, "items_tree")
                and (
                    tree is self.items_tree
                    or tree is getattr(self, "label_library_tree", None)
                    or tree is getattr(self, "generator_tree", None)
                    or tree is getattr(self, "barcode_directory_tree", None)
                    or tree is getattr(self, "checkout_queue_tree", None)
                    or tree is getattr(self, "return_queue_tree", None)
                )
            ):
                item_id = str(row.get("barcode_id", f"row-{index}"))
            else:
                item_id = f"row-{index}"
            tree.insert("", "end", iid=str(item_id), values=values)

    @staticmethod
    def _create_tree(parent: ttk.Frame, columns: list[str], *, selectmode: str = "browse") -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode=selectmode)
        vertical_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        horizontal_scrollbar = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical_scrollbar.set, xscrollcommand=horizontal_scrollbar.set)
        tree.grid_configure(padx=(0, 6), pady=(0, 6))
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        return tree

    @staticmethod
    def _selected_tree_row(tree: ttk.Treeview) -> dict[str, str] | None:
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0], "values")
        columns = list(tree["columns"])
        return {str(column): str(values[index]) if index < len(values) else "" for index, column in enumerate(columns)}

    @staticmethod
    def _get_text(widget: tk.Text) -> str:
        return widget.get("1.0", "end").strip()

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    @staticmethod
    def _apply_password_visibility(entry: ttk.Entry, *, visible: bool, toggle_text_var: tk.StringVar) -> None:
        entry.configure(show="" if visible else "*")
        toggle_text_var.set("Hide" if visible else "Show")

    def _show_error(self, message: str) -> None:
        self._set_status(f"Error: {message}")
        messagebox.showerror("Inventory Error", message, parent=self._dialog_parent())

    def _show_info(self, message: str) -> None:
        self._set_status(message)
        messagebox.showinfo(APP_TITLE, message, parent=self._dialog_parent())

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _dialog_parent(self) -> tk.Misc | None:
        return self if self.winfo_exists() and self.winfo_viewable() else None

    def _focus_checkout_scan(self) -> None:
        self.checkout_scan_entry.focus_set()

    def _on_tab_changed(self, _event: tk.Event | None = None) -> None:
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if current_tab == "Checkout / Return":
            self._focus_checkout_scan()
        elif current_tab == "WINGS Export":
            self.refresh_wings_export()
