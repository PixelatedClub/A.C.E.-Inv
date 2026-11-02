from __future__ import annotations

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
    os.environ.setdefault("TCL_LIBRARY", str(bundle_dir / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(bundle_dir / "_tk_data"))


from inventory_app import InventoryApp, load_settings
from inventory_app.config import APP_TITLE, BASE_DIR
from inventory_app.usb_portable import MARKER, read_marker
from inventory_app.single_instance import SingleInstanceGuard


SINGLE_INSTANCE_MUTEX = r"Local\TeamShapes.ACE.InventorySystem"


def startup_error(message):
    import tkinter as tk
    from tkinter import messagebox
    root=tk.Tk();root.withdraw()
    try:messagebox.showerror('A.C.E. could not open inventory',message,parent=root)
    finally:root.destroy()


def startup_settings(arguments):
    if '--usb-package' in arguments:
        index=arguments.index('--usb-package')
        marker=read_marker(BASE_DIR)
        if index+1>=len(arguments) or not marker or marker['package_id']!=arguments[index+1]:
            raise ValueError('The expected A.C.E. USB is missing or changed. Reconnect the correct drive. No other inventory was opened.')
    return load_settings()


def main() -> None:
    with SingleInstanceGuard.acquire(SINGLE_INSTANCE_MUTEX) as instance:
        if not instance.is_primary:
            if '--usb-package' in sys.argv or (BASE_DIR/MARKER).exists():
                startup_error('A.C.E. is already running. Close the current copy, then open ACE USB so the correct inventory is used.')
                return
            instance.activate_existing_window(APP_TITLE)
            return
        try:
            settings=startup_settings(sys.argv[1:])
        except Exception as error:
            startup_error(str(error))
            return
        app = InventoryApp(settings, preload_catalog=True)
        app.mainloop()


if __name__ == "__main__":
    main()
