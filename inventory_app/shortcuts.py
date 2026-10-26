"""Non-destructive inventory navigation and checkout staging shortcuts."""
import tkinter as tk
import sys
from tkinter import ttk


def show_shortcut_guide(app):
    window=tk.Toplevel(app);window.title('Keyboard Shortcuts');window.transient(app)
    text=('Ctrl+F or Ctrl+1: Items search\nCtrl+2: Checkout\nCtrl+3: Reports\n'
          'Ctrl+Enter in Items or Label Library: queue selected items\nDelete in checkout list: remove selected queued rows\n\n'
          'Ctrl+G: Barcode Generator\nCtrl+L: Temporary Loans\nCtrl+M: Cadet Fitting\nCtrl+I: Index\n'
          'Ctrl+R: Returns\nCtrl+T: Tags / image for the selected item (Items tab)\n'
          'Shortcuts do not finalize transactions.\n\n'
          'Right-click Items or Label Library: checkout menu\n'
          'Drag panel dividers to resize; double-click a divider to reset.')
    ttk.Label(window,text=text,justify='left',padding=20,wraplength=600).pack(fill='both',expand=True)
    ttk.Button(window,text='Close',command=window.destroy).pack(pady=(0,12))


class DirectShortcuts:
    """Handle recognized Ctrl+letter keys before Entry/Text class bindings."""
    def __init__(self,app,actions):
        self.app=app;self.actions=actions

    def key(self,event):
        if self.app.grab_current() is not None:
            return
        key=event.keysym.casefold()
        # On Windows Mod1 (0x8) means Num Lock, not Alt.
        alt_mask = (0x20000 | 0x10) if sys.platform == 'win32' else 0x8
        if event.state & 4 and not event.state & alt_mask and key in self.actions:
            self.actions[key]()
            return 'break'


def queue_selected(app, tree):
    """Stage one unit per selected barcode using the normal availability checks."""
    selected = list(tree.selection())
    if not selected:
        app._show_error('Select at least one inventory barcode first.')
        return 'break'
    # Do not discard a partially entered scanner value or quantity.
    scan, quantity = app.checkout_scan_var.get(), app.checkout_qty_var.get()
    try:
        for barcode in selected:
            app.checkout_scan_var.set(str(barcode))
            app.checkout_qty_var.set('1')
            app._queue_checkout_barcode()
    finally:
        app.checkout_scan_var.set(scan)
        app.checkout_qty_var.set(quantity)
    app.notebook.select(app.checkout_tab)
    app.checkout_notebook.select(app.standard_checkout_tab)
    app._focus_checkout_scan()
    return 'break'


def install_shortcuts(app):
    for tree in (app.items_tree, app.label_library_tree):
        menu = tk.Menu(tree, tearoff=False)
        menu.add_command(label='Add to checkout list (1 each)',
                         command=lambda t=tree: queue_selected(app, t))
        def popup(event, t=tree, m=menu):
            row = t.identify_row(event.y)
            if not row:
                return 'break'
            if row not in t.selection():
                t.selection_set(row)
            t.focus(row)
            t.focus_set()
            try:
                m.tk_popup(event.x_root, event.y_root)
            finally:
                m.grab_release()
            return 'break'
        tree.bind('<Button-3>', popup)
        tree.bind('<Control-Return>', lambda e, t=tree: queue_selected(app, t))

    def navigate(tab, focus=None):
        # Toplevel dialogs must keep ownership of their keyboard shortcuts.
        if app.grab_current() is not None:
            return
        app.notebook.select(tab)
        if tab is app.checkout_tab:
            app.checkout_notebook.select(app.standard_checkout_tab)
        if focus:
            focus()
        return 'break'

    app.bind('<Control-f>', lambda e: navigate(app.items_tab, app.item_search_entry.focus_set))
    app.bind('<Control-Key-1>', lambda e: navigate(app.items_tab, app.item_search_entry.focus_set))
    app.bind('<Control-Key-2>', lambda e: navigate(app.checkout_tab, app._focus_checkout_scan))
    app.bind('<Control-Key-3>', lambda e: navigate(app.reports_tab))
    app.checkout_queue_tree.bind('<Delete>', lambda e: (app._remove_selected_checkout_queue(), 'break')[1])
    def loans():
        navigate(app.returns_tab)
        app.returns_notebook.select(app.loans_tab)
    def returns():
        navigate(app.returns_tab)
        app.returns_notebook.select(app.standard_returns_tab)
    def tags():
        if app.notebook.select()!=str(app.items_tab):return
        from .item_metadata_ui import edit_metadata
        edit_metadata(app)
    app.direct_shortcuts=DirectShortcuts(app,{
        'f':lambda:navigate(app.items_tab,app.item_search_entry.focus_set),
        'g':lambda:navigate(app.generator_tab), 'l':loans,
        'm':lambda:navigate(app.cadet_fitting_tab), 'i':lambda:navigate(app.index_tab),
        'r':returns, 't':tags})
    tag='ACEDirectShortcuts'+str(id(app))
    app.bind_class(tag,'<KeyPress>',app.direct_shortcuts.key)
    def attach(widget):
        if tag not in widget.bindtags():widget.bindtags((tag,)+widget.bindtags())
        for child in widget.winfo_children():attach(child)
    app._attach_direct_shortcuts=attach
    attach(app)
