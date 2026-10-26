"""University connection setup; stores public application IDs only."""
import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk,messagebox
from .identity import validate_profile
from .server import DEFAULT_DATA


def configure(parent):
    win=tk.Toplevel(parent);win.title('University connection settings');win.transient(parent)
    ttk.Label(win,text='Enter the settings supplied by campus IT. No password or client secret is needed.',wraplength=500).grid(row=0,column=0,columnspan=2,padx=15,pady=15)
    path=DEFAULT_DATA/'university.json'
    old=json.loads(path.read_text()) if path.exists() else {}
    variables={}
    fields=[('url','HTTPS API URL'),('tenant_id','Auburn tenant ID'),('client_id','Desktop application ID'),
            ('api_client_id','API application ID'),('drive_id','SharePoint drive ID (optional)'),('folder_id','SharePoint folder ID (optional)')]
    for row,(key,label) in enumerate(fields,1):
        variables[key]=tk.StringVar(value=old.get('sharepoint',{}).get(key,'') if key in ('drive_id','folder_id') else old.get(key,''))
        ttk.Label(win,text=label).grid(row=row,column=0,padx=15,pady=5,sticky='w')
        ttk.Entry(win,textvariable=variables[key],width=60).grid(row=row,column=1,padx=15,pady=5)
    def save():
        values={k:v.get().strip() for k,v in variables.items()}
        profile={k:values[k] for k in ('url','tenant_id','client_id','api_client_id')}
        profile['auth']='entra';profile['sharepoint']={k:values[k] for k in ('drive_id','folder_id')}
        try:
            validate_profile(profile)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(profile,indent=2))
            interpreter=Path(__file__).resolve().parent.parent/'.venv-beta'/'Scripts'/'pythonw.exe'
            subprocess.Popen([str(interpreter if interpreter.exists() else sys.executable),'-m','shared_beta.client','--profile',str(path)],
                cwd=Path(__file__).resolve().parent.parent,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            win.destroy()
        except (ValueError,OSError) as exc:messagebox.showerror('Connection settings',str(exc),parent=win)
    ttk.Button(win,text='Save and open university client',command=save).grid(row=len(fields)+1,column=1,padx=15,pady=15)
