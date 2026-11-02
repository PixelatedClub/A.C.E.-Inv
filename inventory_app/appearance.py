"""Local appearance preferences scoped to the authenticated A.C.E. administrator."""
import hashlib
import re
from .config import load_device_settings, _save_device_settings, BASE_DIR
from .usb_portable import read_marker
from .layout import ResizableSplit

DEFAULTS = dict(background='#eef4fb', accent='#1f4f82', lists='#ffffff', layout='default')

def identity(app):
    admin=app.current_admin
    if not admin:return None
    marker=read_marker(BASE_DIR)
    inventory=marker['package_id'] if marker else hashlib.sha256(str(app.settings.database_path).casefold().encode()).hexdigest()
    person=str(admin.get('admin_id')) if admin.get('admin_id') is not None else 'role:'+str(admin.get('role','')).upper()
    return inventory+':'+person

def preferences(app):
    key=identity(app)
    saved=load_device_settings().get('user_appearance',{}).get(key,{}) if key else {}
    result=dict(DEFAULTS)
    for name in ('background','accent','lists'):
        if re.fullmatch(r'#[0-9a-fA-F]{6}',str(saved.get(name,''))):result[name]=saved[name]
    if saved.get('layout') in ('default','vertical','horizontal'):result['layout']=saved['layout']
    return result

def ink(color):
    channels=[int(color[n:n+2],16)/255 for n in (1,3,5)]
    channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    luminance=sum(v*w for v,w in zip(channels,(.2126,.7152,.0722)))
    return '#111111' if luminance>.179 else '#ffffff'

def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)

def apply_preferences(app):
    # Always restore the default palette before applying a different user's choices.
    app._configure_style()
    palette=preferences(app);background=palette['background'];accent=palette['accent'];lists=palette['lists']
    text=ink(background);button_text=ink(accent);list_text=ink(lists);style=app.style
    app.configure(background=background)
    for name in ('TFrame','TLabelframe','TNotebook','TLabel','Title.TLabel','Subtitle.TLabel','SummaryValue.TLabel','SummaryLabel.TLabel','TLabelframe.Label','TCheckbutton','TRadiobutton'):
        style.configure(name,background=background,foreground=text)
    style.configure('TLabelframe',bordercolor=accent)
    style.configure('TButton',background=accent,foreground=button_text)
    style.map('TButton',background=[('active',accent),('pressed',accent)],foreground=[('disabled','#888888'),('!disabled',button_text)])
    style.configure('TNotebook.Tab',background=background,foreground=text)
    style.map('TNotebook.Tab',background=[('selected',accent)],foreground=[('selected',button_text)])
    for name in ('TEntry','Scan.TEntry','TCombobox','TSpinbox'):
        style.configure(name,fieldbackground=lists,foreground=list_text,insertcolor=list_text)
        style.map(name,fieldbackground=[('readonly',lists)],foreground=[('readonly',list_text)])
    style.configure('Treeview',background=lists,fieldbackground=lists,foreground=list_text)
    style.map('Treeview',background=[('selected',accent)],foreground=[('selected',button_text)])
    style.configure('Treeview.Heading',background=accent,foreground=button_text)
    style.map('Treeview.Heading',background=[('active',accent)])
    import tkinter as tk
    from tkinter import ttk
    for child in widgets(app):
        if isinstance(child,ResizableSplit):
            child.configure(background=accent)
            if child is not getattr(app,'generator_stack',None):child.set_arrangement(palette['layout'])
        elif isinstance(child,tk.Canvas):child.configure(background=background)
        elif isinstance(child,tk.Text):child.configure(background=lists,foreground=list_text,insertbackground=list_text)
        elif isinstance(child,ttk.Treeview):
            child.tag_configure('__ace_hover__',foreground='#111111')
            if child is getattr(app,'loan_tree',None):child.tag_configure('overdue',foreground='#111111')

def open_preferences(app):
    from tkinter import ttk,colorchooser
    import tkinter as tk
    key=identity(app)
    if not key:
        app._show_error('Sign in before changing personal appearance.');return
    window=tk.Toplevel(app);window.title('Personal Appearance and Layout');window.resizable(True,True)
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
    ttk.Label(frame,text='Personal Appearance',style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w')
    ttk.Label(frame,text='Saved for your administrator login on this computer.',wraplength=480).grid(row=1,column=0,columnspan=3,sticky='w',pady=(4,14))
    saved=preferences(app);values={name:tk.StringVar(window,value=saved[name]) for name in DEFAULTS}
    def choose(name):
        color=colorchooser.askcolor(values[name].get(),parent=window)[1]
        if color:values[name].set(color)
    for row,(name,label) in enumerate([('background','Menu background'),('accent','Buttons and selected tabs'),('lists','Lists and text fields')],2):
        ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=6)
        ttk.Entry(frame,textvariable=values[name],width=12).grid(row=row,column=1,sticky='ew',padx=10)
        ttk.Button(frame,text='Choose...',command=lambda n=name:choose(n)).grid(row=row,column=2)
    ttk.Label(frame,text='Panel arrangement').grid(row=5,column=0,sticky='w',pady=8)
    ttk.Combobox(frame,textvariable=values['layout'],values=['default','horizontal','vertical'],state='readonly').grid(row=5,column=1,columnspan=2,sticky='ew',padx=(10,0))
    ttk.Label(frame,text='Vertical stacks panels top to bottom. Drag the divider to change their heights. Right-click a divider for individual layout controls.',wraplength=480).grid(row=6,column=0,columnspan=3,sticky='w',pady=10)
    def save():
        if identity(app)!=key:
            app._show_error('The signed-in administrator changed. Reopen Personal Appearance.');return
        data={name:var.get().strip() for name,var in values.items()}
        if any(not re.fullmatch(r'#[0-9a-fA-F]{6}',data[name]) for name in ('background','accent','lists')):
            app._show_error('Choose colors or enter a six-digit hex color such as #1f4f82.');return
        settings=load_device_settings();settings.setdefault('user_appearance',{})[key]=data
        if not _save_device_settings(settings):app._show_error('Could not save personal appearance.');return
        apply_preferences(app);window.destroy();app._set_status('Personal appearance saved for your login.')
    def reset():
        for name,value in DEFAULTS.items():values[name].set(value)
    buttons=ttk.Frame(frame);buttons.grid(row=7,column=0,columnspan=3,sticky='e',pady=(10,0))
    ttk.Button(buttons,text='Use Default Colors',command=reset).pack(side='left',padx=4)
    ttk.Button(buttons,text='Save',command=save).pack(side='left',padx=4)
    ttk.Button(buttons,text='Cancel',command=window.destroy).pack(side='left',padx=4)
