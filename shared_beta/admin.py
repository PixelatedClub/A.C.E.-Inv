"""Explicit database provisioning and reconciled import into empty Azure SQL."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from .sql_store import SQLStore,azure_engine
from .store import Store


TABLES=('items','cadets','fittings','issues','legacy_barcodes','legacy_archive','audit','receipts')


def import_sql(store,source):
    from sqlalchemy import text
    source=Path(source).resolve()
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Import database is damaged.')
        rows={table:[dict(r) for r in db.execute('SELECT * FROM '+table)] for table in TABLES}
        revision=db.execute('SELECT revision FROM beta_meta WHERE id=1').fetchone()[0]
        expected=Store._state(store,db)
    with closing(store.connect()) as target,target:
        target.execute('BEGIN IMMEDIATE')
        for table in TABLES:
            if target.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]:raise ValueError('Destination must be empty.')
        for table in TABLES:
            identity=table in ('items','cadets','issues')
            if identity:target.execute('SET IDENTITY_INSERT '+table+' ON')
            for row in rows[table]:
                cols=list(row)
                target.execute('INSERT INTO '+table+' ('+','.join('['+k.replace(']',']]')+']' for k in cols)+') VALUES ('+','.join('?' for _ in cols)+')',tuple(row.values()))
            if identity:target.execute('SET IDENTITY_INSERT '+table+' OFF')
        target.execute('UPDATE beta_meta SET revision=? WHERE id=1',(revision,))
        actual=store._state(target)
        # SQL collation may order text differently. Compare records by stable identity.
        for group in ('items','cadets','fittings','issues'):
            if sorted(map(str,actual[group]))!=sorted(map(str,expected[group])):
                # Dictionary insertion order differs between SQL drivers; canonicalize it.
                import json
                if sorted(json.dumps(r,sort_keys=True) for r in actual[group])!=sorted(json.dumps(r,sort_keys=True) for r in expected[group]):
                    raise ValueError('SQL reconciliation failed for '+group)
    return {'revision':revision,'rows':{table:len(value) for table,value in rows.items()}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--init-schema',action='store_true')
    parser.add_argument('--import-reconciled',type=Path)
    args=parser.parse_args()
    store=SQLStore(azure_engine(os.environ['ACE_SQL_ODBC']))
    if args.init_schema:store.initialize_schema();print('Created beta SQL schema.')
    if args.import_reconciled:print(import_sql(store,args.import_reconciled))


if __name__=='__main__':main()
