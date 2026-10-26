"""Separate desktop client for the local shared-save beta."""
import argparse
import csv
import json
import uuid
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from .server import DEFAULT_DATA
from .identity import DesktopIdentity
from .secure_files import read_pending,write_pending
from .sharepoint import upload_report,NoRedirect
from urllib.request import build_opener


class Client(tk.Tk):
    def __init__(self, profile):
        super().__init__()
        self.title('A.C.E. Shared Save Beta 0.2.0')
        self.geometry('1120x720')
        self.profile = json.loads(profile.read_text())
        self.identity=DesktopIdentity(self.profile)
        self.encrypted=self.profile.get('auth')=='entra'
        self.pending_path = profile.with_suffix('.pending.dpapi' if self.encrypted else '.pending.json')
        self.pending = read_pending(self.pending_path,self.encrypted)
        self.state = {}
        self.status = tk.StringVar(value='Connecting...')
        ttk.Label(self,text='SHARED SAVE BETA | '+('University connection' if self.encrypted else 'Synthetic local test records')+' | Refresh to see other sessions',padding=10).pack(fill='x')
        bar = ttk.Frame(self,padding=6)
        bar.pack(fill='x')
        ttk.Button(bar,text='Refresh',command=self.refresh).pack(side='left')
        ttk.Button(bar,text='Retry unconfirmed save',command=self.retry).pack(side='left',padx=5)
        ttk.Button(bar,text='University connection settings',command=self.configure_connection).pack(side='left',padx=5)
        if self.encrypted:
            ttk.Button(bar,text='Sign in with Auburn',command=self.sign_in).pack(side='left',padx=5)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both',expand=True,padx=10,pady=5)
        self.tables = {}
        layouts = {
            'items':('Inventory',('id','barcode','name','category','size','wings','total','available','status')),
            'cadets':('Cadets',('id','name','email')),
            'issues':('Checkouts and Loans',('id','cadet_name','item_name','item_size','quantity','state','due','overdue')),
            'fittings':('Fittings',('cadet','category','size')),
        }
        for key,(label,columns) in layouts.items():
            frame=ttk.Frame(self.notebook)
            self.notebook.add(frame,text=label)
            buttons=ttk.Frame(frame,padding=5)
            buttons.pack(fill='x')
            if key=='items':
                ttk.Button(buttons,text='New item',command=lambda:self.item(False)).pack(side='left')
                ttk.Button(buttons,text='Edit selected item',command=lambda:self.item(True)).pack(side='left')
            elif key=='cadets':
                ttk.Button(buttons,text='New cadet',command=lambda:self.cadet(False)).pack(side='left')
                ttk.Button(buttons,text='Edit selected cadet',command=lambda:self.cadet(True)).pack(side='left')
            elif key=='issues':
                ttk.Button(buttons,text='Issue items / loan',command=self.issue).pack(side='left')
                for caption,mode in [('Return','returned'),('Permanent issue','acquired'),('Purchased','purchased'),('Convert loan to checkout','checkout')]:
                    ttk.Button(buttons,text=caption,command=lambda m=mode:self.resolve(m)).pack(side='left')
            else:
                ttk.Button(buttons,text='Save cadet fitting',command=self.fit).pack(side='left')
            tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
            for col in columns:
                tree.heading(col,text=col.replace('_',' ').title())
                tree.column(col,width=120,anchor='w')
            scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y')
            tree.pack(fill='both',expand=True)
            self.tables[key]=tree
        report=ttk.Frame(self.notebook,padding=15)
        self.notebook.add(report,text='Audit report')
        ttk.Label(report,text='Export dated audit history (UTC dates, inclusive). Leave dates blank for all activity.').pack(anchor='w')
        self.start=tk.StringVar(); self.end=tk.StringVar()
        for label,var in [('Start YYYY-MM-DD',self.start),('End YYYY-MM-DD',self.end)]:
            ttk.Label(report,text=label).pack(anchor='w',pady=(10,0));ttk.Entry(report,textvariable=var).pack(anchor='w')
        ttk.Button(report,text='Export audit CSV',command=self.export).pack(anchor='w',pady=15)
        if self.encrypted:
            ttk.Button(report,text='Publish report to SharePoint',command=self.publish).pack(anchor='w')
        ttk.Label(self,textvariable=self.status,padding=10).pack(fill='x')
        self.after(100,self.refresh)
        self.protocol('WM_DELETE_WINDOW',self.close)

    def api(self,path,payload=None):
        req=Request(self.profile['url']+path,data=json.dumps(payload).encode() if payload is not None else None,
                    headers={'Authorization':'Bearer '+self.identity.token(),'Content-Type':'application/json'})
        with build_opener(NoRedirect).open(req,timeout=5) as response:
            return json.load(response)

    def refresh(self):
        try:
            self.state=self.api('/v1/state')
            for key,tree in self.tables.items():
                tree.delete(*tree.get_children())
                for i,row in enumerate(self.state[key]):
                    tree.insert('', 'end',iid=str(i),values=[row[col] for col in tree['columns']])
            overdue=sum(r['overdue'] for r in self.state['issues'])
            account=self.state['account']
            self.status.set(f"{account['name']} ({account['role']}) | Revision {self.state['revision']} | {overdue} overdue loans" + (' | SAVE UNCONFIRMED - retry required' if self.pending else ''))
        except (OSError,ValueError) as exc:
            self.status.set('Sign in or check the configured API connection, then Refresh.' if self.encrypted else 'Server unavailable. Start the beta server and Refresh.')

    def selected(self,key):
        selection=self.tables[key].selection()
        if not selection:
            messagebox.showinfo('Select a record','Select a row first.',parent=self)
            return None
        return self.state[key][int(selection[0])]

    def form(self,title,fields,action,extra=None):
        if self.pending:
            messagebox.showinfo('Save unconfirmed','Retry the unconfirmed save before starting another change.',parent=self)
            return
        if not self.state or self.state['account']['role']!='operator':
            messagebox.showinfo('Read only','Connect with an operator test profile to make changes.',parent=self)
            return
        revision=self.state['revision']
        win=tk.Toplevel(self);win.title(title);win.transient(self);win.grab_set()
        entries={}
        for row,(key,value,choices) in enumerate(fields):
            ttk.Label(win,text=key.replace('_',' ').title()).grid(row=row,column=0,padx=12,pady=6,sticky='w')
            var=tk.StringVar(value=str(value));entries[key]=var
            widget=ttk.Combobox(win,textvariable=var,values=choices,state='readonly',width=48) if choices else ttk.Entry(win,textvariable=var,width=51)
            widget.grid(row=row,column=1,padx=12,pady=6)
        def submit():
            try:
                data=dict(extra or {})
                for key,var in entries.items():
                    value=var.get().strip()
                    data[key]=int(value.split(' | ')[0]) if key in ('total','quantity','cadet','item') else value
            except ValueError:
                messagebox.showerror('Invalid input','Select the item/cadet and enter whole-number quantities.',parent=win);return
            self.pending=dict(operation=str(uuid.uuid4()),action=action,data=data,revision=revision,
                              expected_actor=self.state['account']['name'])
            try:write_pending(self.pending_path,self.pending,self.encrypted)
            except OSError:
                self.pending=None
                messagebox.showerror('Save unavailable','Unable to protect the pending request on this device.',parent=win);return
            win.destroy();self.retry()
        ttk.Button(win,text='Save '+title.lower(),command=submit).grid(row=len(fields),column=1,pady=15)

    def retry(self):
        if not self.pending:
            return
        try:
            self.api('/v1/operations',self.pending)
            self.pending=None
            self.pending_path.unlink(missing_ok=True)
            self.refresh()
        except HTTPError as exc:
            try: detail=json.load(exc).get('error','Save failed.')
            except ValueError: detail='Save failed.'
            if exc.code < 500:
                self.pending=None
                self.pending_path.unlink(missing_ok=True)
            messagebox.showerror('Save not confirmed',detail,parent=self)
            self.refresh()
        except (OSError,ValueError):
            self.status.set('Save unconfirmed. Restore the server connection and click Retry; this will not duplicate the operation.')

    def item(self,edit):
        row=self.selected('items') if edit else {}
        if row is None:return
        self.form('Item',[(k,row.get(k,'' if k!='total' else 0),None) for k in ('name','category','size','wings','total')],
                  'save_item',{'id':row['id']} if edit else {})

    def cadet(self,edit):
        row=self.selected('cadets') if edit else {}
        if row is None:return
        self.form('Cadet',[(k,row.get(k,''),None) for k in ('name','email')],'save_cadet',{'id':row['id']} if edit else {})

    def choices(self,key):
        return [f"{r['id']} | {r['name']}"+(' | '+r['size'] if key=='items' else ' | '+r['email']) for r in self.state.get(key,[])]

    def issue(self):
        self.form('Issue', [('cadet','',self.choices('cadets')),('item','',self.choices('items')),('quantity',1,None),
                           ('state','loan',['loan','checkout']),('due','',None)],'issue')

    def resolve(self,mode):
        row=self.selected('issues')
        if row:self.form(mode.replace('_',' ').title(),[('quantity',row['quantity'],None)],'resolve',{'id':row['id'],'state':mode})

    def fit(self):
        self.form('Fitting',[('cadet','',self.choices('cadets')),('category','',None),('size','',None)],'fit')

    def export(self):
        try:
            rows=self.api('/v1/audit?'+urlencode(dict(start=self.start.get(),end=self.end.get())))
        except (OSError,ValueError):
            messagebox.showerror('Report unavailable','Check connection and date range (YYYY-MM-DD).',parent=self);return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',initialfile='ACE_Beta_Audit.csv')
        if not path:return
        def safe(value):
            text=str(value)
            return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
        with open(path,'w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f);writer.writerow(['Revision','Time UTC','Actor','Action','Record type','Record','Change','Operation ID'])
            for row in rows:
                before=json.loads(row['before_json']);after=json.loads(row['after_json'])
                for group in ('items','cadets','issues','fittings'):
                    def identity(r):return r.get('id',(r.get('cadet'),r.get('category')))
                    previous={identity(r):r for r in before[group]}
                    for record in after[group]:
                        old=previous.get(identity(record),{})
                        changes=[f'{k}: {old.get(k,"(new)")} -> {v}' for k,v in record.items()
                                 if old.get(k)!=v and k not in ('id','barcode','overdue')]
                        if changes:
                            label=record.get('name',record.get('item_name',str(identity(record))))
                            writer.writerow([safe(v) for v in [row['revision'],row['time'],row['actor'],row['action'],group,label,'; '.join(changes),row['operation']]])
        self.status.set(f'Exported {len(rows)} audited changes to {path}')

    def close(self):
        self.destroy()

    def sign_in(self):
        try:self.identity.token(interactive=True);self.refresh()
        except Exception as exc:messagebox.showerror('Auburn sign-in',str(exc),parent=self)

    def configure_connection(self):
        from .configure import configure
        configure(self)

    def publish(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('Reports','*.csv *.xlsx *.pdf')])
        if not path:return
        try:
            result=upload_report(self.profile,path,self.identity.token(interactive=True,graph=True))
            self.status.set('Published to configured SharePoint folder: '+result.get('name','report'))
        except Exception as exc:
            messagebox.showerror('SharePoint publication',str(exc),parent=self)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=DEFAULT_DATA/'test_williams.json')
    args=parser.parse_args()
    Client(args.profile).mainloop()


if __name__=='__main__':main()
