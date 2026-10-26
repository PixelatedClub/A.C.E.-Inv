"""Read-only legacy preview and explicit import into a NEW isolated beta database."""
import argparse
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone
from pathlib import Path

from .store import Store


def inspect(source):
    source=Path(source).resolve()
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Source database failed integrity check.')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not {'items','cadets','transactions','cadet_size_entries'}<=tables:
            raise ValueError('Not a supported A.C.E. inventory database.')
        # Retain non-secret legacy records, including original transaction and audit details.
        archive={table:[dict(row) for row in db.execute('SELECT * FROM "'+table.replace('"','""')+'"')]
                 for table in sorted(tables-{'admin_codes'})}
    issues=[];errors=[]
    items=archive['items'];cadets=archive['cadets'];transactions=archive['transactions']
    item_ids={row['barcode_id']:i+1 for i,row in enumerate(items)}
    cadet_ids={row['cadet_id'] for row in cadets}
    seen_items=set();seen_emails=set()
    for row in items:
        key=tuple(str(row[k]).strip().casefold() for k in ('item_name','category','variant'))
        if key in seen_items:errors.append('Items with the same name/category/size require item-type review before migration.')
        seen_items.add(key)
        if not str(row.get('wings_item_no') or '').strip():errors.append('An item is missing its WINGS/local number.')
        if row['status'] not in ('Available','Checked Out','Retired','Lost'):errors.append('Unrecognized item status requires review.')
    for row in cadets:
        email=row['email'].strip().casefold()
        if not email or email in seen_emails:errors.append('Missing or duplicate cadet email requires review.')
        seen_emails.add(email)
    for row in transactions:
        if row['barcode_id'] not in item_ids or row['cadet_id'] not in cadet_ids:
            errors.append('Transaction references a missing item or cadet.');continue
        disposition=row.get('disposition','') or ''
        if row.get('return_time'):
            mapping={'Returned':'returned','Acquired / Permanent Issue':'acquired','Purchased':'purchased','':'returned'}
            if disposition not in mapping:
                errors.append('Unrecognized closed transaction disposition.');continue
            state=mapping[disposition];due=''
        else:
            if disposition in ('Acquired / Permanent Issue','Purchased'):
                errors.append('Permanent issue is missing a close timestamp.');continue
            due=row.get('loan_due_date','') or ''
            state='loan' if due else 'checkout'
            if due:
                try:date.fromisoformat(due)
                except ValueError:errors.append('Loan has an invalid return deadline.')
        issues.append(dict(id=row['transaction_id'],cadet=row['cadet_id'],item=item_ids[row['barcode_id']],quantity=1,state=state,due=due))
    opened=Counter()
    for issue in issues:
        if issue['state'] in ('loan','checkout'):opened[issue['item']]+=issue['quantity']
    for row in items:
        expected=row['total_quantity']-opened[item_ids[row['barcode_id']]]
        if row['status'] in ('Retired','Lost'):expected=0
        if expected<0 or expected!=row['available_quantity']:
            errors.append('Item total, availability, and open issue count do not reconcile.')
    fittings=[];seen_fit=set()
    for row in archive['cadet_size_entries']:
        # Preserve individual size labels so several sizes in one uniform category cannot overwrite each other.
        label=' / '.join(filter(None,[row.get('category','').strip(),row['size_label'].strip()]))
        key=(row['cadet_id'],label.casefold())
        if row['cadet_id'] not in cadet_ids or key in seen_fit or len(label)>200:
            errors.append('Fitting record needs review.');continue
        seen_fit.add(key);fittings.append(dict(cadet=row['cadet_id'],category=label,size=row['size_value']))
    report=dict(items=len(items),cadets=len(cadets),transactions=len(transactions),fittings=len(fittings),
                total_units=sum(r['total_quantity'] for r in items),available_units=sum(r['available_quantity'] for r in items),
                open_units=sum(opened.values()),errors=dict(Counter(errors)),ready=not errors,
                admin_secrets_excluded=True,archive_tables={k:len(v) for k,v in archive.items()})
    return report,archive,item_ids,issues,fittings


def migrate(source,target):
    target=Path(target).resolve()
    if target.exists():raise ValueError('Destination already exists; migration never overwrites a database.')
    report,archive,item_ids,issues,fittings=inspect(source)
    if not report['ready']:raise ValueError('Migration blocked: '+json.dumps(report['errors']))
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as folder:
        stage=Path(folder)/'migration.sqlite3';store=Store(stage)
        with closing(store.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            for row in archive['items']:
                ident=item_ids[row['barcode_id']]
                status=row['status'].lower() if row['status'] in ('Retired','Lost') else 'active'
                db.execute('INSERT INTO items(id,name,category,size,wings,total,status) VALUES(?,?,?,?,?,?,?)',(ident,row['item_name'],row['category'],row['variant'],row['wings_item_no'],row['total_quantity'],status))
                db.execute('INSERT INTO legacy_barcodes VALUES(?,?)',(ident,row['barcode_id']))
            for row in archive['cadets']:
                db.execute('INSERT INTO cadets VALUES(?,?,?)',(row['cadet_id'],row['full_name'],row['email'].strip().casefold()))
            for row in issues:
                db.execute('INSERT INTO issues VALUES(?,?,?,?,?,?)',tuple(row[k] for k in ('id','cadet','item','quantity','state','due')))
            for row in fittings:db.execute('INSERT INTO fittings VALUES(?,?,?)',tuple(row.values()))
            for table,rows in archive.items():
                for i,row in enumerate(rows):db.execute('INSERT INTO legacy_archive VALUES(?,?,?)',(table,i,json.dumps(row)))
            db.execute('UPDATE beta_meta SET revision=1')
            db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?,?)',(1,datetime.now(timezone.utc).isoformat(),'Migration tool',
                'legacy_import','migration-initial',json.dumps(dict(revision=0,items=[],cadets=[],issues=[],fittings=[])),json.dumps(store._state(db))))
        state=store.snapshot()
        if sum(r['available'] for r in state['items'])!=report['available_units']:raise ValueError('Post-import availability check failed.')
        # Exclusive creation also protects against a competing migration choosing the same target.
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
        store.backup(target)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--apply-to-new',type=Path)
    args=parser.parse_args()
    result=migrate(args.source,args.apply_to_new) if args.apply_to_new else inspect(args.source)[0]
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
