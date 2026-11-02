"""Frozen entry point for the optional A.C.E. USB setup utility."""
import os
import sys
from pathlib import Path
if getattr(sys,'frozen',False) and hasattr(sys,'_MEIPASS'):
    bundle=Path(sys._MEIPASS)
    os.environ.setdefault('TCL_LIBRARY',str(bundle/'_tcl_data'))
    os.environ.setdefault('TK_LIBRARY',str(bundle/'_tk_data'))
from inventory_app.usb_setup import main
if __name__=='__main__':main()
