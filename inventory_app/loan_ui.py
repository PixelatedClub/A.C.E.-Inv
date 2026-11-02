from datetime import date, timedelta
from .completion_sound import show_error
import tkinter as tk
from tkinter import ttk, messagebox
from .barcode_utils import extract_scanned_barcode, open_file


class LoanUiMixin:
    def _build_loans_tab(self):
        self.loans_tab = ttk.Frame(self.returns_notebook, padding=12)
        self.returns_notebook.add(self.loans_tab, text='Temporary Loans')
        self.loans_tab.columnconfigure(0, weight=1)
        self.loans_tab.rowconfigure(3, weight=1)
        self.loan_search = tk.StringVar()
        self.loan_show_closed = tk.BooleanVar(value=False)
        self.loan_summary = tk.StringVar()
        ttk.Label(self.loans_tab, text='Temporary loans', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(self.loans_tab, text='Choose a return deadline when issuing items. Use Returns to record physical returns.').grid(row=1,column=0,sticky='w')
        controls = ttk.Frame(self.loans_tab)
        controls.grid(row=2,column=0,sticky='ew',pady=10)
        for column in range(3):controls.columnconfigure(column,weight=1)
        entry=ttk.Entry(controls,textvariable=self.loan_search,width=30)
        entry.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,6));entry.bind('<KeyRelease>',lambda e:self.refresh_loans())
        ttk.Checkbutton(controls,text='Include closed',variable=self.loan_show_closed,command=self.refresh_loans).grid(row=0,column=2,sticky='w',padx=8)
        actions=[('Change due date...',self._change_loan_date),('Convert to standard checkout',self._convert_loan_to_checkout),('Return Selected to Inventory',self._return_selected_loans),('Open cadet returns...',self._return_loan_cadet),('Previous week report',self._monday_report),('Refresh',self.refresh_loans)]
        for index,(label,command) in enumerate(actions):
            ttk.Button(controls,text=label,command=command).grid(row=1+index//3,column=index%3,sticky='ew',padx=3,pady=3)
        frame=ttk.Frame(self.loans_tab); frame.grid(row=3,column=0,sticky='nsew')
        frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        self.loan_columns=['transaction_id','cadet_name','item_name','variant','barcode_id','loan_due_date','loan_status','loan_purpose']
        self.loan_tree=self._create_tree(frame,self.loan_columns,selectmode='extended')
        self.loan_tree.grid(row=0,column=0,sticky='nsew')
        self.loan_tree.tag_configure('overdue',background='#ffe2e2')
        ttk.Label(self.loans_tab,textvariable=self.loan_summary).grid(row=4,column=0,sticky='w',pady=8)
        self.returns_notebook.bind('<<NotebookTabChanged>>', self._on_checkout_workflow_changed, add='+')

    def _on_checkout_workflow_changed(self, _event=None):
        if self.returns_notebook.select() == str(self.loans_tab):
            self.refresh_loans()

    def refresh_loans(self):
        if not hasattr(self,'loan_tree'):
            return
        rows=self.service.list_loans(self.loan_search.get(),self.loan_show_closed.get())
        self.loan_tree.delete(*self.loan_tree.get_children())
        for col in self.loan_columns:
            self.loan_tree.heading(col,text=col.replace('_',' ').title())
            self.loan_tree.column(col,width=190 if col in ('cadet_name','item_name','loan_purpose') else 110)
        for row in rows:
            self.loan_tree.insert('', 'end',iid=str(row['transaction_id']),values=[row.get(col,'') for col in self.loan_columns],tags=('overdue',) if row['overdue'] else ())
        active=[r for r in rows if not r['return_time']]
        self.loan_summary.set(f"{len(active)} outstanding units · {len(set(r['cadet_id'] for r in active))} cadets · {sum(bool(r['overdue']) for r in active)} overdue")

    def _loan_date_controls(self, parent, row=0):
        due=tk.StringVar(parent,value=str(date.today()+timedelta(weeks=3)))
        ttk.Label(parent,text='Return by (YYYY-MM-DD)').grid(row=row,column=0,sticky='w',pady=6)
        ttk.Entry(parent,textvariable=due,width=18).grid(row=row,column=1,sticky='w')
        presets=ttk.Frame(parent);presets.grid(row=row+1,column=0,columnspan=2,sticky='w')
        for weeks in (2,3,4):
            ttk.Button(presets,text=f'{weeks} weeks',command=lambda w=weeks:due.set(str(date.today()+timedelta(weeks=w)))).pack(side='left',padx=3)
        return due

    def _submit_checkout_as_loan(self):
        if not self.checkout_queue:
            self._show_error('Scan or paste at least one barcode into the checkout list first.')
            return

        window=tk.Toplevel(self);window.title('Loan queued items');window.transient(self)
        form=ttk.Frame(window,padding=16);form.pack(fill='both',expand=True);form.columnconfigure(1,weight=1)
        cadet_name=self._compose_checkout_name()
        cadet_email=self.checkout_email_var.get().strip()
        draft_key=str(self.standard_checkout_tab)
        target=self.checkout_drafts[draft_key]
        identity=tuple(target[k].get() for k in ('checkout_last_name_var','checkout_middle_initial_var','checkout_first_name_var','checkout_email_var'))
        snapshot=[{'barcode_id':r['barcode_id'],'quantity':r['quantity']} for r in target['checkout_queue'].values()]
        notes=self._get_text(target['checkout_notes_text'])
        queued_units=sum(int(row['quantity']) for row in self.checkout_queue.values())
        ttk.Label(form,text='Cadet').grid(row=0,column=0,sticky='w',pady=(0,6))
        ttk.Label(form,text=f'{cadet_name} | {cadet_email}',style='Accent.TLabel').grid(row=0,column=1,sticky='w',pady=(0,6))
        ttk.Label(form,text='Queued items').grid(row=1,column=0,sticky='w',pady=(0,6))
        ttk.Label(form,text=f'{queued_units} unit(s) across {len(self.checkout_queue)} barcode line(s)').grid(row=1,column=1,sticky='w',pady=(0,6))
        due=self._loan_date_controls(form,2)
        purpose=tk.StringVar(window,value='Game day flags')
        ttk.Label(form,text='Loan purpose').grid(row=4,column=0,sticky='w',pady=8)
        ttk.Entry(form,textvariable=purpose,width=48).grid(row=4,column=1,sticky='ew',pady=8)

        def issue():
            if draft_key not in self.checkout_drafts or identity!=tuple(target[k].get() for k in ('checkout_last_name_var','checkout_middle_initial_var','checkout_first_name_var','checkout_email_var')) or snapshot!=[{'barcode_id':r['barcode_id'],'quantity':r['quantity']} for r in target['checkout_queue'].values()] or notes!=self._get_text(target['checkout_notes_text']):
                self._show_error('The original cadet draft changed or was closed. Reopen Loan Queued Items from that draft before approving.')
                return
            for line in snapshot:
                item=self.service.get_item(line['barcode_id'])
                reserved=sum(int(context['checkout_queue'].get(line['barcode_id'],{}).get('quantity',0)) for key,context in self.checkout_drafts.items() if key!=draft_key)
                if not item or line['quantity']>item['available_quantity']-reserved:
                    self._show_error('Stock is no longer available after other cadet queues. Review the original draft before approving.')
                    return
            deadline=due.get()
            purpose_text=purpose.get()
            line_items=snapshot
            def saved(processed_items):
                total=sum(int(row['quantity']) for row in processed_items)
                window.destroy();target['checkout_queue'].clear();target['checkout_scan_var'].set('');target['checkout_qty_var'].set('1');target['checkout_notes_text'].delete('1.0','end');self.refresh_all_views()
                self._show_info(f'Loaned {total} unit(s) with return deadline {deadline}.')
            self._run_action(
                lambda:self.service.checkout_items_bulk(
                    line_items=line_items,
                    cadet_name=cadet_name,
                    cadet_email=cadet_email,
                    approved_by=self.current_admin,
                    condition_notes=notes,
                    loan_due_date=deadline,
                    loan_purpose=purpose_text,
                ),
                success_message=None,
                on_success=saved,
            )

        actions=ttk.Frame(form);actions.grid(row=5,column=0,columnspan=2,sticky='e',pady=(10,0))
        ttk.Button(actions,text='Cancel',command=window.destroy).pack(side='left',padx=(0,6))
        ttk.Button(actions,text='Loan Queued Items',command=issue).pack(side='left')

    def _new_loan_dialog(self):
        window=tk.Toplevel(self);window.title('Issue a temporary loan');window.transient(self)
        form=ttk.Frame(window,padding=16);form.pack(fill='both',expand=True);form.columnconfigure(1,weight=1)
        cadets=self.service.list_cadets()
        cadet_map={f"{r['full_name']} | {r['email']}":r for r in cadets}
        cadet=tk.StringVar(window);combo=ttk.Combobox(form,textvariable=cadet,values=list(cadet_map),width=66)
        ttk.Label(form,text='Cadet (type to search)').grid(row=0,column=0,sticky='w');combo.grid(row=0,column=1,sticky='ew')
        combo.bind('<KeyRelease>',lambda e:combo.configure(values=[s for s in cadet_map if cadet.get().casefold() in s.casefold()]))
        due=self._loan_date_controls(form,1)
        purpose=tk.StringVar(window,value='Game day flags')
        ttk.Label(form,text='Purpose').grid(row=3,column=0,sticky='w',pady=8);ttk.Entry(form,textvariable=purpose).grid(row=3,column=1,sticky='ew')
        stock=self.service.list_items(status_filter='Available')
        stock_map={f"{r['barcode_id']} | {r['item_name']} | {r['variant']} ({r['available_quantity']} available)":r['barcode_id'] for r in stock}
        selected=tk.StringVar(window);quantity=tk.StringVar(window,value='1')
        ttk.Label(form,text='Scan barcode or search item').grid(row=4,column=0,sticky='w')
        item_combo=ttk.Combobox(form,textvariable=selected,values=list(stock_map),width=66);item_combo.grid(row=4,column=1,sticky='ew')
        item_combo.bind('<KeyRelease>',lambda e:item_combo.configure(values=[s for s in stock_map if selected.get().casefold() in s.casefold()]))
        ttk.Label(form,text='Quantity').grid(row=5,column=0,sticky='w');ttk.Spinbox(form,from_=1,to=1000,textvariable=quantity,width=8).grid(row=5,column=1,sticky='w')
        queue={};listbox=tk.Listbox(form,height=9,width=90);listbox.grid(row=7,column=0,columnspan=2,sticky='ew',pady=8)
        def redraw():
            listbox.delete(0,'end')
            for barcode,line in queue.items():
                listbox.insert('end',f"{barcode} - {line['name']} - {line['quantity']} units")
        def add():
            try:
                barcode=stock_map.get(selected.get()) or extract_scanned_barcode(selected.get())
                item=self.service.get_item(barcode)
                if not item: raise ValueError('Barcode not found.')
                qty=int(quantity.get())
                total=qty+queue.get(barcode,{}).get('quantity',0)
                if qty<1 or total>item['available_quantity'] or item['status'] in ('Lost','Retired'):
                    raise ValueError('Quantity must be positive and within available stock.')
                queue[barcode]={'barcode_id':barcode,'quantity':total,'name':item['item_name']+' '+item['variant']}
                redraw();selected.set('');quantity.set('1');item_combo.focus_set()
            except (ValueError,TypeError) as exc:
                show_error('Loan item',str(exc),parent=window)
        def remove():
            if listbox.curselection():
                del queue[list(queue)[listbox.curselection()[0]]];redraw()
        actions=ttk.Frame(form);actions.grid(row=6,column=0,columnspan=2,sticky='w')
        ttk.Button(actions,text='Add to loan',command=add).pack(side='left')
        ttk.Button(actions,text='Remove selected',command=remove).pack(side='left',padx=6)
        item_combo.bind('<Return>',lambda e:add())
        def issue():
            identity=cadet_map.get(cadet.get())
            if not identity:
                show_error('Select cadet','Select an existing cadet. Add new cadets in the Cadets tab first.',parent=window);return
            def saved(result):
                window.destroy();self.refresh_all_views()
            self._run_action(lambda:self.service.checkout_items_bulk(line_items=list(queue.values()),cadet_name=identity['full_name'],cadet_email=identity['email'],approved_by=self.current_admin,loan_due_date=due.get(),loan_purpose=purpose.get()),success_message='Loan issued with a return deadline.',on_success=saved)
        ttk.Button(form,text='Issue loan',command=issue).grid(row=8,column=1,sticky='e')

    def _change_loan_date(self):
        ids=[int(i) for i in self.loan_tree.selection()]
        if not ids:self._show_error('Select one or more loans first.');return
        window=tk.Toplevel(self);window.title('Change loan deadline');window.transient(self)
        form=ttk.Frame(window,padding=16);form.pack()
        due=self._loan_date_controls(form)
        purpose=tk.StringVar(window,value='Deadline updated')
        ttk.Label(form,text='Purpose / reason').grid(row=2,column=0);ttk.Entry(form,textvariable=purpose).grid(row=2,column=1)
        def save():
            self._run_action(lambda:self.service.set_loan_deadline(ids,due.get(),purpose.get(),self.current_admin),success_message='Loan deadlines updated.',on_success=lambda r:(window.destroy(),self.refresh_loans()))
        ttk.Button(form,text='Save deadline',command=save).grid(row=3,column=1,pady=10)

    def _return_loan_cadet(self):
        ids=self.loan_tree.selection()
        if not ids:self._show_error('Select a loan first.');return
        rows={str(r['transaction_id']):r for r in self.service.list_loans(include_closed=True)}
        if ids[0] not in rows:self._show_error('This loan no longer exists. Refresh the list.');return
        cadet_id=rows[ids[0]]['cadet_id']
        selected=[int(i) for i in ids if i in rows and rows[i]['cadet_id']==cadet_id and not rows[i]['return_time']]
        self._open_return_for_cadet(cadet_id,selected)

    def _return_selected_loans(self):
        ids=[int(i) for i in self.loan_tree.selection()]
        if not ids:self._show_error('Select one or more loan items to return.');return
        loans={int(r['transaction_id']):r for r in self.service.list_loans(include_closed=True)}
        if any(i not in loans or loans[i]['return_time'] for i in ids):
            self._show_error('One or more selected loans are already closed or changed. Refresh the list.');return
        cadets={loans[i]['cadet_id'] for i in ids}
        if len(cadets)!=1:
            self._show_error('Select loans for one cadet at a time. Use separate return tabs for multiple cadets.');return
        cadet_id=next(iter(cadets));name=loans[ids[0]]['cadet_name']
        if not messagebox.askyesno('Return Loan Items',f'Return {len(ids)} selected loan unit(s) for {name} to available inventory?',parent=self):return
        self._run_action(lambda:self.service.return_cadet_items(cadet_id=cadet_id,transaction_ids=ids,approved_by=self.current_admin),
            success_message=f'Returned {len(ids)} loan unit(s) for {name} to inventory. History and reports were updated.',
            on_success=lambda _result:self.refresh_all_views())

    def _convert_loan_to_checkout(self):
        ids = [int(value) for value in self.loan_tree.selection()]
        if not ids:
            self._show_error('Select one or more active loans first.')
            return
        if not messagebox.askyesno(
            'Convert to standard checkout',
            'Remove the loan deadline from the selected item(s)?\n\n'
            'The items will remain checked out to the same cadet and inventory quantities will not change.',
            parent=self,
        ):
            return
        self._run_action(
            lambda: self.service.convert_loans_to_standard_checkout(ids, self.current_admin),
            success_message='Selected loan items are now standard checkouts.',
            on_success=lambda _result: self.refresh_all_views(),
        )

    def _monday_report(self):
        self._run_action(self.service.export_monday_report,success_message='Previous-week A.C.E. report generated.',on_success=open_file)

    def _check_loan_reminders(self):
        try:
            if self.current_admin and self.winfo_viewable():
                self.refresh_loans()
        finally:
            self.after(3600000,self._check_loan_reminders)
