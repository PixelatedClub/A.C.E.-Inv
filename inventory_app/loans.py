"""Loan deadlines share the original checkout records and return lifecycle."""
from datetime import date, timedelta
import json

from .database import utc_now


class LoanServiceMixin:
    @staticmethod
    def validate_loan_date(value, earliest=None):
        from .services import InventoryError
        try:
            parsed = date.fromisoformat(value.strip())
        except (ValueError, AttributeError):
            raise InventoryError('Enter a valid due date as YYYY-MM-DD.')
        if earliest and parsed < earliest:
            raise InventoryError(f'Due date cannot be earlier than {earliest.isoformat()}.')
        return parsed.isoformat()

    @staticmethod
    def _loan_event(connection, transaction_id, action, details, actor):
        connection.execute(
            'INSERT INTO loan_events(event_time,transaction_id,action,details,recorded_by) VALUES(?,?,?,?,?)',
            (utc_now(), transaction_id, action, details, actor),
        )

    def list_loans(self, search='', include_closed=False, today=None):
        today = today or date.today()
        with self.database.connect() as connection:
            rows = connection.execute('''SELECT t.*, i.item_name, i.variant, i.wings_item_no
                FROM transactions t JOIN items i ON i.barcode_id=t.barcode_id
                WHERE t.loan_due_date <> '' ORDER BY t.loan_due_date,t.cadet_name,t.transaction_id''').fetchall()
        result = []
        for row in rows:
            row = dict(row)
            if row['return_time'] and not include_closed:
                continue
            if search.casefold() not in ' '.join(str(v or '') for v in row.values()).casefold():
                continue
            remaining = (date.fromisoformat(row['loan_due_date']) - today).days
            row['loan_status'] = (row['disposition'] or 'Returned') if row['return_time'] else (
                f'OVERDUE {abs(remaining)} days' if remaining < 0 else 'Due today' if remaining == 0 else f'Due in {remaining} days')
            row['overdue'] = not row['return_time'] and remaining < 0
            result.append(row)
        return result

    def set_loan_deadline(self, transaction_ids, due_date, purpose, approved_by):
        from .services import InventoryError
        due_date = self.validate_loan_date(due_date)
        actor = self._normalize_admin_identity(approved_by)['label']
        ids = sorted(set(int(v) for v in transaction_ids))
        if not ids:
            raise InventoryError('Select at least one open checkout.')
        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            for tid in ids:
                row = connection.execute('SELECT * FROM transactions WHERE transaction_id=?', (tid,)).fetchone()
                if row is None or row['return_time'] or row['disposition'] in ('Purchased', 'Acquired / Permanent Issue'):
                    raise InventoryError(f'Checkout {tid} is closed or permanently issued.')
                self.validate_loan_date(due_date, earliest=date.fromisoformat(row['checkout_time'][:10]))
                connection.execute('UPDATE transactions SET loan_due_date=?,loan_purpose=? WHERE transaction_id=?',
                                   (due_date, purpose.strip(), tid))
                self._loan_event(connection, tid, 'Loan deadline assigned',
                                 f"Previous due: {row['loan_due_date'] or 'none'}; new due: {due_date}; {purpose.strip()}", actor)
            connection.commit()
        self.database.note_write()
        return len(ids)

    def convert_loans_to_standard_checkout(self, transaction_ids, approved_by):
        """Remove loan deadlines while preserving the original open checkout records."""
        from .services import InventoryError

        actor = self._normalize_admin_identity(approved_by)['label']
        ids = sorted(set(int(value) for value in transaction_ids))
        if not ids:
            raise InventoryError('Select at least one active loan.')

        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            rows = []
            for transaction_id in ids:
                row = connection.execute(
                    'SELECT * FROM transactions WHERE transaction_id=?',
                    (transaction_id,),
                ).fetchone()
                if row is None or row['return_time'] is not None:
                    raise InventoryError(f'Loan {transaction_id} is closed or no longer exists.')
                if not str(row['loan_due_date'] or '').strip():
                    raise InventoryError(f'Checkout {transaction_id} is not an active loan.')
                rows.append(row)

            for row in rows:
                old_due = str(row['loan_due_date'] or '').strip()
                old_purpose = str(row['loan_purpose'] or '').strip()
                connection.execute(
                    "UPDATE transactions SET loan_due_date='', loan_purpose='' WHERE transaction_id=?",
                    (row['transaction_id'],),
                )
                details = f'Previous due: {old_due}'
                if old_purpose:
                    details += f'; previous purpose: {old_purpose}'
                self._loan_event(
                    connection,
                    row['transaction_id'],
                    'Converted to standard checkout',
                    details,
                    actor,
                )
            connection.commit()

        self.database.note_write()
        return len(rows)

    def merge_cadet_profiles(self, keep_id, duplicate_id, approved_by):
        from .services import InventoryError
        actor = self._normalize_admin_identity(approved_by)['label']
        if keep_id == duplicate_id:
            raise InventoryError('Choose two different profiles.')
        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            keep = connection.execute('SELECT * FROM cadets WHERE cadet_id=?', (keep_id,)).fetchone()
            duplicate = connection.execute('SELECT * FROM cadets WHERE cadet_id=?', (duplicate_id,)).fetchone()
            if not keep or not duplicate:
                raise InventoryError('Both profiles must exist.')
            sizes = connection.execute('SELECT * FROM cadet_size_entries WHERE cadet_id=?', (duplicate_id,)).fetchall()
            conflicts = []
            for size in sizes:
                existing = connection.execute('SELECT * FROM cadet_size_entries WHERE cadet_id=? AND size_label=? COLLATE NOCASE',
                                              (keep_id, size['size_label'])).fetchone()
                if existing and any(existing[k] != size[k] for k in ('size_value', 'category', 'catalog_item_no', 'notes')):
                    conflicts.append(size['size_label'])
            if conflicts:
                raise InventoryError('Resolve conflicting fittings before merging: ' + ', '.join(conflicts))
            snapshot = {'retained': dict(keep), 'merged': dict(duplicate), 'fittings': [dict(s) for s in sizes]}
            for size in sizes:
                existing = connection.execute('SELECT 1 FROM cadet_size_entries WHERE cadet_id=? AND size_label=? COLLATE NOCASE',
                                              (keep_id, size['size_label'])).fetchone()
                if existing:
                    connection.execute('DELETE FROM cadet_size_entries WHERE size_entry_id=?', (size['size_entry_id'],))
                else:
                    connection.execute('UPDATE cadet_size_entries SET cadet_id=? WHERE size_entry_id=?', (keep_id, size['size_entry_id']))
            connection.execute('UPDATE transactions SET cadet_id=?,cadet_name=?,cadet_email=? WHERE cadet_id=?',
                               (keep_id, keep['full_name'], keep['email'], duplicate_id))
            connection.execute('DELETE FROM cadets WHERE cadet_id=?', (duplicate_id,))
            self._loan_event(connection, None, 'Cadet profiles merged', json.dumps(snapshot), actor)
            connection.commit()
        self.database.note_write()

    def export_monday_report(self, monday=None):
        """Generate the standard browser report for the previous Monday-Sunday period."""
        monday = monday or (date.today() - timedelta(days=date.today().weekday()))
        start, end = monday - timedelta(days=7), monday - timedelta(days=1)
        return self.export_activity_html(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            open_after=False,
            filename_stem=f"ACE_Monday_Report_{monday.isoformat()}",
        )
