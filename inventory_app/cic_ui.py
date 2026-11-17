"""Microsoft CIC intake and explicit identity/item review."""
import json
import tkinter as tk
from tkinter import ttk,messagebox
from .barcode_utils import open_file
from .layout import ResizableSplit
from .cic import item_key, _remaining_line_issues
from .cic_sharepoint_ui import MicrosoftCicUiMixin


class CicUiMixin(MicrosoftCicUiMixin):
    def _build_cic_tab(self):
        self.cic_cards={};self.cic_unread=0;self.cic_search=tk.StringVar();self.cic_status=tk.StringVar(value='Cards arrive through Microsoft Forms, SharePoint and OneDrive. Review each card before approval.')
        self.notebook.bind('<<NotebookTabChanged>>',self._ack_cic_notice,add='+')
        self.cic_tab.columnconfigure(0,weight=1);self.cic_tab.rowconfigure(2,weight=1)
        controls=ttk.Frame(self.cic_tab);controls.grid(row=0,column=0,sticky='ew')
        for label,command in [('Copy Form Link',self._copy_microsoft_form_link),('Refresh',self.refresh_cic),('Review Selected Card',self._review_cic)]:
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
        self._init_microsoft_cic(controls)
        self.refresh_cic()

    def _cic_admin(self):
        if not self.current_admin:
            from .services import InventoryError
            raise InventoryError('Sign in as an ACE administrator before reviewing cards.')
        return self.current_admin

    def _copy_microsoft_form_link(self):
        if not self.microsoft_reader:
            self._show_error('Configure Microsoft Intake first.');return
        from urllib.parse import urlencode
        url='https://forms.cloud.microsoft/Pages/ResponsePage.aspx?'+urlencode({'id':self.microsoft_reader.profile['form_id']})
        self.clipboard_clear();self.clipboard_append(url)
        self._set_status('Microsoft CIC form link copied.')

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
            if card.get('intake_issues_json','[]')!='[]':
                import json
                content+='\n\nMicrosoft intake holds (Review Selected Card → Edit Form Answers):\n'+'\n'.join(json.loads(card['intake_issues_json']))
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
        existing = getattr(self, '_cic_review_window', None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            return
        card_id=self._selected_cic()
        if not card_id:self._show_error('Select a card first.');return
        try:actor=self._cic_admin();card=self.service.revalidate_cic(card_id)
        except Exception as error:self._show_error(str(error));return
        if card['status'] in ('Approved','Rejected'):self._show_info('This card has already been '+card['status'].lower()+'. Use Card Copy or Approved WINGS Export.');return
        dialog=tk.Toplevel(self)
        self._cic_review_window = dialog
        dialog.title(f"Review CIC — {card['cadet_name']}")
        dialog.geometry('1180x760')
        dialog.minsize(760,500)
        if dialog.tk.call('tk','windowingsystem') == 'win32':
            dialog.state('zoomed')
        frame=ttk.Frame(dialog,padding=14);frame.pack(fill='both',expand=True);frame.columnconfigure(0,weight=1);frame.rowconfigure(3,weight=1)
        ttk.Label(frame,text=f"{card['cadet_name']} | {card['cadet_email']}\nChoose an existing profile or explicitly create a new one. Existing profiles are never renamed here.",wraplength=950).grid(row=0,column=0,sticky='w')
        candidates=self.service.cic_candidates(card_id)
        # Include all profiles for manual selection without guessing an identity.
        ids={r['cadet_id'] for r in candidates}
        choices=[(None,'Create NEW cadet profile')]+[(r['cadet_id'],f"{r['match_reason']}: #{r['cadet_id']} {r['full_name']} <{r['email']}>") for r in candidates]+[(r['cadet_id'],f"Other profile: #{r['cadet_id']} {r['full_name']} <{r['email']}>") for r in self.service.list_cadets() if r['cadet_id'] not in ids]
        chosen=tk.StringVar(value=choices[1][1] if candidates else choices[0][1]);selector=ttk.Combobox(frame,textvariable=chosen,values=[x[1] for x in choices],state='readonly',width=100);selector.grid(row=1,column=0,sticky='ew',pady=8)
        issue_text = tk.StringVar()
        ttk.Label(frame,textvariable=issue_text,wraplength=950).grid(row=2,column=0,sticky='w')
        panes=ttk.Panedwindow(frame,orient='horizontal')
        panes.grid(row=3,column=0,sticky='nsew',pady=8)
        table=ttk.Frame(panes);table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        panes.add(table,weight=3)
        tree=self._create_tree(table,columns=['item_no','entered_name','entered_size','quantity','problem']);tree.grid(row=0,column=0,sticky='nsew')
        for column,label,width in [('item_no','Catalog ID',135),('entered_name','Item',220),
                                   ('entered_size','Size',95),('quantity','Qty',45),('problem','Review',85)]:
            tree.heading(column,text=label)
            tree.column(column,width=width,stretch=column=='entered_name')
        ordered_lines = sorted(card['lines'], key=lambda line: not bool(line['problem']))
        held_lines = [str(line['line_id']) for line in ordered_lines if line['problem']]
        form_issues = json.loads(card['intake_issues_json'])
        standalone = form_issues
        for line in ordered_lines:
            if line['problem']:
                standalone = _remaining_line_issues({'intake_issues_json':json.dumps(standalone)},line)
        issue_rows = {}
        for index, issue in enumerate(standalone):
            row_id = f'form-{index}'
            issue_rows[row_id] = issue
            field, separator, reason = issue.partition(': ')
            tree.insert('','end',iid=row_id,values=('',field,reason if separator else '', '', 'Form hold'))
        review_rows = list(issue_rows) + held_lines
        for line in ordered_lines:
            tree.insert('','end',iid=str(line['line_id']),values=(line['item_no'],line['entered_name'],
                line['entered_size'],line['quantity'],'Held' if line['problem'] else 'Matched'))
        detail=ttk.Labelframe(panes,text='Summary and reconciliation',padding=8)
        detail.columnconfigure(0,weight=1);detail.rowconfigure(0,weight=1)
        panes.add(detail,weight=2)
        preview=tk.Text(detail,width=40,wrap='word',state='disabled')
        preview.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(detail,orient='vertical',command=preview.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        preview.configure(yscrollcommand=scrollbar.set)
        context={'review':None}
        def display(text):
            preview.configure(state='normal')
            preview.delete('1.0','end')
            preview.insert('1.0',text)
            preview.configure(state='disabled')
        def summary():
            declared = sum(line['quantity'] for line in card['lines'])
            items = [f"{line['quantity']} × {line['entered_name']} / {line['entered_size']}"
                     + (' (held)' if line['problem'] else '') for line in card['lines']]
            text = f"Card summary • {declared} units on item lines\n" + '\n'.join(items)
            if form_issues:
                text = 'Form issues blocking approval\n' + '\n'.join(form_issues) + '\n\n' + text
            display(text)
        def selected_issue(event=None):
            selection = tree.selection()
            if selection and selection[0] in issue_rows:
                issue_text.set(issue_rows[selection[0]] + '\nDouble-click this row to edit the answer.')
            elif selection and selection[0] in held_lines:
                issue_text.set(f'Unresolved item {held_lines.index(selection[0])+1} of {len(held_lines)}. Choose Suggested Matches or Approve Local Item.')
            elif form_issues:
                shown = '\n'.join(form_issues[:2])
                issue_text.set(f'Approval on hold. Select Edit Form Answers.\n{shown}'
                               + (f'\n{len(form_issues)-2} more issue(s) in the summary.' if len(form_issues)>2 else ''))
            else:
                issue_text.set('Review the card summary, then preview reconciliation before approving.')
        def next_issue():
            if review_rows:
                selection = tree.selection()
                index = review_rows.index(selection[0])+1 if selection and selection[0] in review_rows else 0
                target = review_rows[index % len(review_rows)]
                tree.selection_set(target)
                tree.focus(target)
                tree.see(target)
        tree.bind('<<TreeviewSelect>>',selected_issue)
        next_issue()
        selected_issue()
        summary()
        def identify():
            cid=next(x[0] for x in choices if x[1]==chosen.get());return {'cadet_id':cid,'create_new':cid is None}
        def show_preview():
            try:
                review=self.service.preview_cic(card_id,**identify());context['review']=review
                content='\n'.join(f"{x['item_name']} / {x['size']}: declared {x['quantity']}, already checked out {x['existing']}, acquired/purchased {x['owned']}, NEW reconciled checkouts {x['add']}."+(f" WARNING: {x['excess']} more already recorded than declared; investigate separately. Nothing will be removed." if x['excess'] else '')+(' LOCAL: WINGS export blocked.' if not x['official'] else '') for x in review['plan'])
                display(content)
                return True
            except Exception as error:
                context['review']=None
                display(str(error))
                issue_text.set('Approval blocked. See the summary panel for the reason.')
                return False
        selector.bind('<<ComboboxSelected>>',lambda e:context.update(review=None))
        def approve():
            if not show_preview():return
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
        corrections=ttk.Frame(frame);corrections.grid(row=4,column=0,sticky='ew',pady=(0,7))
        decisions=ttk.Frame(frame);decisions.grid(row=5,column=0,sticky='ew')
        def action(parent,label,command):
            ttk.Button(parent,text=label,command=command).pack(side='left',padx=(0,6))
        def open_selected():
            selection=tree.selection()
            if selection and selection[0] in issue_rows:
                self._correct_microsoft_answers(card_id,dialog,focus_issue=issue_rows[selection[0]])
            else:
                self._map_cic_dialog(dialog,card_id,tree)
        action(corrections,'Suggested Matches',open_selected)
        action(corrections,'Approve Local Item',lambda:self._approve_local_item_dialog(dialog,card,tree))
        if getattr(self, 'microsoft_reader', None) and self.service.microsoft_cic_answers(card_id, self.microsoft_reader.profile) is not None:
            action(corrections,'Edit Form Answers',lambda:self._correct_microsoft_answers(card_id,dialog))
        action(corrections,'Card Summary',summary)
        if len(review_rows) > 1:
            def review_next():
                next_issue()
                open_selected()
            action(corrections,'Next Issue',review_next)
        action(decisions,'Preview Reconciliation',show_preview)
        action(decisions,'Approve Card',approve)
        action(decisions,'Reject Card',reject)
        action(decisions,'Keep on Hold' if card['status']=='Held' else 'Close',dialog.destroy)
        tree.bind('<Double-1>',lambda event:open_selected())
        if held_lines and not issue_rows:
            self._map_cic_dialog(dialog,card_id,tree)

    def _approve_local_item_dialog(self, review, card, tree):
        selected = tree.selection()
        line = next((r for r in card['lines'] if selected and str(r['line_id']) == selected[0]), None)
        if line is None or not line['problem']:
            self._show_error('Select an unresolved item line first.')
            return
        family = {'ocp':'OCP','ptg':'PTG','blues':'Blues','service':'Service Dress','other':'Other'}.get(
            line['group_key'].split('.')[0], '')
        window = tk.Toplevel(review)
        window.title('Approve Local Item')
        window.transient(review)
        frame = ttk.Frame(window,padding=14)
        frame.pack(fill='both',expand=True)
        frame.columnconfigure(1,weight=1)
        ttk.Label(frame,text=f"Submitted: {line['entered_name']} / {line['entered_size']} × {line['quantity']}",
                  wraplength=520).grid(row=0,columnspan=2,sticky='w',pady=(0,10))
        fields = {}
        for row, (key, label, default, choices) in enumerate((
            ('name','Catalog item name',line['entered_name'],None),
            ('size','Size',line['entered_size'],None),
            ('category','Category','',None),
            ('subcategory','Subcategory',family,None),
            ('sex','Fit','',('', 'M','F','U')),
            ('uom','Unit','EA',('EA','PR','SET')),
        ),1):
            var = tk.StringVar(value=default)
            fields[key] = var
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',padx=(0,8),pady=3)
            widget = (ttk.Combobox(frame,textvariable=var,values=choices,state='readonly') if choices
                      else ttk.Entry(frame,textvariable=var,width=44))
            widget.grid(row=row,column=1,sticky='ew',pady=3)
        def save():
            try:
                self.service.approve_cic_local_item(card['card_id'],line['line_id'],
                    expected_version=card['version'],approved_by=self._cic_admin(),
                    **{key: var.get() for key,var in fields.items()})
            except Exception as error:
                self._show_error(str(error))
                return
            review.destroy()
            self.refresh_cic()
            self._review_cic()
        ttk.Button(frame,text='Approve Local Item',command=save).grid(row=7,column=1,sticky='e',pady=(10,0))

    def _map_cic_dialog(self,review,card_id,tree):
        from .cic_matching import canonical
        selected=tree.selection()
        if not selected:self._show_error('Select the item line that needs correction.');return
        previous = getattr(review,'_cic_match_window',None)
        if previous is not None and previous.winfo_exists():
            previous.destroy()
        lid = int(selected[0])
        card = self.service.get_cic(card_id)
        if card['status'] not in ('Held','Pending'):
            self._show_error('Reopen the card to see its current status.')
            return
        line = next((r for r in card['lines'] if r['line_id']==lid), None)
        if line is None:
            self._show_error('This card changed. Reopen the review.')
            return
        suggestions = self.service.cic_line_suggestions(card_id,lid)
        window=tk.Toplevel(review);window.title('Review Suggested Catalog Matches');window.geometry('950x450');window.transient(review)
        review._cic_match_window = window
        ttk.Label(window,text=f"Submitted: {line['entered_name']} × {line['quantity']}",wraplength=880).pack(anchor='w',padx=12,pady=(10,0))
        status=tk.StringVar()
        ttk.Label(window,textvariable=status,wraplength=880).pack(anchor='w',padx=12,pady=4)
        query=tk.StringVar();entry=ttk.Entry(window,textvariable=query);entry.pack(fill='x',padx=12,pady=8)
        table=ttk.Frame(window);table.pack(fill='both',expand=True,padx=12);table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        results=self._create_tree(table,columns=['item_no','item_name','size','type','sex']);results.grid(row=0,column=0,sticky='nsew')
        for column, label, width in [('item_no','Catalog ID',200),('item_name','Catalog Item',310),
                                     ('size','Size',90),('type','Type',140),('sex','Fit',55)]:
            results.heading(column,text=label)
            results.column(column,width=width,stretch=column=='item_name')
        lookup={}
        def show(rows, suggested=False):
            results.delete(*results.get_children());lookup.clear()
            for i,row in enumerate(rows[:250]):
                name = row.get('item_name') or row['name']
                kind = row.get('subcategory','')
                if suggested and line['group_key'] in ('ocp.coat','ocp.trousers'):
                    tokens = canonical(name + ' ' + kind)
                    kind = ('Hot Weather' if 'summer' in tokens else 'All Weather'
                            if 'allweather' in tokens or row.get('official') else 'Weather unspecified')
                lookup[str(i)]=row
                results.insert('','end',iid=str(i),values=(row['item_no'],name,row['size'],kind,row['sex']))
            if suggested:
                status.set(f'{len(rows)} suggested catalog match(es). Choose the actual item, or keep the line on hold.'
                           if rows else 'No suggested match. Search the catalog, confirm a local item, or keep this line on hold.')
            else:
                status.set(f'{min(len(rows),250)} catalog search result(s).')
        def search():
            show(self.service.list_wings_catalog(search=query.get()))
        def use():
            selected=results.selection()
            if not selected:
                self._show_error('Select a catalog match first.')
                return
            row=lookup[selected[0]]
            try:
                self.service.map_cic_line(card_id,lid,row['item_no'],approved_by=self._cic_admin(),expected_version=card['version'])
                review.destroy();self.refresh_cic();self._review_cic()
            except Exception as error:self._show_error(str(error))
        def local():
            window.destroy()
            tree.selection_set(str(lid))
            self._approve_local_item_dialog(review,card,tree)
        entry.bind('<Return>',lambda e:search())
        actions=ttk.Frame(window);actions.pack(fill='x',padx=12,pady=10)
        for label,command in [('Use Selected Match',use),('Search Catalog',search),('Suggestions',lambda:show(suggestions,True)),
                              ('Approve Local Item',local),('Keep on Hold',window.destroy)]:
            ttk.Button(actions,text=label,command=command).pack(side='left',padx=3)
        show(suggestions,True)

    def destroy(self):
        self.microsoft_reader=None
        worker=getattr(self,'microsoft_worker',None)
        if worker and worker.is_alive():worker.join(timeout=2)
        super().destroy()
