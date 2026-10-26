"""Desktop-controlled phone sessions and explicit CIC identity/item review."""
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from .barcode_utils import open_file
from .layout import ResizableSplit
from .cic_server import CicSession,local_addresses
from .cic import item_key


class CicUiMixin:
    def _build_cic_tab(self):
        self.cic_session=None;self.cic_cards={};self.cic_unread=0;self.cic_seen_notices=set();self.cic_search=tk.StringVar();self.cic_status=tk.StringVar(value='Phone session stopped. No incoming connection is accepted.')
        self.notebook.bind('<<NotebookTabChanged>>',self._ack_cic_notice,add='+')
        self.cic_tab.columnconfigure(0,weight=1);self.cic_tab.rowconfigure(2,weight=1)
        controls=ttk.Frame(self.cic_tab);controls.grid(row=0,column=0,sticky='ew')
        for label,command in [('Start Phone Session',self._start_cic_session),('Stop Session',self._stop_cic_session),('Copy Join Link',self._copy_cic_link),('Refresh',self.refresh_cic),('Review Selected Card',self._review_cic)]:
            ttk.Button(controls,text=label,command=command).pack(side='left',padx=3)
        ttk.Label(self.cic_tab,textvariable=self.cic_status,wraplength=1100).grid(row=1,column=0,sticky='w',pady=10)
        split=ResizableSplit(self.cic_tab,orient=tk.HORIZONTAL);split.grid(row=2,column=0,sticky='nsew')
        left=ttk.Frame(split,padding=6);right=ttk.Frame(split,padding=6);split.add(left,minsize=280,stretch='always');split.add(right,minsize=350,stretch='always')
        left.columnconfigure(0,weight=1);left.rowconfigure(1,weight=1);right.columnconfigure(0,weight=1);right.rowconfigure(0,weight=1)
        search=ttk.Entry(left,textvariable=self.cic_search);search.grid(row=0,column=0,sticky='ew');search.bind('<Return>',lambda e:self.refresh_cic())
        table=ttk.Frame(left);table.grid(row=1,column=0,sticky='nsew');table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        self.cic_tree=self._create_tree(table,columns=['cadet_name','cadet_email','status','submitted_at']);self.cic_tree.grid(row=0,column=0,sticky='nsew')
        self.cic_tree.bind('<<TreeviewSelect>>',lambda e:self._cic_details());self.cic_tree.bind('<Double-1>',lambda e:self._review_cic())
        self.cic_details=tk.Text(right,wrap='word',state='disabled',width=60);self.cic_details.grid(row=0,column=0,sticky='nsew')
        buttons=ttk.Frame(right);buttons.grid(row=1,column=0,sticky='ew',pady=8)
        ttk.Button(buttons,text='Card Copy',command=lambda:self._cic_export(False)).pack(side='left',padx=3)
        ttk.Button(buttons,text='Approved WINGS Export',command=lambda:self._cic_export(True)).pack(side='left',padx=3)
        ttk.Label(self.cic_tab,text='Submission does not issue stock. Approval adds only unrecorded possessions; missing or misspelled items remain Held. Local IDs block official WINGS export.',wraplength=1150).grid(row=3,column=0,sticky='w',pady=8)
        self.refresh_cic();self.after(2000,self._poll_cic)

    def _cic_admin(self):
        if not self.current_admin:
            from .services import InventoryError
            raise InventoryError('Sign in as an ACE administrator before starting or reviewing cards.')
        return self.current_admin

    def _start_cic_session(self):
        if self.cic_session:self._show_error('Stop the current session before starting another.');return
        try:self._cic_admin()
        except Exception as error:self._show_error(str(error));return
        dialog=tk.Toplevel(self);dialog.title('Start CIC Phone Session');dialog.transient(self)
        frame=ttk.Frame(dialog,padding=18);frame.pack(fill='both',expand=True)
        lan=tk.BooleanVar(value=False);addresses=local_addresses();address=tk.StringVar(value=addresses[0] if addresses else '')
        port=tk.StringVar(value='8766');hours=tk.StringVar(value='2');cert=tk.StringVar();key=tk.StringVar()
        ttk.Label(frame,text='Connect phones to the same trusted Wi-Fi / hotspot as this computer.\nCampus Wi-Fi may block device-to-device traffic. No firewall rules or router ports are changed.\nDefault: this computer only. LAN access must be enabled explicitly.',wraplength=640).pack(anchor='w',pady=8)
        ttk.Checkbutton(frame,text='Allow phones on my trusted local network',variable=lan).pack(anchor='w')
        for label,var in [('Computer LAN IPv4 address',address),('Port',port),('Session duration in hours (1-8)',hours)]:
            ttk.Label(frame,text=label).pack(anchor='w',pady=(8,0));ttk.Entry(frame,textvariable=var).pack(fill='x')
        ttk.Label(frame,text='Optional HTTPS: select a certificate trusted by your phones and its private key.\nWithout these, HTTP is unencrypted. Use only an isolated, trusted network for the beta.',wraplength=640).pack(anchor='w',pady=12)
        for label,var in [('TLS certificate',cert),('TLS private key',key)]:
            row=ttk.Frame(frame);row.pack(fill='x',pady=3);ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
            ttk.Button(row,text=label,command=lambda v=var:v.set(filedialog.askopenfilename(parent=dialog))).pack(side='left')
        def start():
            try:
                if self.cic_session:raise ValueError('A phone session is already active. Stop it before starting another.')
                if lan.get() and not cert.get() and not messagebox.askyesno('Unencrypted local beta','HTTP does not encrypt cadet information in transit. Start only on an isolated, trusted network with permission to collect these cards. Continue?',parent=dialog):return
                self.cic_session=CicSession(self.service,host=address.get().strip() if lan.get() else '127.0.0.1',advertise_host=address.get().strip() if lan.get() else '127.0.0.1',port=int(port.get()),hours=float(hours.get()),certfile=cert.get(),keyfile=key.get())
                self.cic_status.set(f'Active: {self.cic_session.join_url}  |  Join code: {self.cic_session.code}  |  Expires after {hours.get()} hours. Keep ACE open.')
                dialog.destroy()
            except Exception as error:self._show_error(str(error))
        ttk.Button(frame,text='Start Session',command=start).pack(pady=12)

    def _stop_cic_session(self):
        if self.cic_session:self.cic_session.stop();self.cic_session=None
        self.cic_status.set('Session stopped. Submitted cards remain in ACE for review.')

    def _copy_cic_link(self):
        if not self.cic_session:self._show_error('Start a phone session first.');return
        self.clipboard_clear();self.clipboard_append(f'Det005: Open {self.cic_session.join_url} and enter session code {self.cic_session.code}')
        self._set_status('CIC join link and code copied. Share only with the current bag-drag participants.')

    def _poll_cic(self):
        if self.cic_session:
            import time
            if time.monotonic()>self.cic_session.expires:self._stop_cic_session()
            else:
                events=[e for e in self.cic_session.notifications() if e['card_id'] not in self.cic_seen_notices]
                if events:
                    self.cic_seen_notices.update(e['card_id'] for e in events)
                    self.refresh_cic();self.bell();self._set_status(f'{len(events)} CIC submission(s) received. Review them in Cadet Inventory Cards.')
                    if self.notebook.select()!=str(self.cic_tab):
                        self.cic_unread+=len(events)
                        self.notebook.tab(self.cic_tab,text=f'Cadet Inventory Cards ({self.cic_unread} new)')
        self.after(2000,self._poll_cic)

    def _ack_cic_notice(self,event=None):
        if self.notebook.select()==str(self.cic_tab):
            self.cic_unread=0;self.notebook.tab(self.cic_tab,text='Cadet Inventory Cards')

    def refresh_cic(self):
        if not hasattr(self,'cic_tree'):return
        selection=self.cic_tree.selection();rows=self.service.list_cic(self.cic_search.get());self.cic_cards={r['card_id']:r for r in rows}
        self.cic_tree.delete(*self.cic_tree.get_children())
        for r in rows:self.cic_tree.insert('', 'end',iid=r['card_id'],values=[r[k] for k in ('cadet_name','cadet_email','status','submitted_at')])
        if selection and selection[0] in self.cic_cards:self.cic_tree.selection_set(selection[0])
        self._cic_details()

    def _selected_cic(self):
        selected=self.cic_tree.selection()
        return selected[0] if selected else None

    def _cic_details(self):
        card_id=self._selected_cic();content='Select a card to review declared items, matching profiles and hold reasons.'
        if card_id:
            card=self.service.get_cic(card_id)
            content=f"{card['cadet_name']}\n{card['cadet_email']}\nStatus: {card['status']}\nSubmitted: {card['submitted_at']}\nCard: {card_id}\n\n"+'\n\n'.join(f"{r['entered_name']} / {r['entered_size']} x {r['quantity']}\nID: {r['item_no'] or '(unresolved)'}"+(f"\nHOLD: {r['problem']}" if r['problem'] else '') for r in card['lines'])
            if card['notes']:content+='\n\nNotes: '+card['notes']
            if card['assessment_json']!='{}':
                import json
                from .cic_questions import QUESTIONS
                counts=json.loads(card['assessment_json']);families=list(dict.fromkeys(q[1] for q in QUESTIONS))
                content+='\n\nQuantity questionnaire (0 means none):\n'+'\n'.join(f"{family}: "+(', '.join(f'{q[2]} {counts.get(q[0],0)}' for q in QUESTIONS if q[1]==family and counts.get(q[0],0)) or 'None') for family in families)
        self.cic_details.configure(state='normal');self.cic_details.delete('1.0','end');self.cic_details.insert('1.0',content);self.cic_details.configure(state='disabled')

    def _cic_export(self,wings):
        card_id=self._selected_cic()
        if not card_id:self._show_error('Select a card first.');return
        self._run_action(lambda:self.service.export_cic_wings(card_id) if wings else self.service.export_cic_copy(card_id),success_message=None,on_success=open_file)

    def _review_cic(self):
        card_id=self._selected_cic()
        if not card_id:self._show_error('Select a card first.');return
        try:actor=self._cic_admin();card=self.service.revalidate_cic(card_id)
        except Exception as error:self._show_error(str(error));return
        if card['status'] in ('Approved','Rejected'):self._show_info('This card has already been '+card['status'].lower()+'. Use Card Copy or Approved WINGS Export.');return
        dialog=tk.Toplevel(self);dialog.title('Review Cadet Inventory Card');dialog.transient(self);dialog.geometry('1000x760');dialog.minsize(800,600)
        frame=ttk.Frame(dialog,padding=14);frame.pack(fill='both',expand=True);frame.columnconfigure(0,weight=1);frame.rowconfigure(3,weight=1)
        ttk.Label(frame,text=f"{card['cadet_name']} | {card['cadet_email']}\nChoose an existing profile or explicitly create a new one. Existing profiles are never renamed here.",wraplength=950).grid(row=0,column=0,sticky='w')
        candidates=self.service.cic_candidates(card_id)
        # Include all profiles for manual selection without guessing an identity.
        ids={r['cadet_id'] for r in candidates}
        choices=[(None,'Create NEW cadet profile')]+[(r['cadet_id'],f"{r['match_reason']}: #{r['cadet_id']} {r['full_name']} <{r['email']}>") for r in candidates]+[(r['cadet_id'],f"Other profile: #{r['cadet_id']} {r['full_name']} <{r['email']}>") for r in self.service.list_cadets() if r['cadet_id'] not in ids]
        chosen=tk.StringVar(value=choices[1][1] if candidates else choices[0][1]);selector=ttk.Combobox(frame,textvariable=chosen,values=[x[1] for x in choices],state='readonly',width=100);selector.grid(row=1,column=0,sticky='ew',pady=8)
        ttk.Label(frame,text='To correct a held line: create/correct its item in ACE Index or Items, then select the line below and Map Selected Line. Re-preview after changes.',wraplength=950).grid(row=2,column=0,sticky='w')
        table=ttk.Frame(frame);table.grid(row=3,column=0,sticky='nsew',pady=8);table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        tree=self._create_tree(table,columns=['item_no','entered_name','entered_size','quantity','problem']);tree.grid(row=0,column=0,sticky='nsew')
        for line in card['lines']:tree.insert('','end',iid=str(line['line_id']),values=[line[k] for k in ('item_no','entered_name','entered_size','quantity','problem')])
        preview=tk.Text(frame,height=9,wrap='word',state='disabled');preview.grid(row=4,column=0,sticky='ew')
        context={'review':None}
        def identify():
            cid=next(x[0] for x in choices if x[1]==chosen.get());return {'cadet_id':cid,'create_new':cid is None}
        def show_preview():
            try:
                review=self.service.preview_cic(card_id,**identify());context['review']=review
                content='\n'.join(f"{x['item_name']} / {x['size']}: declared {x['quantity']}, already checked out {x['existing']}, acquired/purchased {x['owned']}, NEW reconciled checkouts {x['add']}."+(f" WARNING: {x['excess']} more already recorded than declared; investigate separately. Nothing will be removed." if x['excess'] else '')+(' LOCAL: WINGS export blocked.' if not x['official'] else '') for x in review['plan'])
                preview.configure(state='normal');preview.delete('1.0','end');preview.insert('1.0',content);preview.configure(state='disabled')
            except Exception as error:context['review']=None;self._show_error(str(error))
        selector.bind('<<ComboboxSelected>>',lambda e:context.update(review=None))
        def approve():
            if context['review'] is None:self._show_error('Preview reconciliation before approving.');return
            review=context['review'];amount=sum(x['add'] for x in review['plan'])
            if not messagebox.askyesno('Confirm CIC approval',f"{'Create new profile' if review['cadet'] is None else 'Use saved profile '+review['cadet']['full_name']}?\n\nAdd {amount} newly confirmed held item(s) and matching checkout records. Shelf availability will not increase or decrease. Existing recorded possessions will not be duplicated. No official WINGS issue or email will be sent.",parent=dialog):return
            try:self.service.approve_cic(card_id,**identify(),approved_by=self._cic_admin(),review_token=review['review_token']);dialog.destroy();self.refresh_all_views()
            except Exception as error:self._show_error(str(error));context['review']=None
        def reject():
            from tkinter.simpledialog import askstring
            reason=askstring('Reject Card','Reason for rejection (no stock changes):',parent=dialog)
            if not reason:return
            try:self.service.reject_cic(card_id,approved_by=self._cic_admin(),reason=reason);dialog.destroy();self.refresh_cic()
            except Exception as error:self._show_error(str(error))
        buttons=ttk.Frame(frame);buttons.grid(row=5,column=0,sticky='ew',pady=10)
        ttk.Button(buttons,text='Map Selected Line',command=lambda:self._map_cic_dialog(dialog,card_id,tree)).pack(side='left',padx=4)
        ttk.Button(buttons,text='Preview Reconciliation',command=show_preview).pack(side='left',padx=4)
        ttk.Button(buttons,text='Approve Card',command=approve).pack(side='left',padx=4)
        ttk.Button(buttons,text='Reject Card',command=reject).pack(side='left',padx=4)
        ttk.Button(buttons,text='Close',command=dialog.destroy).pack(side='left',padx=4)

    def _map_cic_dialog(self,review,card_id,tree):
        selected=tree.selection()
        if not selected:self._show_error('Select the item line that needs correction.');return
        lid=int(selected[0]);window=tk.Toplevel(review);window.title('Map to Correct ACE Index Item');window.geometry('850x500')
        query=tk.StringVar();entry=ttk.Entry(window,textvariable=query);entry.pack(fill='x',padx=12,pady=8)
        table=ttk.Frame(window);table.pack(fill='both',expand=True,padx=12);table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        results=self._create_tree(table,columns=['item_no','item_name','size','category','sex']);results.grid(row=0,column=0,sticky='nsew')
        lookup={}
        def search():
            results.delete(*results.get_children());lookup.clear()
            for i,row in enumerate(self.service.list_wings_catalog(search=query.get())[:250]):
                lookup[str(i)]=row;results.insert('','end',iid=str(i),values=[row[k] for k in ('item_no','item_name','size','category','sex')])
        def use():
            selected=results.selection()
            if not selected:return
            row=lookup[selected[0]]
            if not messagebox.askyesno('Confirm mapping',f"Map this line to {row['item_name']} / {row['size']} / {row['item_no']}?",parent=window):return
            try:
                self.service.map_cic_line(card_id,lid,row['item_no'],approved_by=self._cic_admin());window.destroy();review.destroy();self.refresh_cic();self._review_cic()
            except Exception as error:self._show_error(str(error))
        entry.bind('<Return>',lambda e:search());ttk.Button(window,text='Search',command=search).pack(pady=4);ttk.Button(window,text='Use Selected Item',command=use).pack(pady=8);search()

    def destroy(self):
        if getattr(self,'cic_session',None):self.cic_session.stop();self.cic_session=None
        super().destroy()
