"""Tag chips, family/season selectors, and an embedded PNG image viewer."""
import base64
import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .item_metadata import FAMILIES, SEASONS, normalize_tags, save_metadata


def edit_metadata(app):
    selected=app.items_tree.selection()
    if not selected:
        app._show_error('Select an item first.')
        return
    barcode=selected[0]
    rows=app.service.list_items(search=barcode)
    row=next((r for r in rows if r['barcode_id']==barcode),None)
    if row is None: return
    with app.service.database.connect() as db:
        record=db.execute('SELECT * FROM item_metadata WHERE barcode_id=?',(barcode,)).fetchone()
    window=tk.Toplevel(app); window.title('Tags and image: '+barcode)
    window.transient(app); window.grab_set()
    frame=ttk.Frame(window,padding=16); frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=row['item_name']+' | '+row['variant']).pack(anchor='w')
    ttk.Label(frame,text='Category tags (automatic): '+row['category']+', '+row['item_type'],wraplength=600).pack(anchor='w',pady=5)
    tags=set(row['custom_tags']); chips=ttk.Frame(frame); chips.pack(fill='x')
    def redraw():
        for child in chips.winfo_children(): child.destroy()
        for i,tag in enumerate(sorted(tags)):
            ttk.Button(chips,text=tag+'  x',command=lambda t=tag:remove(t)).grid(row=i//3,column=i%3,padx=2,pady=2)
    def remove(tag): tags.remove(tag); redraw()
    redraw()
    entry_var=tk.StringVar(window)
    suggestions=sorted({tag for r in app.service.list_items() for tag in r['tags']})
    entry=ttk.Combobox(frame,textvariable=entry_var,values=suggestions,width=55); entry.pack(fill='x',pady=6)
    def suggest(e=None):
        needle=entry_var.get().strip().casefold()
        entry.configure(values=[tag for tag in suggestions if needle in tag])
    def add(e=None):
        try:
            proposed=normalize_tags(list(tags)+entry_var.get().split(','))
            if any(len(t)>60 for t in proposed): raise ValueError('Tags must be 60 characters or fewer.')
            tags.clear(); tags.update(proposed); entry_var.set(''); redraw()
        except ValueError as exc: messagebox.showerror('Tags',str(exc),parent=window)
        return 'break'
    entry.bind('<KeyRelease>',suggest); entry.bind('<Return>',add)
    ttk.Button(frame,text='Add tag (or type comma-separated tags)',command=add).pack(anchor='w')
    family=tk.StringVar(window,value=record['family'] if record and record['family'] else 'Automatic')
    season=tk.StringVar(window,value=row['season'])
    for label,var,values in [('Uniform family',family,('Automatic',)+FAMILIES),('Season',season,SEASONS)]:
        ttk.Label(frame,text=label).pack(anchor='w',pady=(8,0))
        ttk.Combobox(frame,textvariable=var,values=values,state='readonly',width=35).pack(anchor='w')
    ttk.Label(frame,text='Season is an inventory analysis tag, not an authorization to wear an item.').pack(anchor='w',pady=6)
    image_value=[record['image_png'] if record else '']; image_changed=[False]
    preview=ttk.Label(frame,text='No item image'); preview.pack(pady=8)
    def render():
        if not image_value[0]: preview.configure(image='',text='No item image'); preview.image=None; return
        try:
            photo=tk.PhotoImage(master=window,data=image_value[0])
            photo=photo.subsample(max(1,math.ceil(max(photo.width()/420,photo.height()/210))))
            preview.configure(image=photo,text=''); preview.image=photo
        except tk.TclError: preview.configure(image='',text='Image could not be displayed')
    def choose():
        path=filedialog.askopenfilename(parent=window,title='Choose item PNG',filetypes=[('PNG images','*.png')])
        if not path:return
        try:
            if Path(path).stat().st_size>2_000_000: raise ValueError('PNG must be 2 MB or smaller.')
            data=Path(path).read_bytes()
            from .image_utils import read_png_dimensions
            if max(read_png_dimensions(data))>4096: raise ValueError('PNG must be 4096 pixels per side or smaller.')
            encoded=base64.b64encode(data).decode('ascii')
            tk.PhotoImage(master=window,data=encoded) # Decode before accepting.
            image_value[0]=encoded; image_changed[0]=True; render()
        except (ValueError,OSError,tk.TclError) as exc: messagebox.showerror('Image',str(exc),parent=window)
    def clear_image(): image_value[0]=''; image_changed[0]=True; render()
    render()
    buttons=ttk.Frame(frame); buttons.pack(fill='x')
    ttk.Button(buttons,text='Choose PNG...',command=choose).pack(side='left')
    ttk.Button(buttons,text='Remove image',command=clear_image).pack(side='left')
    def save():
        try:
            pending=normalize_tags(list(tags)+entry_var.get().split(','))
            save_metadata(app.service,barcode,pending,'' if family.get()=='Automatic' else family.get(),season.get(),
                          image_value[0] if image_changed[0] else None)
        except (ValueError,OSError) as exc: messagebox.showerror('Item metadata',str(exc),parent=window); return
        window.destroy(); app.refresh_items_tree()
    ttk.Button(buttons,text='Save',command=save).pack(side='right')
    ttk.Button(buttons,text='Cancel',command=window.destroy).pack(side='right')
