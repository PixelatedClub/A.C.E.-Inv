"""Native pie charts for the application's existing dependency-free exporter."""
from xml.etree.ElementTree import Element, SubElement, tostring

OFFICE='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
X='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'


def node(parent, ns, element_name, text=None, **attrs):
    child=SubElement(parent,'{'+ns+'}'+element_name,{k:str(v) for k,v in attrs.items()})
    if text is not None: child.text=str(text)
    return child


def pie_parts(index, sheet):
    rows=sheet['rows']; name=sheet['sheet_name'].replace("'","''")
    root=Element('{'+C+'}chartSpace'); chart=node(root,C,'chart')
    title=node(chart,C,'title'); rich=node(node(title,C,'tx'),C,'rich')
    node(rich,A,'bodyPr');node(rich,A,'lstStyle')
    node(node(node(rich,A,'p'),A,'r'),A,'t',sheet['sheet_name']+' - recorded units')
    plot=node(chart,C,'plotArea');node(plot,C,'layout')
    pie=node(plot,C,'pieChart');node(pie,C,'varyColors',val=1)
    series=node(pie,C,'ser');node(series,C,'idx',val=0);node(series,C,'order',val=0)
    for container, ref, cache, col, field in [('cat','strRef','strCache','A','Group'),('val','numRef','numCache','B','Total Units')]:
        source=node(node(series,C,container),C,ref)
        node(source,C,'f',f"'{name}'!${col}$7:${col}${6+len(rows)}")
        cached=node(source,C,cache)
        if col=='B':node(cached,C,'formatCode','0')
        node(cached,C,'ptCount',val=len(rows))
        for i,row in enumerate(rows):node(node(cached,C,'pt',idx=i),C,'v',row[field])
    labels=node(pie,C,'dLbls')
    for key,val in [('showLegendKey',0),('showVal',0),('showCatName',0),('showPercent',1),('showLeaderLines',1)]:node(labels,C,key,val=val)
    legend=node(chart,C,'legend');node(legend,C,'legendPos',val='b');node(legend,C,'overlay',val=0)
    node(chart,C,'plotVisOnly',val=1)
    drawing=Element('{'+X+'}wsDr');anchor=node(drawing,X,'twoCellAnchor')
    for part,col,row in [('from',5,5),('to',16,29)]:
        marker=node(anchor,X,part)
        for key,value in [('col',col),('colOff',0),('row',row),('rowOff',0)]:node(marker,X,key,value)
    frame=node(anchor,X,'graphicFrame',macro=''); props=node(frame,X,'nvGraphicFramePr')
    node(props,X,'cNvPr',id=index,name='Inventory pie chart');node(props,X,'cNvGraphicFramePr')
    transform=node(frame,X,'xfrm');node(transform,A,'off',x=0,y=0);node(transform,A,'ext',cx=0,cy=0)
    data=node(node(frame,A,'graphic'),A,'graphicData',uri=C)
    SubElement(data,'{'+C+'}chart',{'{'+OFFICE+'}id':'rId1'})
    node(anchor,X,'clientData')
    def relation(kind,target):
        ns='http://schemas.openxmlformats.org/package/2006/relationships'
        rel=Element('{'+ns+'}Relationships')
        node(rel,ns,'Relationship',Id='rId1',Type=OFFICE+'/'+kind,Target=target)
        return tostring(rel,encoding='utf-8',xml_declaration=True)
    return {
        f'xl/charts/chart{index}.xml':tostring(root,encoding='utf-8',xml_declaration=True),
        f'xl/drawings/drawing{index}.xml':tostring(drawing,encoding='utf-8',xml_declaration=True),
        f'xl/drawings/_rels/drawing{index}.xml.rels':relation('chart',f'../charts/chart{index}.xml'),
        f'xl/worksheets/_rels/sheet{index}.xml.rels':relation('drawing',f'../drawings/drawing{index}.xml'),
    }
