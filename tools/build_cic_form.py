"""Prepare a Word source for Microsoft Forms Quick Import (no private data)."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inventory_app.cic_sharepoint import FIELDS, FAMILIES
from inventory_app.cic_questions import QUESTIONS


def build(path):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    doc=Document();section=doc.sections[0]
    section.page_width=Inches(8.5);section.page_height=Inches(11)
    section.top_margin=section.bottom_margin=Inches(.7)
    style=doc.styles['Normal'];style.font.name='Arial';style.font.size=Pt(11)
    style.paragraph_format.space_after=Pt(8)
    for key in ['Title','Heading 1','Heading 2']:
        doc.styles[key].font.color.rgb=RGBColor(0,0,0)
    doc.add_paragraph('Det 005 Cadet Inventory Card',style='Title')
    doc.add_paragraph('Report the uniform items you currently possess, including quantities and label sizes. Records are visible to the Det 005 Cadet Wing group.')
    ordered=[(k,label,[]) for k,label in FIELDS[:4]]
    for family_key,family in FAMILIES:
        ordered.append((family_key+'.has_items',f'Do you currently possess any {family} items?',['Yes','No']))
        for key,fam,label in QUESTIONS:
            if fam!=family:continue
            ordered.append((key+'.has_item',f'Do you possess any {family} {label}?',['Yes','No']))
            ordered.append((key+'.count',f'{family} {label} quantity',[]))
            ordered.append((key+'.sizes',f'{family} {label} sizes and exact types',[]))
    for i,(key,label,options) in enumerate(ordered,1):
        p=doc.add_paragraph(f'{i}. [{key}] {label}');p.paragraph_format.space_after=Pt(12)
        p.paragraph_format.keep_with_next=bool(options)
        for j,(letter,option) in enumerate(zip('ABCDEFGHIJKL',options)):
            p=doc.add_paragraph(f'{letter}. {option}')
            p.paragraph_format.space_after=Pt(2)
            p.paragraph_format.keep_with_next=j<len(options)-1
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);doc.save(path)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');args=p.parse_args();build(args.output)
