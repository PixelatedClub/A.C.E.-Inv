"""Loan deadlines share the original checkout records and return lifecycle."""
from datetime import date, timedelta
from html import escape
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
        """Printable weekly report; current loan status is explicitly distinguished."""
        from pathlib import Path
        monday = monday or (date.today() - timedelta(days=date.today().weekday()))
        start, end = monday - timedelta(days=7), monday - timedelta(days=1)
        with self.database.connect() as connection:
            issues = [dict(r) for r in connection.execute('''SELECT t.*,i.item_name,i.variant FROM transactions t
                JOIN items i ON i.barcode_id=t.barcode_id WHERE substr(t.checkout_time,1,10) BETWEEN ? AND ?
                ORDER BY t.checkout_time,t.transaction_id''', (str(start),str(end)))]
            changes = [dict(r) for r in connection.execute('SELECT * FROM inventory_changes WHERE substr(event_time,1,10) BETWEEN ? AND ? ORDER BY event_time,change_id', (str(start),str(end)))]
            returns = connection.execute('SELECT COUNT(*) FROM transactions WHERE substr(return_time,1,10) BETWEEN ? AND ? AND disposition NOT IN (?,?)',
                                        (str(start), str(end), 'Purchased', 'Acquired / Permanent Issue')).fetchone()[0]
            fittings = connection.execute('SELECT COUNT(*) FROM cadet_size_entries WHERE substr(updated_at,1,10) BETWEEN ? AND ?', (str(start),str(end))).fetchone()[0]
        loans = self.list_loans()
        def table(rows, fields):
            if not rows:
                return '<p>None recorded.</p>'
            return '<table><thead><tr>' + ''.join('<th>'+escape(label)+'</th>' for key,label in fields) + '</tr></thead><tbody>' + ''.join(
                '<tr>'+''.join('<td>'+escape(str(row.get(key,'') or ''))+'</td>' for key,label in fields)+'</tr>' for row in rows)+'</tbody></table>'
        overdue = sum(bool(r['overdue']) for r in loans)
        permanent = sum(r['disposition'] in ('Purchased','Acquired / Permanent Issue') for r in issues)
        html = f'''<!doctype html><html><head><meta charset="utf-8"><title>A.C.E. Monday Report {monday}</title>
        <style>body{{font:14px Arial;color:#162a43;max-width:1100px;margin:32px auto;line-height:1.5}}h1,h2{{color:#03244d}}table{{border-collapse:collapse;width:100%;font-size:12px;margin:16px 0}}th{{background:#03244d;color:white;text-align:left}}td,th{{padding:7px;border-bottom:1px solid #cdd8e3}}tr:nth-child(even){{background:#f0f4f8}}thead{{display:table-header-group}}tr{{break-inside:avoid}}@media print{{body{{margin:0}}}}</style></head><body>
        <h1>A.C.E. Monday Morning Report — {monday}</h1><p>Reporting period: {start} through {end}. Generated {date.today()}.</p>
        <h2>BLUF</h2><p>{len(issues)} units checked out to {len(set(r['cadet_id'] for r in issues))} cadets during the week; {permanent} of those units have permanent-issue/purchase dispositions. {returns} returns recorded. Current loan register: {len(loans)} outstanding units, {overdue} overdue.</p>
        <h2>Major activities</h2><p>{len(changes)} inventory changes recorded; {fittings} fitting entries last updated during the reporting period. Loan classification and profile corrections performed after the period are reflected in the current register below.</p>
        <h2>Current loans — status as of {date.today()}</h2>'''
        html += table(loans, [('cadet_name','Cadet'),('item_name','Item'),('variant','Size'),('barcode_id','Barcode'),('loan_due_date','Due'),('loan_status','Status')])
        html += '<h2>Checkout detail for the reporting period</h2>' + table(issues,[('checkout_time','Checked out'),('cadet_name','Cadet'),('item_name','Item'),('variant','Size'),('disposition','Disposition'),('loan_due_date','Loan due')])
        html += '<h2>Inventory change detail</h2>' + table(changes,[('event_time','Date'),('item_name','Item'),('variant','Size'),('quantity_change','Change'),('total_after','New total'),('source','Recorded by')])
        html += '<h2>COA / validation</h2><p>Reconcile outstanding loans against physical returns. Follow up on overdue entries and review approaching deadlines. This report describes recorded activity; it does not certify a physical count.</p></body></html>'
        destination = self.settings.database_path.parent / 'exports' / f'ACE_Monday_Report_{monday}.html'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html, encoding='utf-8')
        return destination
