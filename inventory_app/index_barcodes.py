"""Create an inventory barcode directly from a size-specific catalog entry."""
import tkinter as tk
from tkinter import ttk
from .services import InventoryError,ONE_SIZE_VARIANT

class IndexBarcodeMixin:
    def _generate_selected_index_barcode(self):
        selected=self._selected_tree_row(self.index_tree)
        if not selected or not selected.get('item_no'):
            self._show_error('Select a size-specific catalog entry. Use Add Custom Item to describe a new local item first.')
            return
        self._show_catalog_barcode_dialog(selected['item_no'])

    def _show_catalog_barcode_dialog(self,item_no):
        try:record=self.service.get_wings_catalog_item(item_no)
        except InventoryError as exc:
            self._show_error(str(exc));return
        window=tk.Toplevel(self);window.title('Generate Index Barcode');window.transient(self);window.grab_set()
        form=ttk.Frame(window,padding=18);form.pack(fill='both',expand=True)
        ttk.Label(form,text=f"{record['item_name']} ({record['size'] or ONE_SIZE_VARIANT})",wraplength=600,
            style='Title.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
        ttk.Label(form,text=f"Item number: {record['item_no']}").grid(row=1,column=0,columnspan=2,sticky='w')
        quantity=tk.StringVar(window,value='0')
        ttk.Label(form,text='Quantity to add').grid(row=2,column=0,sticky='w',pady=10)
        ttk.Spinbox(form,from_=0,to=10000,textvariable=quantity,width=10).grid(row=2,column=1,sticky='w')
        ttk.Label(form,text='Use 0 to create a label without adding stock. Existing matching barcodes are reused.',
            wraplength=600).grid(row=3,column=0,columnspan=2,sticky='w',pady=(0,12))
        result=tk.StringVar(window)
        ttk.Label(form,textvariable=result,wraplength=600).grid(row=4,column=0,columnspan=2,sticky='w')
        actions=ttk.Frame(form);actions.grid(row=5,column=0,columnspan=2,sticky='e',pady=(12,0))
        def created(item):
            self.refresh_all_views()
            result.set(f"Barcode {item['barcode_id']} ready. Total {item['total_quantity']}, available {item['available_quantity']}.")
            generate.configure(state='disabled')
            ttk.Button(actions,text='View / Print Label',command=lambda:self._open_index_barcode_label(window,item)).pack(side='left',padx=6)
        def generate_barcode():
            self._run_action(lambda:self.service.save_generated_barcode(
                category=record['category'],variant=record['size'] or ONE_SIZE_VARIANT,
                item_type=record['subcategory'] or record['item_name'],item_name=record['item_name'],
                wings_item_no=record['item_no'],units_per_barcode=quantity.get(),allow_zero=True),
                success_message=None,on_success=created)
        ttk.Button(actions,text='Close',command=window.destroy).pack(side='left',padx=6)
        generate=ttk.Button(actions,text='Generate Barcode',command=generate_barcode);generate.pack(side='left')
        return window

    def _open_index_barcode_label(self,window,item):
        window.destroy()
        self.generator_wings_item_no_var.set(item['wings_item_no'])
        self.generator_category_var.set(item['category']);self.generator_item_name_var.set(item['item_name'])
        self.generator_item_type_var.set(item['item_type']);self.generator_variant_var.set(item['variant'])
        self.generator_selected_item_var.set(f"{item['item_name']} ({item['variant']})")
        self.generator_preview_record=dict(item)
        self.generator_result_var.set(f"Barcode {item['barcode_id']} ready for printing.")
        self._populate_tree(self.generator_tree,
            ['barcode_id','item_name','category','variant','item_type','total_quantity'],[item])
        self.notebook.select(self.generator_tab)
        self._select_barcode_in_label_library(item['barcode_id'])
