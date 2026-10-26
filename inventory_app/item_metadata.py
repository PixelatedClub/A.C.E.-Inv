"""Case-insensitive browsing tags and portable item images, separate from WINGS IDs."""
import base64
import json
import re
import unicodedata

from .database import utc_now
from .image_utils import read_png_dimensions

FAMILIES = ('Blues', 'OCP', 'PTG', 'Flight Suit', 'Other', 'Unclassified')
SEASONS = ('Winter', 'Summer', 'All-season', 'Unclassified')


def normalize_tags(values):
    if isinstance(values, str):
        values = values.split(',')
    result = set()
    for value in values:
        tag = ' '.join(unicodedata.normalize('NFKC', str(value)).split()).casefold()
        if tag:
            result.add(tag)
    if len(result) > 40:
        raise ValueError('Use no more than 40 tags per item.')
    return sorted(result)


def infer_family(item):
    text = ' '.join(str(item.get(k) or '') for k in ('category','item_type','item_name')).casefold()
    if re.search(r'\b(ocp|patrol|coyote|rigger)\b', text): return 'OCP'
    if re.search(r'\b(ptg|iptu|ptu|pt|track)\b', text): return 'PTG'
    if 'flight suit' in text: return 'Flight Suit'
    if re.search(r'\b(blues|blue|service dress|service coat|flight cap)\b', text): return 'Blues'
    return 'Unclassified'


def enrich_items(service, rows):
    with service.database.connect() as db:
        metadata = {r['barcode_id']: dict(r) for r in db.execute(
            'SELECT barcode_id,tags_json,family,season FROM item_metadata')}
        counts = {r['barcode_id']: dict(r) for r in db.execute('SELECT * FROM inventory_count_state')}
    for row in rows:
        meta = metadata.get(row['barcode_id'], {})
        count = counts.get(row['barcode_id'], {})
        row['count_status'] = 'Counted' if count or int(row.get('total_quantity') or 0)>0 else 'Not counted'
        row['counted_at'] = count.get('counted_at','')
        row['last_count_available'] = count.get('last_count_available')
        row['family'] = meta.get('family') or infer_family(row)
        row['season'] = meta.get('season') or 'Unclassified'
        row['custom_tags'] = json.loads(meta.get('tags_json') or '[]')
        # Legacy category/type values remain intact. Their search tags are normalized.
        row['tags'] = normalize_tags(row['custom_tags'] + [row.get('category',''), row.get('item_type',''), row['family'], row['season']])
    return rows


def save_metadata(service, barcode, tags, family, season, image_png=None):
    tags = normalize_tags(tags)
    if any(len(tag) > 60 for tag in tags):
        raise ValueError('Each custom tag must be 60 characters or fewer.')
    if family not in ('',) + FAMILIES or season not in SEASONS:
        raise ValueError('Choose a listed uniform family and season.')
    if image_png is not None:
        if image_png:
            raw = base64.b64decode(image_png, validate=True)
            width, height = read_png_dimensions(raw)
            if len(raw) > 2_000_000 or max(width,height) > 4096:
                raise ValueError('Use a PNG up to 2 MB and 4096 pixels per side.')
    with service.database.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        item = db.execute('SELECT * FROM items WHERE barcode_id=?',(barcode,)).fetchone()
        if item is None:
            raise ValueError('The item no longer exists.')
        existing = db.execute('SELECT * FROM item_metadata WHERE barcode_id=?',(barcode,)).fetchone()
        image = image_png if image_png is not None else (existing['image_png'] if existing else '')
        db.execute('''INSERT INTO item_metadata(barcode_id,tags_json,family,season,image_png,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(barcode_id) DO UPDATE SET
            tags_json=excluded.tags_json,family=excluded.family,season=excluded.season,
            image_png=excluded.image_png,updated_at=excluded.updated_at''',
            (barcode,json.dumps(tags),family,season,image,utc_now()))
        db.execute('''INSERT INTO inventory_changes(event_time,action,barcode_id,wings_item_no,
            item_name,category,variant,item_type,quantity_change,total_before,total_after,
            available_before,available_after,details,source) VALUES(?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)''',
            (utc_now(),'Item Tags / Image Updated',barcode,item['wings_item_no'] or '',item['item_name'],
             item['category'],item['variant'],item['item_type'],item['total_quantity'],item['total_quantity'],
             item['available_quantity'],item['available_quantity'],
             'Tags: '+', '.join(tags)+'; family: '+(family or 'Automatic')+'; season: '+season+
             ('; image updated' if image_png is not None else ''),'Admin code 3 - Williams'))
    service.database.note_write()


def inventory_analysis(rows):
    sheets=[]
    for key,title in [('family','Uniform Families'),('season','Uniform Seasons')]:
        groups={}
        for row in rows:
            label=row[key]
            group=groups.setdefault(label, {'Group':label,'Total Units':0,'Available Units':0,'Barcode Rows':0})
            group['Total Units'] += int(row['total_quantity'])
            group['Available Units'] += int(row['available_quantity']) if row['status'] not in ('Lost','Retired') else 0
            group['Barcode Rows'] += 1
        data=[groups[k] for k in sorted(groups)]
        sheets.append({'sheet_name':title,'columns':['Group','Total Units','Available Units','Barcode Rows'],
                       'rows':data,'pie':True,
                       'note':'Current recorded inventory, not weekly receipts. Season is user-assigned; unclassified items are shown explicitly.'})
    return sheets
