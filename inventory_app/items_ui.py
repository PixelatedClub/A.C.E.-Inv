"""Compact Items workspace retained from the locally deployed 1.6.9 design."""
import tkinter as tk
from tkinter import ttk
from .barcode_utils import SCANNED_BARCODE_PATTERN, extract_scanned_barcode
from .layout import ResizableSplit, ScrollablePanel


def build_items_tab(app):
    tab=app.items_tab
    tab.columnconfigure(0,weight=3);tab.columnconfigure(1,weight=1);tab.rowconfigure(1,weight=1)
    controls=ttk.Frame(tab);controls.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,10))
    ttk.Label(controls,text='Search / scan barcode').pack(side='left')
    entry=ttk.Entry(controls,textvariable=app.item_search_var,width=40);entry.pack(side='left',padx=6)
    app.item_search_entry=entry
    entry.bind('<KeyRelease>',lambda e:app.refresh_items_tree() if e.keysym not in ('Return','KP_Enter') else None)
    entry.bind('<Return>',lambda e:submit_item_search(app,entry))
    entry.bind('<KP_Enter>',lambda e:submit_item_search(app,entry))
    ttk.Button(controls,text='Find',command=lambda:submit_item_search(app,entry)).pack(side='left')
    status=ttk.Combobox(controls,textvariable=app.item_status_filter_var,values=['All','Available','Checked Out','Lost','Retired'],state='readonly',width=15)
    status.pack(side='left');status.bind('<<ComboboxSelected>>',lambda e:app.refresh_items_tree())
    ttk.Button(controls,text='Refresh',command=app.refresh_items_tree).pack(side='left',padx=8)
    actions=ttk.Frame(tab);actions.grid(row=5,column=0,columnspan=2,sticky='ew',pady=4)
    ttk.Button(actions,text='New Manual Barcode...',command=app._create_manual_item).pack(side='left')
    ttk.Button(actions,text='Add Custom Item...',command=app._open_add_custom_item_dialog).pack(side='left',padx=4)
    ttk.Button(actions,text='Export WINGS',command=app._export_inventory_spreadsheet).pack(side='left',padx=4)
    ttk.Button(actions,text='Copy All Visible',command=app._copy_all_visible_item_barcodes).pack(side='left',padx=4)
    ttk.Button(actions,text='Copy Selected Barcode(s)',command=app._copy_selected_item_barcodes).pack(side='left',padx=4)
    app.items_split=ResizableSplit(tab,fraction=0.7)
    app.items_split.grid(row=1,column=0,columnspan=2,sticky='nsew')
    frame=ttk.LabelFrame(app.items_split,text='Inventory Items',padding=8)
    app.items_split.add(frame,minsize=300,stretch='always')
    frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
    app.items_tree=app._create_tree(frame,['barcode_id','wings_item_no','item_name','category','variant','item_type','status','total_quantity','available_quantity','count_status'],selectmode='extended')
    app.items_tree.grid(row=0,column=0,sticky='nsew');app.items_tree.bind('<<TreeviewSelect>>',app._on_item_selected)
    app.items_tree.bind('<Double-1>',lambda e:app._edit_selected_item())
    ttk.Label(tab,textvariable=app.item_list_summary_var).grid(row=2,column=0,sticky='w',pady=(8,0))
    filters=ttk.Frame(tab);filters.grid(row=3,column=0,columnspan=2,sticky='ew',pady=4)
    app.item_tag_filter_var=tk.StringVar()
    ttk.Label(filters,text='Tags (match all, comma separated)').pack(side='left')
    tag_entry=ttk.Combobox(filters,textvariable=app.item_tag_filter_var,width=45)
    tag_entry.pack(side='left',padx=6)
    def tag_choices():
        needle=app.item_tag_filter_var.get().split(',')[-1].strip().casefold()
        tag_entry.configure(values=sorted({tag for row in app.service.list_items() for tag in row['tags'] if needle in tag}))
    tag_entry.configure(postcommand=tag_choices)
    tag_entry.bind('<Return>',lambda e:app.refresh_items_tree())
    tag_entry.bind('<<ComboboxSelected>>',lambda e:app.refresh_items_tree())
    ttk.Button(filters,text='Apply tags',command=app.refresh_items_tree).pack(side='left')
    ttk.Button(filters,text='Clear tags',command=lambda:(app.item_tag_filter_var.set(''),app.refresh_items_tree())).pack(side='left')
    app.item_count_filter_var=tk.StringVar(value='All counts')
    ttk.Label(filters,text='Counting').pack(side='left',padx=(12,4))
    counts=ttk.Combobox(filters,textvariable=app.item_count_filter_var,
        values=['All counts','Not counted','Counted','Counted zero'],state='readonly',width=16)
    counts.pack(side='left');counts.bind('<<ComboboxSelected>>',lambda e:app.refresh_items_tree())
    panel_frame=ttk.LabelFrame(app.items_split,text='Selected Item (drag divider to resize)',padding=4)
    app.items_split.add(panel_frame,minsize=250,stretch='always')
    scroller=ScrollablePanel(panel_frame);scroller.pack(fill='both',expand=True)
    panel=scroller.body
    app.item_detail_var=tk.StringVar(value='Select an item to manage it.')
    detail=ttk.Label(panel,textvariable=app.item_detail_var,wraplength=340,justify='left');detail.pack(fill='x',pady=(0,15))
    status_label=ttk.Label(panel,textvariable=app.item_form_status_var,wraplength=340);status_label.pack(fill='x')
    panel.bind('<Configure>',lambda e:[label.configure(wraplength=max(100,e.width-20)) for label in (detail,status_label)],add='+')
    from .item_metadata_ui import edit_metadata
    ttk.Button(panel,text='Tags / View or Add Image...',command=lambda:edit_metadata(app)).pack(fill='x',pady=4)
    ttk.Button(panel,text='Record Physical Count...',command=lambda:record_count(app)).pack(fill='x',pady=4)
    stock=ttk.LabelFrame(panel,text='Add Stock',padding=10);stock.pack(fill='x',pady=12)
    ttk.Label(stock,text='Quantity to add').pack(anchor='w')
    ttk.Spinbox(stock,from_=1,to=100000,textvariable=app.item_quantity_var,width=10).pack(anchor='w')
    ttk.Label(stock,text='Optional action note').pack(anchor='w',pady=(8,0))
    app.item_notes_text=tk.Text(stock,height=2,width=36,wrap='word');app.item_notes_text.pack(fill='x')
    ttk.Button(stock,text='Add Quantity',command=app._restock_item).pack(fill='x',pady=(8,0))
    for label,command in [('Edit Details...',app._edit_selected_item),('Print One Label',lambda:print_label(app)),('Set Available',lambda:app._set_item_status('Available')),('Mark Lost',lambda:app._set_item_status('Lost')),('Retire Barcode',lambda:app._set_item_status('Retired')),('Clear Selection',app._clear_item_form),('Delete Barcode Permanently',app._delete_item)]:
        ttk.Button(panel,text=label,command=command).pack(fill='x',pady=3)


def submit_item_search(app, entry):
    """Scanner Enter resolves a barcode without editing stock or checking it out."""
    query=app.item_search_var.get().strip()
    record=app.service.get_item(query) if query else None
    app._clear_item_form()
    if not record and SCANNED_BARCODE_PATTERN.search(query):
        try:
            query=extract_scanned_barcode(query)
        except ValueError as exc:
            app._show_error(str(exc))
            entry.focus_set()
            entry.selection_range(0,tk.END)
            return 'break'
        app.item_search_var.set(query)
        record=app.service.get_item(query)
    if record:
        # A checked-out/retired item must remain findable despite a stale filter.
        app.item_status_filter_var.set('All')
        app.item_search_var.set(record['barcode_id'])
        if hasattr(app,'item_tag_filter_var'):
            app.item_tag_filter_var.set('')
        if hasattr(app,'item_count_filter_var'):app.item_count_filter_var.set('All counts')
    app.refresh_items_tree()
    if record and record['barcode_id'] in app.item_cache:
        barcode=record['barcode_id']
        app.items_tree.selection_set(barcode)
        app.items_tree.focus(barcode)
        app.items_tree.see(barcode)
        app._on_item_selected()
    entry.focus_set()
    entry.selection_range(0,tk.END)
    return 'break'


def print_label(app):
    barcode=app.item_barcode_var.get()
    if not barcode:app._show_error('Select a barcode first.');return
    app._run_action(lambda:app.service.export_label_book(barcode_ids=[barcode],barcode_quantities={barcode:1},filename_stem=barcode+'_label'),success_message='One label exported.')

def record_count(app):
    barcode=app.item_barcode_var.get()
    if not barcode:app._show_error('Select the item you counted first.');return
    item=app.service.get_item(barcode)
    window=tk.Toplevel(app);window.title('Record Physical Inventory Count');window.transient(app);window.grab_set()
    form=ttk.Frame(window,padding=16);form.pack(fill='both',expand=True)
    ttk.Label(form,text=f"{item['item_name']} ({item['variant']})",wraplength=550,
        style='Title.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
    count=tk.StringVar(window,value=str(item['available_quantity']))
    note=tk.StringVar(window)
    ttk.Label(form,text='Available units physically counted').grid(row=1,column=0,sticky='w')
    ttk.Spinbox(form,from_=0,to=100000,textvariable=count,width=12).grid(row=1,column=1,padx=10)
    ttk.Label(form,text='Count only the units on hand. Existing cadet checkouts remain included in the total.',
        wraplength=550).grid(row=2,column=0,columnspan=2,sticky='w',pady=10)
    ttk.Label(form,text='Count note (optional)').grid(row=3,column=0,sticky='w')
    ttk.Entry(form,textvariable=note,width=36).grid(row=3,column=1,sticky='ew',padx=10)
    def saved(result):
        window.destroy();app._after_inventory_write(result)
    ttk.Button(form,text='Record Count',command=lambda:app._run_action(
        lambda:app.service.record_available_count(barcode_id=barcode,available_quantity=count.get(),
            approved_by=app.current_admin,notes=note.get()),
        success_message='Physical count saved. This item is now marked Counted.',on_success=saved)).grid(row=4,column=1,sticky='e',pady=12)


def create_manual_item(app):
    window=tk.Toplevel(app);window.title('Create Manual Barcode');window.transient(app);window.grab_set()
    form=ttk.Frame(window,padding=16);form.pack(fill='both',expand=True);form.columnconfigure(1,weight=1)
    ttk.Label(form,text='Use Barcode Generator for normal WINGS/custom stock.\nUse this dialog to retain a specific physical barcode.').grid(row=0,column=0,columnspan=2,pady=10)
    variables={}
    for row,(key,label) in enumerate([('barcode_id','Barcode'),('item_name','Item Name'),('category','Category'),('variant','Size / Variant'),('item_type','Item Type'),('quantity','Starting Quantity'),('notes','Optional Notes')],1):
        variables[key]=tk.StringVar(window,value='1' if key=='quantity' else '')
        ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=4)
        if key in ('category','variant','item_type','item_name'):
            widget=ttk.Combobox(form,textvariable=variables[key],values=app.service.list_catalog_values(key))
        else:widget=ttk.Entry(form,textvariable=variables[key],width=45)
        widget.grid(row=row,column=1,sticky='ew',padx=8)
    def save():
        app._run_action(lambda:app.service.create_manual_item(**{k:v.get() for k,v in variables.items()}),success_message='Manual barcode created.',on_success=lambda r:(window.destroy(),app._after_inventory_write(r)))
    ttk.Button(form,text='Create Barcode',command=save).grid(row=8,column=1,pady=12,sticky='e')
