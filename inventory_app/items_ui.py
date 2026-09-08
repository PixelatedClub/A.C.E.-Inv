"""Compact Items workspace retained from the locally deployed 1.6.9 design."""
import tkinter as tk
from tkinter import ttk


def build_items_tab(app):
    tab=app.items_tab
    tab.columnconfigure(0,weight=3);tab.columnconfigure(1,weight=1);tab.rowconfigure(1,weight=1)
    controls=ttk.Frame(tab);controls.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,10))
    ttk.Label(controls,text='Search').pack(side='left')
    entry=ttk.Entry(controls,textvariable=app.item_search_var,width=40);entry.pack(side='left',padx=6)
    entry.bind('<KeyRelease>',lambda e:app.refresh_items_tree())
    status=ttk.Combobox(controls,textvariable=app.item_status_filter_var,values=['All','Available','Checked Out','Lost','Retired'],state='readonly',width=15)
    status.pack(side='left');status.bind('<<ComboboxSelected>>',lambda e:app.refresh_items_tree())
    ttk.Button(controls,text='Refresh',command=app.refresh_items_tree).pack(side='left',padx=8)
    ttk.Button(controls,text='New Manual Barcode...',command=app._create_manual_item).pack(side='right')
    frame=ttk.LabelFrame(tab,text='Inventory Items',padding=8);frame.grid(row=1,column=0,sticky='nsew',padx=(0,10))
    frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
    app.items_tree=app._create_tree(frame,['barcode_id','wings_item_no','item_name','variant','status','total_quantity','available_quantity'])
    app.items_tree.grid(row=0,column=0,sticky='nsew');app.items_tree.bind('<<TreeviewSelect>>',app._on_item_selected)
    app.items_tree.bind('<Double-1>',lambda e:app._edit_selected_item())
    panel=ttk.LabelFrame(tab,text='Selected Item',padding=12);panel.grid(row=1,column=1,sticky='nsew')
    app.item_detail_var=tk.StringVar(value='Select an item to manage it.')
    ttk.Label(panel,textvariable=app.item_detail_var,wraplength=340,justify='left').pack(fill='x',pady=(0,15))
    ttk.Label(panel,textvariable=app.item_form_status_var,wraplength=340).pack(fill='x')
    stock=ttk.LabelFrame(panel,text='Add Stock',padding=10);stock.pack(fill='x',pady=12)
    ttk.Label(stock,text='Quantity to add').pack(anchor='w')
    ttk.Spinbox(stock,from_=1,to=100000,textvariable=app.item_quantity_var,width=10).pack(anchor='w')
    ttk.Label(stock,text='Optional action note').pack(anchor='w',pady=(8,0))
    app.item_notes_text=tk.Text(stock,height=2,width=36,wrap='word');app.item_notes_text.pack(fill='x')
    ttk.Button(stock,text='Add Quantity',command=app._restock_item).pack(fill='x',pady=(8,0))
    for label,command in [('Edit Details...',app._edit_selected_item),('Print One Label',lambda:print_label(app)),('Set Available',lambda:app._set_item_status('Available')),('Mark Lost',lambda:app._set_item_status('Lost')),('Retire Barcode',lambda:app._set_item_status('Retired')),('Clear Selection',app._clear_item_form),('Delete Barcode Permanently',app._delete_item)]:
        ttk.Button(panel,text=label,command=command).pack(fill='x',pady=3)


def print_label(app):
    barcode=app.item_barcode_var.get()
    if not barcode:app._show_error('Select a barcode first.');return
    app._run_action(lambda:app.service.export_label_book(barcode_ids=[barcode],barcode_quantities={barcode:1},filename_stem=barcode+'_label'),success_message='One label exported.')


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
