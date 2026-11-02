"""Independent cadet return workspaces; drafts never change inventory."""
import json
import tkinter as tk
from tkinter import ttk,messagebox

VARIABLES=('return_cadet_search_var','return_scan_var','return_qty_var','return_summary_var')
WIDGETS=('return_cadet_search_entry','return_cadet_tree','return_scan_entry','return_inventory_tree','return_notes_text','returns_split')
STATE=('selected_return_cadet_id','return_cadet_details','return_cadet_cache')
SUMMARY='Search for and select the cadet who is returning items.'

class ReturnDraftMixin:
    @property
    def _return_drafts_path(self):return self.settings.database_path.parent/'return_drafts.json'

    def _build_returns_tab(self):
        self.returns_tab.columnconfigure(0,weight=1);self.returns_tab.rowconfigure(0,weight=1)
        self.returns_notebook=ttk.Notebook(self.returns_tab)
        self.returns_notebook.grid(row=0,column=0,columnspan=2,sticky='nsew')
        self.standard_returns_tab=ttk.Frame(self.returns_notebook,padding=8)
        self.standard_returns_tab.columnconfigure(0,weight=1);self.standard_returns_tab.rowconfigure(1,weight=1)
        self.returns_notebook.add(self.standard_returns_tab,text='Return Items')
        controls=ttk.Frame(self.standard_returns_tab);controls.grid(row=0,column=0,sticky='ew',pady=(0,8))
        ttk.Button(controls,text='+ New Cadet Return',command=lambda:self._new_return_draft(activate=False)).pack(side='left')
        ttk.Button(controls,text='Close Return Tab',command=self._close_return_draft).pack(side='left',padx=8)
        self.return_draft_notebook=ttk.Notebook(self.standard_returns_tab)
        self.return_draft_notebook.grid(row=1,column=0,sticky='nsew')
        self.return_drafts={};self._active_return_key=None;self._return_save_pending=None;self._return_restoring=True
        try:
            payload=json.loads(self._return_drafts_path.read_text(encoding='utf-8'))
            saved=payload.get('drafts',[]) if payload.get('version')==1 else []
            if not isinstance(saved,list):saved=[]
        except (OSError,ValueError,TypeError,AttributeError):saved=[]
        for data in saved:
            if isinstance(data,dict):self._new_return_draft(saved=data)
        if not self.return_drafts:self._new_return_draft()
        self.return_draft_notebook.bind('<<NotebookTabChanged>>',self._on_return_draft_changed)
        self._return_restoring=False

    def _capture_return_draft(self):
        context=self.return_drafts.get(self._active_return_key)
        if context:
            for name in STATE:context[name]=getattr(self,name)

    def _activate_return_draft(self,key):
        self._capture_return_draft();context=self.return_drafts.get(str(key))
        if not context:return
        self._active_return_key=str(key)
        for name in VARIABLES+WIDGETS+STATE:setattr(self,name,context[name])

    def _new_return_draft(self,*,saved=None,activate=True):
        self._capture_return_draft();previous=self._active_return_key
        used={c['number'] for c in self.return_drafts.values()};number=1
        while number in used:number+=1
        frame=ttk.Frame(self.return_draft_notebook,padding=4)
        frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        for name in VARIABLES:setattr(self,name,tk.StringVar(self,value='1' if name=='return_qty_var' else SUMMARY if name=='return_summary_var' else ''))
        self.selected_return_cadet_id=None;self.return_cadet_details=None;self.return_cadet_cache={}
        self._build_return_workspace(frame)
        from .appearance import preferences,ink
        if self.current_admin:self.returns_split.set_arrangement(preferences(self)['layout'])
        background=self.style.lookup('TFrame','background') or '#eef4fb'
        self.returns_split.configure(background='#454545' if ink(background)=='#ffffff' else '#d0d0d0')
        field=self.style.lookup('TEntry','fieldbackground') or '#ffffff'
        self.return_notes_text.configure(background=field,foreground=ink(field),insertbackground=ink(field))
        context={name:getattr(self,name) for name in VARIABLES+WIDGETS+STATE};context.update(frame=frame,number=number)
        key=str(frame);self.return_drafts[key]=context;self._active_return_key=key
        self.return_draft_notebook.add(frame,text=f'Return {number}')
        if activate or not previous:self.return_draft_notebook.select(frame)
        if saved:
            for name in VARIABLES[:3]:
                if isinstance(saved.get(name),str):context[name].set(saved[name])
            cadet_id=saved.get('cadet_id')
            if isinstance(cadet_id,int) and cadet_id>0:
                from .services import InventoryError
                try:self._load_return_cadet_details(cadet_id,focus=False)
                except InventoryError:pass
            self._set_text(self.return_notes_text,str(saved.get('notes','')))
            self._restore_return_selection(self.return_inventory_tree,saved.get('selected',[]))
            for name in ('return_scan_var','return_qty_var'):
                if isinstance(saved.get(name),str):context[name].set(saved[name])
        if not self._return_restoring:self._refresh_return_cadets()
        self._capture_return_draft();self._rename_return_draft(key)
        for variable in (context[n] for n in VARIABLES[:3]):variable.trace_add('write',lambda *args:self._schedule_return_draft_save())
        context['return_inventory_tree'].bind('<<TreeviewSelect>>',lambda event:self._schedule_return_draft_save(),add='+')
        context['return_notes_text'].bind('<<Modified>>',lambda event,k=key:self._return_notes_edited(k))
        if hasattr(self,'_attach_direct_shortcuts'):self._attach_direct_shortcuts(frame)
        if not activate and previous:
            self._activate_return_draft(previous)
            self._set_status(f'Return {number} created in the background. Select its tab when ready.')
        self._schedule_return_draft_save()
        return frame

    def _rename_return_draft(self,key):
        context=self.return_drafts.get(key)
        if not context:return
        details=context.get('return_cadet_details')
        name=details['cadet']['full_name'] if details else f'Return {context["number"]}'
        self.return_draft_notebook.tab(context['frame'],text=name)

    def _return_notes_edited(self,key):
        context=self.return_drafts.get(key)
        if not context:return
        widget=context['return_notes_text']
        if widget.edit_modified():widget.edit_modified(False);self._schedule_return_draft_save()

    def _on_return_draft_changed(self,event=None):
        self._activate_return_draft(self.return_draft_notebook.select());self._update_return_summary()
        if self.notebook.select()==str(self.returns_tab) and self.returns_notebook.select()==str(self.standard_returns_tab) and self.grab_current() is None:
            (self.return_scan_entry if self.selected_return_cadet_id else self.return_cadet_search_entry).focus_set()

    def _restore_return_selection(self,tree,ids):
        wanted={str(i) for i in ids} if isinstance(ids,list) else set()
        matches=[item for item in tree.get_children() if str(tree.set(item,'transaction_id')) in wanted]
        if matches:tree.selection_set(*matches)

    def refresh_return_cadets(self):
        previous=self._active_return_key
        for key in list(self.return_drafts):
            self._activate_return_draft(key);self._refresh_return_cadets();self._capture_return_draft();self._rename_return_draft(key)
        if previous in self.return_drafts:self._activate_return_draft(previous)
        self._schedule_return_draft_save()

    def _schedule_return_draft_save(self):
        if self._return_restoring:return
        if self._return_save_pending:self.after_cancel(self._return_save_pending)
        self._return_save_pending=self.after(250,self._save_return_drafts)

    def _save_return_drafts(self):
        if self._return_save_pending:self.after_cancel(self._return_save_pending)
        self._return_save_pending=None;self._capture_return_draft();drafts=[]
        for context in self.return_drafts.values():
            tree=context['return_inventory_tree']
            data={n:context[n].get() for n in VARIABLES[:3]}
            data.update(cadet_id=context['selected_return_cadet_id'],notes=self._get_text(context['return_notes_text']),selected=[int(tree.set(i,'transaction_id')) for i in tree.selection()])
            drafts.append(data)
        from .usb_portable import atomic_json
        try:
            atomic_json(self._return_drafts_path,dict(version=1,drafts=drafts))
            return True
        except OSError as error:
            self._set_status(f'Return drafts could not be saved: {error}')
            return False

    def _close_return_draft(self):
        key=self.return_draft_notebook.select();context=self.return_drafts.get(key)
        if not context:return
        self._capture_return_draft()
        if (context['selected_return_cadet_id'] or self._get_text(context['return_notes_text'])) and not messagebox.askyesno('Close Return Tab','Discard this cadet return draft? No inventory will be changed.',parent=self):return
        self.return_drafts.pop(key);self.return_draft_notebook.forget(context['frame']);context['frame'].destroy();self._active_return_key=None
        if not self.return_drafts:self._new_return_draft()
        self._activate_return_draft(self.return_draft_notebook.select());self._save_return_drafts()

    def _open_return_for_cadet(self,cadet_id,transaction_ids=None):
        self._capture_return_draft()
        key=next((k for k,c in self.return_drafts.items() if c['selected_return_cadet_id']==cadet_id),None)
        if key is None:
            if self.selected_return_cadet_id or self._get_text(self.return_notes_text):self._new_return_draft()
            key=self._active_return_key
        self.notebook.select(self.returns_tab);self.returns_notebook.select(self.standard_returns_tab)
        self.return_draft_notebook.select(key);self._activate_return_draft(key)
        self._load_return_cadet_details(cadet_id)
        if transaction_ids:self._restore_return_selection(self.return_inventory_tree,transaction_ids)
        self._update_return_summary();self._schedule_return_draft_save()
