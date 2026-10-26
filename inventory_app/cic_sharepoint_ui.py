"""Opt-in Microsoft intake configuration and nonblocking folder polling."""
import json
from pathlib import Path
import queue
import secrets
import threading
import tkinter as tk
from tkinter import ttk, filedialog

from .cic_sharepoint import FIELDS, FAMILIES, InboxReader, load_profile
from .cic_questions import QUESTIONS
from .config import load_device_settings, _save_device_settings


class MicrosoftCicUiMixin:
    def _init_microsoft_cic(self, controls):
        self.microsoft_reader = None
        self.microsoft_worker = None
        self.microsoft_results = queue.Queue()
        self.microsoft_errors = []
        self.microsoft_status = tk.StringVar(value='Microsoft intake is not configured.')
        ttk.Button(controls, text='Microsoft Intake', command=self._microsoft_setup).pack(side='left', padx=3)
        ttk.Button(controls, text='Correct Microsoft Answers', command=self._correct_microsoft_answers).pack(side='left', padx=3)
        ttk.Label(self.cic_tab, textvariable=self.microsoft_status, wraplength=1100).grid(row=4, column=0, sticky='w', pady=4)
        settings = load_device_settings().get('cic_microsoft', {})
        if settings.get('enabled'):
            try:
                self._activate_microsoft(settings)
            except Exception as error:
                self.microsoft_status.set('Microsoft intake needs attention: ' + str(error))
        self.after(1000, self._poll_microsoft_cic)

    def _activate_microsoft(self, settings):
        if settings.get('database_path') and settings['database_path'] != str(self.service.settings.database_path):
            raise ValueError('This intake belongs to another database. Reconfigure it for the current inventory.')
        profile = load_profile(settings['profile_path'])
        folder = Path(settings['inbox_path'])
        if not folder.is_dir():
            raise ValueError('Select the local OneDrive-synced ACE CIC Inbox folder.')
        self.microsoft_reader = InboxReader(self.service, folder, profile, settings['secret'])
        self.microsoft_status.set(f'Microsoft intake enabled. Reading {folder}. OneDrive must be running; cards wait for staff approval.')

    def _microsoft_setup(self):
        try:
            self._cic_admin()
        except Exception as error:
            self._show_error(str(error)); return
        dialog = tk.Toplevel(self); dialog.title('Microsoft CIC Intake'); dialog.transient(self)
        frame = ttk.Frame(dialog, padding=18); frame.pack(fill='both', expand=True)
        settings = load_device_settings().get('cic_microsoft', {})
        enabled = tk.BooleanVar(value=settings.get('enabled', False))
        profile = tk.StringVar(value=settings.get('profile_path', ''))
        inbox = tk.StringVar(value=settings.get('inbox_path', ''))
        ttk.Label(frame, text='Microsoft Forms sends cards to your approved SharePoint site. OneDrive synchronizes the dedicated ACE CIC Inbox to this computer.\nACE only reads those files. It never edits, moves or deletes them. A new card still needs staff approval.', wraplength=700).pack(anchor='w', pady=8)
        ttk.Checkbutton(frame, text='Automatically receive Microsoft CIC cards on this computer', variable=enabled).pack(anchor='w')
        for label, var, browse in [('CIC form profile', profile, lambda: filedialog.askopenfilename(parent=dialog, filetypes=[('ACE CIC profile', '*.json')])),
                                   ('Local synchronized ACE CIC Inbox', inbox, lambda: filedialog.askdirectory(parent=dialog))]:
            ttk.Label(frame, text=label).pack(anchor='w', pady=(12, 0))
            row = ttk.Frame(frame); row.pack(fill='x')
            ttk.Entry(row, textvariable=var, width=85).pack(side='left', fill='x', expand=True)
            ttk.Button(row, text='Browse', command=lambda v=var, b=browse: v.set(b() or v.get())).pack(side='left')
        def save():
            if self.microsoft_worker and self.microsoft_worker.is_alive():
                self._show_error('An intake scan is finishing. Try again in a moment.'); return
            data = {'enabled': enabled.get(), 'profile_path': profile.get(), 'inbox_path': inbox.get(),
                    'database_path': str(self.service.settings.database_path),
                    'secret': settings.get('secret') or secrets.token_urlsafe(32)}
            try:
                if enabled.get():
                    self._activate_microsoft(data)
                else:
                    self.microsoft_reader = None
                    self.microsoft_status.set('Microsoft intake paused. Existing cards remain available for review.')
                device = load_device_settings(); device['cic_microsoft'] = data
                if not _save_device_settings(device):
                    raise ValueError('Could not save device configuration.')
                dialog.destroy()
            except Exception as error:
                self._show_error(str(error))
        ttk.Button(frame, text='Save Configuration', command=save).pack(pady=12)
        ttk.Button(frame, text='Show Intake Errors', command=lambda: self._show_info('\n\n'.join(f'{f}: {e}' for f, e in self.microsoft_errors) or 'No intake errors reported.')).pack()

    def _poll_microsoft_cic(self):
        while True:
            try:
                reader, result = self.microsoft_results.get_nowait()
            except queue.Empty:
                break
            if reader is not self.microsoft_reader:
                continue
            cards, errors = result
            self.microsoft_errors = errors
            if errors:
                self.microsoft_status.set(f'Microsoft intake needs attention: {len(errors)} error(s). {errors[0][0]}: {errors[0][1]}')
            else:
                self.microsoft_status.set('Microsoft inbox checked. OneDrive sync status must also be checked. Submitted cards wait for staff approval.')
            if cards:
                self.refresh_cic()
                self._set_status(f'{len(cards)} Microsoft CIC card(s) received. Review them in Cadet Inventory Cards.')
                if self.notebook.select() != str(self.cic_tab):
                    self.cic_unread += len(cards)
                    self.notebook.tab(self.cic_tab, text=f'Cadet Inventory Cards ({self.cic_unread} new)')
        if self.microsoft_reader and not (self.microsoft_worker and self.microsoft_worker.is_alive()):
            reader = self.microsoft_reader
            def scan():
                try:
                    result = reader.poll()
                except Exception as error:
                    result = ([], [('Inbox', str(error))])
                self.microsoft_results.put((reader, result))
            self.microsoft_worker = threading.Thread(target=scan, name='ACE-Microsoft-CIC', daemon=True)
            self.microsoft_worker.start()
        self.after(10000, self._poll_microsoft_cic)

    def _correct_microsoft_answers(self):
        try:
            self._cic_admin()
            if not self.microsoft_reader:
                raise ValueError('Configure Microsoft Intake with this form profile first.')
            card_id = self._selected_cic()
            if not card_id:
                raise ValueError('Select a Microsoft CIC card first.')
            card = self.service.get_cic(card_id)
            if card['status'] not in ('Pending', 'Held'):
                raise ValueError('Finalized cards cannot be changed.')
            answers = self.service.microsoft_cic_answers(card_id, self.microsoft_reader.profile)
            if answers is None:
                raise ValueError('This card was not received from Microsoft Forms.')
        except Exception as error:
            self._show_error(str(error)); return
        dialog = tk.Toplevel(self); dialog.title('Correct Microsoft CIC Answers'); dialog.geometry('850x740')
        frame = ttk.Frame(dialog, padding=12); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Correct identity, counts or size lines below.\nSize lines: item ID or full catalog name | exact size | quantity.\nThe original submission is retained. Saving corrections does not approve the card.', wraplength=800).pack(anchor='w', pady=8)
        tabs=ttk.Notebook(frame);tabs.pack(fill='both',expand=True)
        variables={};text_fields={}
        def entry(parent,key,label,choices=None):
            ttk.Label(parent,text=label).pack(anchor='w',pady=(8,2))
            var=tk.StringVar(value=answers.get(key,''));variables[key]=var
            widget=ttk.Combobox(parent,textvariable=var,values=choices,state='readonly') if choices else ttk.Entry(parent,textvariable=var)
            widget.pack(fill='x');return widget
        identity=ttk.Frame(tabs,padding=12);tabs.add(identity,text='Identity')
        for key,label in FIELDS[:4]:entry(identity,key,label)
        for family_key,family in FAMILIES:
            page=ttk.Frame(tabs);tabs.add(page,text=family)
            canvas=tk.Canvas(page,highlightthickness=0);scroll=ttk.Scrollbar(page,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            body=ttk.Frame(canvas,padding=12);body_id=canvas.create_window((0,0),window=body,anchor='nw')
            body.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>',lambda e,c=canvas,i=body_id:c.itemconfigure(i,width=e.width))
            entry(body,family_key+'.has_items','Possesses any '+family+' items?',('Yes','No','yes','no'))
            for key,fam,label in QUESTIONS:
                if fam!=family:continue
                group=ttk.LabelFrame(body,text=label,padding=10);group.pack(fill='x',pady=8)
                entry(group,key+'.has_item','Possesses this item?',('Yes','No','yes','no'))
                entry(group,key+'.count','Quantity')
                ttk.Label(group,text='Exact type or item ID | size | quantity, one line per size').pack(anchor='w',pady=(8,2))
                text=tk.Text(group,height=3,wrap='word');text.pack(fill='x');text.insert('1.0',answers.get(key+'.sizes',''));text_fields[key+'.sizes']=text
        def save():
            try:
                corrected={key:var.get() for key,var in variables.items()}
                corrected.update({key:text.get('1.0','end').strip() for key,text in text_fields.items()})
                for key,family in FAMILIES:
                    if corrected[key+'.has_items'].casefold()=='no':
                        for item,fam,_ in QUESTIONS:
                            if fam==family:corrected.update({item+'.has_item':'No',item+'.count':'0',item+'.sizes':''})
                for key,_,_ in QUESTIONS:
                    if corrected[key+'.has_item'].casefold()=='no':corrected.update({key+'.count':'0',key+'.sizes':''})
                self.service.correct_microsoft_cic(card_id, corrected, approved_by=self._cic_admin(), expected_version=card['version'])
                self.refresh_cic(); dialog.destroy()
            except Exception as error:
                self._show_error(str(error))
        ttk.Button(frame, text='Save Corrections for Review', command=save).pack(pady=8)
