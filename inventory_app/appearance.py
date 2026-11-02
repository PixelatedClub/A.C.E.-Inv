"""Local appearance preferences scoped to the authenticated A.C.E. administrator."""
import hashlib
import re
from .config import load_device_settings, _save_device_settings, BASE_DIR
from .usb_portable import read_marker
from .layout import ResizableSplit

DEFAULTS = dict(background='#eef4fb', accent='#1f4f82', lists='#ffffff', layout='default')
PRESETS = {
    'Auburn (Default)': dict(background='#eef4fb', accent='#1f4f82', lists='#ffffff'),
    'Light': dict(background='#f4f4f5', accent='#3f4c6b', lists='#ffffff'),
    'Midnight': dict(background='#1d2430', accent='#80bfff', lists='#111820'),
    'Forest': dict(background='#edf3ed', accent='#326747', lists='#ffffff'),
    'Slate': dict(background='#e9edf2', accent='#475569', lists='#f8fafc'),
    'High Contrast': dict(background='#000000', accent='#ffdf00', lists='#101010'),
}

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

def apply_preferences(app, palette=None, *, apply_layout=True):
    # Always restore the default palette before applying a different user's choices.
    app._configure_style()
    palette=preferences(app) if palette is None else palette
    background=palette['background'];accent=palette['accent'];lists=palette['lists']
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
            child.configure(background='#454545' if ink(background)=='#ffffff' else '#d0d0d0')
            if apply_layout and child is not getattr(app,'generator_stack',None):child.set_arrangement(palette['layout'])
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
    existing=getattr(app,'_appearance_window',None)
    if existing is not None and existing.winfo_exists():
        if existing.appearance_owner==key:
            existing.lift();return existing
        existing.destroy()
    window=tk.Toplevel(app);window.title('Personal Appearance and Layout');window.resizable(True,True)
    app._appearance_window=window;window.appearance_owner=key
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
    ttk.Label(frame,text='Personal Appearance',style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w')
    ttk.Label(frame,text='Colors preview immediately. Save keeps them for your login; Cancel restores your saved colors.',wraplength=480).grid(row=1,column=0,columnspan=3,sticky='w',pady=(4,14))
    saved=preferences(app);preview=dict(saved)
    values={name:tk.StringVar(window,value=saved[name]) for name in DEFAULTS}
    preset=tk.StringVar(window,value='Custom')
    pending=[None];committed=[False]
    ttk.Label(frame,text='Color preset').grid(row=2,column=0,sticky='w',pady=6)
    presets=ttk.Combobox(frame,textvariable=preset,values=list(PRESETS),state='readonly')
    presets.grid(row=2,column=1,columnspan=2,sticky='ew',padx=(10,0))
    def color_value(value):
        value=value.strip()
        if re.fullmatch(r'[0-9a-fA-F]{6}',value):value='#'+value
        return value.lower() if re.fullmatch(r'#[0-9a-fA-F]{6}',value) else None
    def preview_changes():
        pending[0]=None
        if not window.winfo_exists() or identity(app)!=key:return
        for name in ('background','accent','lists'):
            color=color_value(values[name].get())
            if color:preview[name]=color
        layout_changed=preview['layout']!=values['layout'].get()
        preview['layout']=values['layout'].get()
        apply_preferences(app,preview,apply_layout=layout_changed)
        preset.set(next((name for name,colors in PRESETS.items() if all(preview[k]==v for k,v in colors.items())),'Custom'))
    def changed(*_args):
        if pending[0] is not None:window.after_cancel(pending[0])
        pending[0]=window.after(70,preview_changes)
    def choose(name):
        color=colorchooser.askcolor(color_value(values[name].get()) or preview[name],parent=window)[1]
        if color:values[name].set(color)
    for row,(name,label) in enumerate([('background','Menu background'),('accent','Buttons and selected tabs'),('lists','Lists and text fields')],3):
        ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=6)
        ttk.Entry(frame,textvariable=values[name],width=12).grid(row=row,column=1,sticky='ew',padx=10)
        ttk.Button(frame,text='Choose...',command=lambda n=name:choose(n)).grid(row=row,column=2)
    ttk.Label(frame,text='Panel arrangement').grid(row=6,column=0,sticky='w',pady=8)
    ttk.Combobox(frame,textvariable=values['layout'],values=['default','horizontal','vertical'],state='readonly').grid(row=6,column=1,columnspan=2,sticky='ew',padx=(10,0))
    ttk.Label(frame,text='Vertical stacks panels top to bottom. Drag the divider to change their heights. Right-click a divider for individual layout controls.',wraplength=480).grid(row=7,column=0,columnspan=3,sticky='w',pady=10)
    def stop_preview():
        if pending[0] is not None:
            window.after_cancel(pending[0]);pending[0]=None
    def closed(event):
        if event.widget is not window:return
        stop_preview()
        if not committed[0]:
            try:
                if app.winfo_exists():apply_preferences(app,apply_layout=preview['layout']!=saved['layout'])
            except tk.TclError:pass
    window.bind('<Destroy>',closed,add='+')
    window.protocol('WM_DELETE_WINDOW',window.destroy)
    window.bind('<Escape>',lambda _event:window.destroy())
    def save():
        if identity(app)!=key:
            app._show_error('The signed-in administrator changed. Reopen Personal Appearance.');return
        data={name:color_value(values[name].get()) for name in ('background','accent','lists')}
        data['layout']=values['layout'].get()
        if any(data[name] is None for name in ('background','accent','lists')):
            app._show_error('Choose colors or enter a six-digit hex color such as #1f4f82.');return
        settings=load_device_settings();settings.setdefault('user_appearance',{})[key]=data
        if not _save_device_settings(settings):app._show_error('Could not save personal appearance.');return
        stop_preview();committed[0]=True
        apply_preferences(app,apply_layout=data['layout']!=saved['layout'])
        window.destroy();app._set_status('Personal appearance saved for your login.')
    def select_preset(name):
        for field,value in PRESETS[name].items():values[field].set(value)
    presets.bind('<<ComboboxSelected>>',lambda _event:select_preset(preset.get()))
    for variable in values.values():variable.trace_add('write',changed)
    preset.set(next((name for name,colors in PRESETS.items() if all(saved[k]==v for k,v in colors.items())),'Custom'))
    buttons=ttk.Frame(frame);buttons.grid(row=8,column=0,columnspan=3,sticky='e',pady=(10,0))
    ttk.Button(buttons,text='Use Default Colors',command=lambda:select_preset('Auburn (Default)')).pack(side='left',padx=4)
    ttk.Button(buttons,text='Save',command=save).pack(side='left',padx=4)
    ttk.Button(buttons,text='Cancel',command=window.destroy).pack(side='left',padx=4)
    return window
