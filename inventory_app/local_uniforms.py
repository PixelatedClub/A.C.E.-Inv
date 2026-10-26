"""Conservative local uniform labels. Unknown sex, fabric or width stays explicit."""
import re

BOOT_SIZES=tuple(f'{n/2:g}' for n in range(8,33))
BOOT_WIDTHS=('REGULAR','WIDE')

def boot_size(value):
    text=str(value).strip().upper()
    match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(REGULAR|WIDE|R|W|RF|WF)?',text)
    if not match:return text,None
    size=f'{float(match[1]):g}';width=match[2]
    if width:width='REGULAR' if width.startswith('R') else 'WIDE'
    return size,width

def standard_local(row):
    name=' '.join(row['item_name'].split()).replace('\u2014','-')
    category=row['category'].strip().upper();kind=row['item_type'].strip().upper()
    variant=' '.join(row['variant'].split()).upper()
    sex=row.get('sex') or ''
    text=f'{name} {kind}'.casefold()
    if 'boot' in text or name.casefold()=='bots':
        size,width=boot_size(variant)
        name='OCP Boots' if 'ocp' in text or category=='OCP' else 'Boots'
        name+=", Men's" if sex=='M' else ", Women's" if sex=='F' else ' (sex unspecified)'
        variant=f'{size} {width}' if width else f'{size} (width unspecified)'
        category='FOOTWEAR';kind='BOOTS'
    elif category=='OCP' or 'ocp' in text:
        if 'blouse' in text or 'coat' in text or 'pants' in text or 'trouser' in text:
            garment='Blouse' if 'blouse' in text or 'coat' in text else 'Trousers'
            fabric='Summer' if 'summer' in text or 'ihwcu' in text else 'All Weather' if 'all weather' in text else 'Fabric unspecified'
            name=f'OCP {garment} - {fabric}'
            if sex in ('M','F'):name+=", Men's" if sex=='M' else ", Women's"
            category='SHIRTS' if garment=='Blouse' else 'PANTS/SKIRT';kind='OCP - '+fabric.upper()
            variant=re.sub(r'^([\dA-Z]+)[\s-]*([XSRL]{1,2})$',r'\1-\2',variant)
    else:
        name=name.title().replace("Men'S","Men's").replace("Women'S","Women's").replace('Mens',"Men's").replace('Womens',"Women's")
        for acronym in ('OCP','PTG','AFROTC','IPTU','GMC','US'):
            name=re.sub(r'\b'+acronym+r'\b',acronym,name,flags=re.I)
    return dict(item_name=name,category=category,variant=variant,item_type=kind)
