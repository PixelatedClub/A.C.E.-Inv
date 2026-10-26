"""Restore a permanent issue to its original open checkout, with an audit trail."""
import json
import sqlite3
import zipfile
import tempfile
from pathlib import Path
from contextlib import closing
from collections import Counter
from datetime import datetime

from .database import utc_now

DISPOSITIONS=('Acquired / Permanent Issue','Purchased')

class AcquisitionUndoMixin:
    def latest_acquisition(self, cadet_id):
        with self.database.connect() as c:
            row=c.execute('''SELECT * FROM transactions WHERE cadet_id=?
                AND disposition IN (?,?) AND return_time IS NOT NULL
                ORDER BY return_time DESC,transaction_id DESC LIMIT 1''',
                (int(cadet_id),*DISPOSITIONS)).fetchone()
            if row is None:
                return None
            actions=c.execute('''SELECT after_json FROM acquisition_actions WHERE cadet_id=?
                AND created_at=? AND undone_at='' ORDER BY action_id DESC''',
                (int(cadet_id),row['return_time'])).fetchall()
            selected_ids=None
            if actions:
                ids=[r['transaction_id'] for r in json.loads(actions[0]['after_json'])]
                selected_ids=set(ids)
                row=c.execute('SELECT * FROM transactions WHERE transaction_id=?',(ids[0],)).fetchone()
            batch=[dict(r) for r in c.execute('''SELECT t.*,i.item_name,i.variant
                FROM transactions t JOIN items i ON i.barcode_id=t.barcode_id
                WHERE t.cadet_id=? AND t.return_time=? AND t.disposition=?
                ORDER BY t.transaction_id''',(row['cadet_id'],row['return_time'],row['disposition']))]
            if selected_ids is not None:
                batch=[r for r in batch if r['transaction_id'] in selected_ids]
            return {'cadet_id':int(cadet_id),'cadet_name':row['cadet_name'],
                    'closed_at':row['return_time'],'disposition':row['disposition'],
                    'transaction_ids':[r['transaction_id'] for r in batch],'items':batch}

    def _acquisition_snapshot(self,c,batch):
        from .services import InventoryError
        ids=[r['transaction_id'] for r in batch]
        candidates=c.execute('''SELECT * FROM acquisition_actions WHERE cadet_id=?
            AND created_at=? AND undone_at='' ORDER BY action_id DESC''',
            (batch[0]['cadet_id'],batch[0]['return_time'])).fetchall()
        action=next((a for a in candidates if [r['transaction_id'] for r in json.loads(a['after_json'])]==ids),None)
        if action:
            before=json.loads(action['before_json']);after=json.loads(action['after_json'])
            if [r['transaction_id'] for r in after]!=ids or after!=batch:
                raise InventoryError('These acquisition records changed after they were saved. Undo was not applied.')
            return before,json.loads(action['item_notes_json']),action['action_id']
        # Older builds created a backup immediately before each acquisition.
        stamp=datetime.fromisoformat(batch[0]['return_time']).strftime('%Y%m%d_%H%M%S')
        for path in sorted(self.settings.backup_dir.glob(f'inventory_pre_acquisition_{stamp}_*.zip'),reverse=True):
            try:
                with zipfile.ZipFile(path) as z:
                    data=z.read('inventory.db')
                # SQLite backup files can carry WAL headers; open a temporary
                # file so SQLite can read them without an in-memory WAL VFS.
                with tempfile.TemporaryDirectory(prefix='ace-acquisition-undo-') as directory:
                    snapshot=Path(directory)/'inventory.db'
                    snapshot.write_bytes(data)
                    with closing(sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True)) as old:
                        return self._legacy_snapshot_rows(old,c,batch)
            except (sqlite3.Error,zipfile.BadZipFile,KeyError,OSError,InventoryError):
                continue
        raise InventoryError('The original acquisition snapshot is unavailable. Restore this action from its pre-acquisition backup before changing stock.')

    @staticmethod
    def _legacy_snapshot_rows(old,c,batch):
        from .services import InventoryError
        old.row_factory=sqlite3.Row
        before=[];notes={}
        units=Counter(r['barcode_id'] for r in batch)
        timestamp=datetime.fromisoformat(batch[0]['return_time']).strftime('%Y-%m-%d %H:%M')
        for current in batch:
            previous=old.execute('SELECT * FROM transactions WHERE transaction_id=?',(current['transaction_id'],)).fetchone()
            if previous is None or previous['return_time'] is not None:
                break
            prior=dict(previous)
            if any(prior[k]!=current[k] for k in ('cadet_id','barcode_id','checkout_time','cadet_email')):
                break
            before.append(prior)
            barcode=prior['barcode_id']
            item=old.execute('SELECT notes FROM items WHERE barcode_id=?',(barcode,)).fetchone()
            original=(item['notes'] or '').strip()
            latest=c.execute('SELECT notes FROM items WHERE barcode_id=?',(barcode,)).fetchone()['notes'] or ''
            prefix=f"[{timestamp}] {units[barcode]} unit(s) removed as {current['disposition']} for "
            addition=next((line for line in latest.splitlines() if line.startswith(prefix)),'')
            # Only remove the acquisition note when it is the sole addition.
            notes[barcode]={'before':original,'after':(original+'\n'+addition).strip()}
        if len(before)==len(batch):
            return before,notes,None
        raise InventoryError('The pre-acquisition backup does not match these checkout records.')

    def undo_latest_acquisition(self, *, cadet_id, approved_by=None, expected_transaction_ids=None):
        from .services import InventoryError
        approval=self._normalize_admin_identity(approved_by)
        preview=self.latest_acquisition(cadet_id)
        if preview is None:
            raise InventoryError('This cadet has no acquired or purchased items to undo.')
        if expected_transaction_ids is not None and sorted(expected_transaction_ids)!=preview['transaction_ids']:
            raise InventoryError('The latest acquisition changed. Review it again before undoing.')
        self.database.create_backup(reason='pre_acquisition_undo')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            ids=preview['transaction_ids'];marks=','.join('?' for _ in ids)
            batch=[dict(r) for r in c.execute(f'SELECT * FROM transactions WHERE transaction_id IN ({marks}) ORDER BY transaction_id',ids)]
            if len(batch)!=len(ids) or any(r['return_time']!=preview['closed_at'] or r['disposition']!=preview['disposition'] for r in batch):
                raise InventoryError('The acquisition changed. Undo was not applied.')
            before,notes,action_id=self._acquisition_snapshot(c,batch)
            units=Counter(r['barcode_id'] for r in batch)
            for barcode in units:
                item=c.execute('SELECT * FROM items WHERE barcode_id=?',(barcode,)).fetchone()
                if item is None or item['status'] in ('Lost','Retired'):
                    raise InventoryError('An affected item is missing, lost or retired. Undo was not applied.')
            now=utc_now()
            for row in before:
                if row['return_time'] is not None:
                    raise InventoryError('The original record was not an open checkout.')
                c.execute('''UPDATE transactions SET return_time=?,return_approved_by_admin_id=?,
                    return_approved_by_name=?,return_approved_by_role=?,return_approved_at=?,
                    disposition=?,condition_notes=? WHERE transaction_id=?''',
                    tuple(row[k] for k in ('return_time','return_approved_by_admin_id','return_approved_by_name',
                        'return_approved_by_role','return_approved_at','disposition','condition_notes','transaction_id')))
                self._loan_event(c,row['transaction_id'],'Acquisition undone',
                    f"Reopened original checkout. Previous disposition: {preview['disposition']}; closed {preview['closed_at']}.",approval['label'])
            for barcode,count in units.items():
                last=c.execute('SELECT COALESCE(MAX(change_id),0) FROM inventory_changes').fetchone()[0]
                current=c.execute('SELECT notes FROM items WHERE barcode_id=?',(barcode,)).fetchone()[0] or ''
                record=notes[barcode]
                restored_notes=record['before'] if current==record['after'] else self._append_note(current,'Acquisition undone; original checkout reopened.')
                c.execute('UPDATE items SET total_quantity=total_quantity+?,notes=?,updated_at=? WHERE barcode_id=?',
                    (count,restored_notes,now,barcode))
                self._sync_item_state(c,barcode)
                c.execute('''UPDATE inventory_changes SET action='Acquisition Undone',details=?,source=?
                    WHERE change_id>? AND barcode_id=?''',
                    (f"Restored {count} inventory unit(s) to open checkout for {preview['cadet_name']}. Reversal of {preview['disposition']} at {preview['closed_at']}. Transactions: {ids}.",approval['label'],last,barcode))
            if action_id:
                c.execute('UPDATE acquisition_actions SET undone_at=?,undone_by=? WHERE action_id=?',(now,approval['label'],action_id))
            c.commit()
        self.database.note_write()
        return {'cadet_name':preview['cadet_name'],'transaction_ids':ids,'units':len(ids)}
