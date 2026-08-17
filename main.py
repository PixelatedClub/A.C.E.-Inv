from __future__ import annotations

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
    os.environ.setdefault("TCL_LIBRARY", str(bundle_dir / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(bundle_dir / "_tk_data"))


from inventory_app import InventoryApp, load_settings


def main() -> None:
    app = InventoryApp(load_settings())
    app.mainloop()


if __name__ == "__main__":
    main()
