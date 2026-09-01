from __future__ import annotations

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
    os.environ.setdefault("TCL_LIBRARY", str(bundle_dir / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(bundle_dir / "_tk_data"))


from inventory_app import InventoryApp, load_settings
from inventory_app.config import APP_TITLE
from inventory_app.single_instance import SingleInstanceGuard


SINGLE_INSTANCE_MUTEX = r"Local\TeamShapes.ACE.InventorySystem"


def main() -> None:
    with SingleInstanceGuard.acquire(SINGLE_INSTANCE_MUTEX) as instance:
        if not instance.is_primary:
            instance.activate_existing_window(APP_TITLE)
            return
        app = InventoryApp(load_settings())
        app.mainloop()


if __name__ == "__main__":
    main()
