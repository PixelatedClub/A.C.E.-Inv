"""Draggable work areas. Layout changes never write inventory data."""
import tkinter as tk
from tkinter import ttk


class ResizableSplit(tk.PanedWindow):
    def __init__(self, parent, *, orient=tk.HORIZONTAL, fraction=0.65, **kwargs):
        super().__init__(parent, orient=orient, sashwidth=10, sashrelief='raised',
                         showhandle=True, handlesize=10, opaqueresize=True,
                         borderwidth=0, background='#c8d1da', **kwargs)
        self.fraction=fraction
        self.initialized=False
        self.bind('<Configure>',self._initial_size)
        self.bind('<Double-Button-1>',self._double_click)

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
    def __init__(self,parent):
        super().__init__(parent)
        self.columnconfigure(0,weight=1);self.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(self,highlightthickness=0,width=340,height=200)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body=ttk.Frame(self.canvas,padding=8)
        self.window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window,width=e.width))
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.bind('<Map>',lambda e:self._bind_wheel(self.body))

    def _bind_wheel(self,widget):
        widget.bind('<MouseWheel>',self._wheel)
        for child in widget.winfo_children():self._bind_wheel(child)

    def _wheel(self,event):
        if self.body.winfo_height()>self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
            return 'break'
