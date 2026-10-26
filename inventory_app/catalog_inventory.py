"""Zero-stock catalog inventory and a separate record of counting progress."""
from datetime import datetime

COUNT_SCHEMA='''
CREATE TABLE IF NOT EXISTS inventory_count_state (
    barcode_id TEXT PRIMARY KEY REFERENCES items(barcode_id) ON DELETE CASCADE,
    counted_at TEXT NOT NULL,
    count_source TEXT NOT NULL,
    last_count_total INTEGER NOT NULL,
    last_count_available INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trg_count_stock_insert AFTER INSERT ON items
WHEN NEW.total_quantity>0 BEGIN
 INSERT OR REPLACE INTO inventory_count_state VALUES(NEW.barcode_id,NEW.updated_at,'Stock recorded',NEW.total_quantity,NEW.available_quantity);
END;
CREATE TRIGGER IF NOT EXISTS trg_count_stock_update AFTER UPDATE OF total_quantity ON items
WHEN NEW.total_quantity<>OLD.total_quantity BEGIN
 INSERT OR REPLACE INTO inventory_count_state VALUES(NEW.barcode_id,NEW.updated_at,'Stock recorded',NEW.total_quantity,NEW.available_quantity);
END;
'''

def item_key(value):
    value=str(value or '').strip()
    return str(int(value)) if value.isdigit() else value.casefold()

class CatalogInventoryMixin:
    def enable_catalog_inventory(self):
        self.catalog_inventory_enabled=True
        return self.ensure_catalog_inventory()

    def ensure_catalog_inventory(self, item_nos=None):
        from .services import ONE_SIZE_VARIANT
        catalog=self.list_wings_catalog()
        if item_nos is not None:
            wanted={item_key(no) for no in item_nos}
            catalog=[row for row in catalog if item_key(row['item_no']) in wanted]
        now=datetime.now().astimezone().isoformat(timespec='seconds')
        created=[]
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('''INSERT OR IGNORE INTO inventory_count_state
                SELECT i.barcode_id,i.updated_at,'Existing inventory history',i.total_quantity,i.available_quantity
                FROM items i WHERE i.total_quantity>0 OR EXISTS(
                    SELECT 1 FROM transactions t WHERE t.barcode_id=i.barcode_id)
                    OR EXISTS(SELECT 1 FROM inventory_changes a WHERE a.barcode_id=i.barcode_id AND a.quantity_change<>0)''')
            present={item_key(row[0]) for row in c.execute('SELECT wings_item_no FROM items') if row[0]}
            used={str(row[0]).upper() for row in c.execute('SELECT barcode_id FROM items UNION SELECT alias_barcode_id FROM barcode_aliases')}
            number=1
            for row in catalog:
                if item_key(row['item_no']) in present:continue
                while f'A{number:07d}' in used:number+=1
                barcode=f'A{number:07d}';used.add(barcode);number+=1
                last=c.execute('SELECT COALESCE(MAX(change_id),0) FROM inventory_changes').fetchone()[0]
                c.execute('''INSERT INTO items(barcode_id,wings_item_no,item_name,category,variant,item_type,status,notes,
                    total_quantity,available_quantity,created_at,updated_at) VALUES(?,?,?,?,?,?,'Available','',0,0,?,?)''',
                    (barcode,row['item_no'],row['item_name'],row['category'].upper(),
                     row['size'] or ONE_SIZE_VARIANT,(row['subcategory'] or row['item_name']).upper(),now,now))
                c.execute('''UPDATE inventory_changes SET action='Catalog Baseline Created',details=?,source='Admin code 3 - Williams'
                    WHERE change_id>? AND barcode_id=?''',
                    ('Catalog item added at zero stock. Physical inventory has not been counted yet.',last,barcode))
                present.add(item_key(row['item_no']));created.append(barcode)
            c.commit()
        if created:self.database.note_write()
        return {'created':len(created),'barcodes':created}

    def record_available_count(self, *, barcode_id, available_quantity, approved_by=None, notes=''):
        from .services import InventoryError
        available=self._validate_quantity(available_quantity,field_name='Available physical count',allow_zero=True)
        source='Admin code 3 - Williams'
        if approved_by:
            actor=self._normalize_admin_identity(approved_by)
            source=f"Admin code {actor['admin_id']} - {actor['approved_by_name']}" if actor['admin_id'] else actor['label']
        now=datetime.now().astimezone().isoformat(timespec='seconds')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            barcode=self._resolve_barcode_alias(c,barcode_id.strip().upper())
            old=c.execute('SELECT * FROM items WHERE barcode_id=?',(barcode,)).fetchone()
            if old is None:raise InventoryError('Select an inventory item to count.')
            if old['status'] in ('Lost','Retired'):raise InventoryError('Reactivate a lost or retired item before recording a count.')
            held=self._open_checkout_count(c,barcode)
            total=available+held
            last=c.execute('SELECT COALESCE(MAX(change_id),0) FROM inventory_changes').fetchone()[0]
            c.execute('''UPDATE items SET total_quantity=?,available_quantity=?,updated_at=? WHERE barcode_id=?''',
                (total,available,now,barcode))
            self._sync_item_state(c,barcode)
            detail=f'Physical count recorded: {available} available, {held} checked out, {total} total.'
            if notes.strip():detail+=' '+notes.strip()
            audit=c.execute('SELECT change_id FROM inventory_changes WHERE change_id>? AND barcode_id=?',(last,barcode)).fetchone()
            if audit:
                c.execute("UPDATE inventory_changes SET action='Inventory Count Recorded',details=?,source=? WHERE change_id=?",
                    (detail,source,audit['change_id']))
            else:
                c.execute('''INSERT INTO inventory_changes(event_time,action,barcode_id,wings_item_no,item_name,category,variant,item_type,
                    quantity_change,total_before,total_after,available_before,available_after,details,source)
                    VALUES(?,'Inventory Count Recorded',?,?,?,?,?,?,0,?,?,?,?,?,?)''',
                    (now,barcode,old['wings_item_no'] or '',old['item_name'],old['category'],old['variant'],old['item_type'],
                     old['total_quantity'],total,old['available_quantity'],available,detail,source))
            c.execute('INSERT OR REPLACE INTO inventory_count_state VALUES(?,?,?,?,?)',
                (barcode,now,source,total,available));c.commit()
        self.database.note_write()
        from .item_metadata import enrich_items
        return enrich_items(self,[self.get_item(barcode)])[0]
