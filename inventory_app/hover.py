"""Visual hover feedback without changing selection or business actions."""
HOVER_TAG = '__ace_hover__'


def install_hover(tree):
    tree.tag_configure(HOVER_TAG,background='#dceafb',foreground='#111111')
    current=[None]
    def clear(event=None):
        if current[0] and tree.exists(current[0]):
            tree.item(current[0],tags=tuple(t for t in tree.item(current[0],'tags') if t!=HOVER_TAG))
        current[0]=None
    def motion(event):
        row=tree.identify_row(event.y) if tree.identify_region(event.x,event.y) in ('cell','tree') else ''
        if row==current[0] and row and HOVER_TAG in tree.item(row,'tags'):return
        clear()
        if row:
            tree.item(row,tags=(HOVER_TAG,)+tuple(tree.item(row,'tags')))
            current[0]=row
    tree.bind('<Motion>',motion,add='+')
    tree.bind('<Leave>',clear,add='+')
    tree.bind('<Unmap>',clear,add='+')
    # Scrolling can move another record beneath a stationary pointer.
    tree.bind('<MouseWheel>',clear,add='+')
