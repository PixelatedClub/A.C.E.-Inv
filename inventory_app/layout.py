"""Draggable work areas. Layout changes never write inventory data."""
import tkinter as tk
from tkinter import ttk


class ResizableSplit(tk.PanedWindow):
    def __init__(self, parent, *, orient=tk.HORIZONTAL, fraction=0.65, **kwargs):
        super().__init__(parent, orient=orient, sashwidth=10, sashrelief='raised',
                         showhandle=True, handlesize=10, opaqueresize=True,
                         borderwidth=0, background='#c8d1da', **kwargs)
        self.fraction=fraction
        self.default_orient=orient
        self.original_minimums=None
        self.initialized=False
        self.bind('<Configure>',self._initial_size)
        self.bind('<Double-Button-1>',self._double_click)
        self.bind('<Button-3>',self._layout_menu)

    def _layout_menu(self,event):
        if not self.identify(event.x,event.y):return
        menu=tk.Menu(self,tearoff=False)
        menu.add_command(label='Stack panels vertically',command=lambda:self.set_arrangement('vertical'))
        menu.add_command(label='Arrange panels side by side',command=lambda:self.set_arrangement('horizontal'))
        menu.add_command(label='Reset layout',command=lambda:self.set_arrangement('default'))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def set_arrangement(self,arrangement):
        if self.original_minimums is None:
            self.original_minimums={str(p):self.panecget(p,'minsize') for p in self.panes()}
        orient=self.default_orient if arrangement=='default' else arrangement
        self.configure(orient=orient)
        for pane in self.panes():
            minimum=self.original_minimums.get(str(pane),90) if arrangement=='default' else (90 if orient=='vertical' else 160)
            self.paneconfigure(pane,minsize=minimum)
        self.after_idle(self.reset)

    def _initial_size(self, event=None):
        if not self.initialized and self.winfo_width()>50 and self.winfo_height()>50 and len(self.panes())>=2:
            self.reset()
            self.initialized=True

    def reset(self):
        if len(self.panes())<2:return
        vertical=str(self.cget('orient'))=='vertical'
        size=self.winfo_height() if vertical else self.winfo_width()
        position=round(size*self.fraction)
        self.sash_place(0,0 if vertical else position,position if vertical else 0)

    def _double_click(self,event):
        if self.identify(event.x,event.y):
            self.reset()
            return 'break'


class ScrollablePanel(ttk.Frame):
    def __init__(self,parent,*,stretch=False):
        super().__init__(parent)
        self.stretch=stretch
        self.columnconfigure(0,weight=1);self.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(self,highlightthickness=0,width=340,height=200)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body=ttk.Frame(self.canvas,padding=8)
        self.window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.canvas.bind('<Configure>',self._resize)
        self.body.bind('<Configure>',self._resize)
        self.bind('<Map>',lambda e:self._bind_wheel(self.body))

    def _resize(self,event=None):
        options=dict(width=self.canvas.winfo_width())
        if self.stretch:options['height']=max(self.canvas.winfo_height(),self.body.winfo_reqheight())
        self.canvas.itemconfigure(self.window,**options)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _bind_wheel(self,widget):
        widget.bind('<MouseWheel>',self._wheel)
        for child in widget.winfo_children():self._bind_wheel(child)

    def _wheel(self,event):
        if isinstance(event.widget,(ttk.Treeview,tk.Text,tk.Listbox,ttk.Combobox)):return
        if self.body.winfo_height()>self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
            return 'break'
