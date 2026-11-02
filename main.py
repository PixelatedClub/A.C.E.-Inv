from __future__ import annotations


import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
    os.environ.setdefault("TCL_LIBRARY", str(bundle_dir / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(bundle_dir / "_tk_data"))


from inventory_app import InventoryApp, load_settings
from inventory_app.completion_sound import show_error
from inventory_app.config import APP_TITLE, BASE_DIR
from inventory_app.usb_portable import has_marker, read_marker
from inventory_app.single_instance import SingleInstanceGuard


SINGLE_INSTANCE_MUTEX = r"Local\TeamShapes.ACE.InventorySystem"


def startup_error(message):
    import tkinter as tk
    root=tk.Tk();root.withdraw()
    try:show_error('A.C.E. could not open inventory',message,parent=root)
    finally:root.destroy()


def startup_settings(arguments):
    marker=read_marker(BASE_DIR)
    if marker and marker['schema']=='ace.usb.v1':
        raise ValueError('This USB is an installation package. Run Set Up A.C.E.exe, then use ACE Inventory on the desktop. The working program and inventory run on the computer.')
    flag=next((f for f in ('--usb-package','--installed-package') if f in arguments),None)
    if flag:
        index=arguments.index(flag)
        marker=read_marker(BASE_DIR)
        if index+1>=len(arguments) or not marker or marker['package_id']!=arguments[index+1]:
            raise ValueError('The expected A.C.E. installation is missing or changed. No other inventory was opened.')
    return load_settings()


def main() -> None:
    with SingleInstanceGuard.acquire(SINGLE_INSTANCE_MUTEX) as instance:
        if not instance.is_primary:
            if '--usb-package' in sys.argv or '--installed-package' in sys.argv or has_marker(BASE_DIR):
                startup_error('A.C.E. is already running. Close the current copy before opening another inventory.')
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
