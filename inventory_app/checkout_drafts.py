"""Independent checkout forms and queues, saved alongside the local database."""
import json
import tkinter as tk
from tkinter import ttk, messagebox

VARIABLES=('checkout_scan_var','checkout_last_name_var','checkout_middle_initial_var',
    'checkout_first_name_var','checkout_email_var','checkout_qty_var','checkout_summary_var')
WIDGETS=('checkout_scan_entry','checkout_first_name_entry','checkout_queue_tree','checkout_notes_text')
SUMMARY='Scan or paste a barcode and press Enter to add it to the checkout list.'

class CheckoutDraftMixin:
    def _build_checkout_tab(self):
        self.checkout_tab.columnconfigure(0,weight=1)
        self.checkout_tab.rowconfigure(1,weight=1)
        controls=ttk.Frame(self.checkout_tab);controls.grid(row=0,column=0,sticky='ew',pady=(0,8))
        ttk.Button(controls,text='+ New Cadet Checkout',command=lambda:self._new_checkout_draft(activate=False)).pack(side='left')
        ttk.Button(controls,text='Close Checkout Tab',command=self._close_checkout_draft).pack(side='left',padx=8)
        self.checkout_notebook=ttk.Notebook(self.checkout_tab)
        self.checkout_notebook.grid(row=1,column=0,sticky='nsew')
        self.checkout_drafts={};self._checkout_draft_number=0;self._draft_save_pending=None
        self._checkout_restoring=True
        try:
            payload=json.loads(self._checkout_drafts_path.read_text(encoding='utf-8'))
            saved=payload.get('drafts',[]) if payload.get('version')==1 else []
        except (OSError,ValueError,TypeError,AttributeError):
            saved=[]
        for draft in saved:
            if isinstance(draft,dict):self._new_checkout_draft(saved=draft)
        if not self.checkout_drafts:self._new_checkout_draft()
        self.checkout_notebook.bind('<<NotebookTabChanged>>',self._on_checkout_draft_changed)
        self._checkout_restoring=False
        self.protocol('WM_DELETE_WINDOW',self._close_with_checkout_drafts)

    @property
    def _checkout_drafts_path(self):
        return self.settings.database_path.parent/'checkout_drafts.json'

    def _close_with_checkout_drafts(self):
        self._save_checkout_drafts()
        if hasattr(self,"_save_return_drafts"):self._save_return_drafts()
        self.destroy()

    def _new_checkout_draft(self,*,saved=None,activate=True):
        previous=self.checkout_notebook.select()
        previous_barcode=self.current_checkout_barcode
        used={context['number'] for context in self.checkout_drafts.values()}
        self._checkout_draft_number=1
        while self._checkout_draft_number in used:self._checkout_draft_number+=1
        frame=ttk.Frame(self.checkout_notebook,padding=8)
        frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        self.checkout_queue={};self.current_checkout_barcode=None
        for name in VARIABLES:
            setattr(self,name,tk.StringVar(self,value='1' if name=='checkout_qty_var' else SUMMARY if name=='checkout_summary_var' else ''))
        self._build_checkout_workspace(frame)
        context={name:getattr(self,name) for name in VARIABLES+WIDGETS}
        context.update(frame=frame,checkout_queue=self.checkout_queue,number=self._checkout_draft_number)
        self.checkout_drafts[str(frame)]=context
        self.standard_checkout_tab=frame
        self.checkout_notebook.add(frame,text=f'Checkout {context["number"]}')
        if activate or not previous:self.checkout_notebook.select(frame)
        if saved:
            for name in VARIABLES:
                if name in saved and isinstance(saved[name],str):context[name].set(saved[name])
            queue=saved.get('queue',{})
            if isinstance(queue,dict):
                for barcode,line in queue.items():
                    if isinstance(line,dict) and isinstance(line.get('quantity'),int) and line['quantity']>0:
                        self.checkout_queue[barcode]=line
            self._set_text(self.checkout_notes_text,str(saved.get('notes','')))
        self.checkout_queue_tree.bind('<Delete>',lambda e:(self._remove_selected_checkout_queue(),'break')[1])
        for name in VARIABLES:
            context[name].trace_add('write',lambda *args,key=str(frame):self._checkout_draft_edited(key))
        self.checkout_notes_text.bind('<<Modified>>',lambda e,key=str(frame):self._checkout_notes_edited(key))
        self._update_checkout_queue_tree()
        self._checkout_draft_edited(str(frame))
        if hasattr(self,'_attach_direct_shortcuts'):self._attach_direct_shortcuts(frame)
        if not activate and previous:
            self._activate_checkout_draft(previous);self.current_checkout_barcode=previous_barcode
            self._set_status(f'Checkout {context["number"]} created in the background. Select its tab when ready.')
        return frame

    def _activate_checkout_draft(self,key):
        context=self.checkout_drafts.get(str(key))
        if not context:return
        for name in VARIABLES+WIDGETS+('checkout_queue',):setattr(self,name,context[name])
        self.standard_checkout_tab=context['frame']
        self.current_checkout_barcode=None

    def _on_checkout_draft_changed(self,event=None):
        self._activate_checkout_draft(self.checkout_notebook.select())
        if self.notebook.select()==str(self.checkout_tab) and self.grab_current() is None:
            self._focus_checkout_scan()

    def _checkout_draft_edited(self,key):
        context=self.checkout_drafts.get(key)
        if not context:return
        name=' '.join(filter(None,(context['checkout_first_name_var'].get().strip(),context['checkout_last_name_var'].get().strip())))
        self.checkout_notebook.tab(context['frame'],text=name or f'Checkout {context["number"]}')
        self._schedule_checkout_draft_save()

    def _checkout_notes_edited(self,key):
        context=self.checkout_drafts.get(key)
        if context and context['checkout_notes_text'].edit_modified():
            context['checkout_notes_text'].edit_modified(False)
            self._schedule_checkout_draft_save()

    def _schedule_checkout_draft_save(self):
        if getattr(self,'_checkout_restoring',True):return
        if self._draft_save_pending:self.after_cancel(self._draft_save_pending)
        self._draft_save_pending=self.after(250,self._save_checkout_drafts)

    def _save_checkout_drafts(self):
        if self._draft_save_pending:
            self.after_cancel(self._draft_save_pending)
        self._draft_save_pending=None
        drafts=[]
        for context in self.checkout_drafts.values():
            draft={name:context[name].get() for name in VARIABLES}
            draft.update(queue=context['checkout_queue'],notes=self._get_text(context['checkout_notes_text']))
            drafts.append(draft)
        path=self._checkout_drafts_path;temporary=path.with_suffix('.json.tmp')
        try:
            temporary.write_text(json.dumps({'version':1,'drafts':drafts},indent=2),encoding='utf-8')
            temporary.replace(path)
            return True
        except OSError as exc:
            self._set_status(f'Checkout drafts could not be saved: {exc}')
            return False

    def _close_checkout_draft(self):
        key=self.checkout_notebook.select();context=self.checkout_drafts.get(key)
        if not context:return
        has_details=bool(context['checkout_queue'] or self._get_text(context['checkout_notes_text']) or
            any(context[name].get().strip() for name in VARIABLES[1:5]))
        if has_details and not messagebox.askyesno('Close Checkout Tab',
            'Discard this cadet checkout draft and its queued items?',parent=self):return
        self.checkout_drafts.pop(key);self.checkout_notebook.forget(context['frame']);context['frame'].destroy()
        if not self.checkout_drafts:self._new_checkout_draft()
        self._activate_checkout_draft(self.checkout_notebook.select())
        self._save_checkout_drafts()

    def _other_draft_units(self,barcode):
        return sum(int(context['checkout_queue'].get(barcode,{}).get('quantity',0))
            for context in self.checkout_drafts.values() if context['checkout_queue'] is not self.checkout_queue)

    def _open_checkout_for_cadet(self,row):
        email=row['email'].casefold()
        for key,context in self.checkout_drafts.items():
            if context['checkout_email_var'].get().strip().casefold()==email:
                self.checkout_notebook.select(key);self._activate_checkout_draft(key);return
        if self.checkout_queue or any(v.get().strip() for v in
                (self.checkout_last_name_var,self.checkout_first_name_var,self.checkout_email_var)):
            self._new_checkout_draft()

    def _refresh_checkout_draft_stock(self):
        columns=['barcode_id','item_name','category','variant','item_type','available_quantity','quantity']
        for context in self.checkout_drafts.values():
            for barcode,line in context['checkout_queue'].items():
                item=self.service.get_item(barcode)
                line['available_quantity']=item['available_quantity'] if item else 0
            self._populate_tree(context['checkout_queue_tree'],columns,list(context['checkout_queue'].values()))
        self._schedule_checkout_draft_save()
