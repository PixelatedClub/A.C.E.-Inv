"""Approved, delayed cadet transaction cleanup."""

from collections import Counter
from contextlib import closing
from datetime import date


SCHEMA = """
CREATE TABLE IF NOT EXISTS cadet_graduations (
    cadet_id INTEGER PRIMARY KEY REFERENCES cadets(cadet_id) ON DELETE CASCADE,
    graduation_date TEXT NOT NULL,
    cleanup_date TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    transactions_deleted INTEGER NOT NULL DEFAULT 0,
    units_acquired INTEGER NOT NULL DEFAULT 0
);
"""


def graduation_dates(value, *, already_graduated, today=None):
    from .services import InventoryError

    try:
        graduated = date.fromisoformat(value.strip())
        if graduated.isoformat() != value.strip():
            raise ValueError
        # The first anniversary of February 29 falls on February 28.
        day = 28 if (graduated.month, graduated.day) == (2, 29) else graduated.day
        cleanup = graduated.replace(year=graduated.year + 1, day=day)
    except (AttributeError, ValueError, OverflowError) as exc:
        raise InventoryError("Enter a graduation date as YYYY-MM-DD.") from exc
    today = today or date.today()
    if already_graduated and graduated > today:
        raise InventoryError("An actual graduation date must be today or earlier.")
    if not already_graduated and graduated < today:
        raise InventoryError("An expected graduation date must be today or later.")
    return graduated, cleanup


class GraduationServiceMixin:
    def get_graduation(self, cadet_id):
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM cadet_graduations WHERE cadet_id=?", (cadet_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_graduation(self, *, cadet_id, graduation_date, already_graduated, approved_by):
        from .database import utc_now
        from .services import InventoryError

        actor = self._normalize_admin_identity(approved_by)["label"]
        graduated, cleanup = graduation_dates(graduation_date, already_graduated=already_graduated)
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._is_easter_egg_cadet_id(cadet_id) or not connection.execute(
                "SELECT 1 FROM cadets WHERE cadet_id=?", (cadet_id,)
            ).fetchone():
                raise InventoryError("Select a saved cadet to schedule graduation.")
            cursor = connection.execute(
                """INSERT INTO cadet_graduations(cadet_id,graduation_date,cleanup_date,approved_by,approved_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(cadet_id) DO UPDATE SET graduation_date=excluded.graduation_date,
                       cleanup_date=excluded.cleanup_date,approved_by=excluded.approved_by,
                       approved_at=excluded.approved_at
                   WHERE cadet_graduations.completed_at=''""",
                (cadet_id, graduated.isoformat(), cleanup.isoformat(), actor, utc_now()),
            )
            if not cursor.rowcount:
                raise InventoryError("Graduation cleanup has already completed for this cadet.")
        self.database.note_write()

    def cancel_graduation(self, *, cadet_id, approved_by):
        from .services import InventoryError

        self._normalize_admin_identity(approved_by)
        with closing(self.database.connect()) as connection, connection:
            deleted = connection.execute(
                "DELETE FROM cadet_graduations WHERE cadet_id=? AND completed_at=''", (cadet_id,)
            ).rowcount
            if not deleted:
                raise InventoryError("There is no pending graduation schedule to cancel.")
        self.database.note_write()

    def process_due_graduations(self, *, today=None):
        from .services import InventoryError

        cutoff = (today or date.today()).isoformat()
        with closing(self.database.connect()) as connection:
            due = connection.execute(
                """SELECT g.cadet_id,c.full_name FROM cadet_graduations g JOIN cadets c USING(cadet_id)
                   WHERE completed_at='' AND cleanup_date<=? ORDER BY cleanup_date,cadet_id""", (cutoff,)
            ).fetchall()
        completed, failures = [], []
        for cadet in due:
            try:
                result = self._complete_graduation(cadet["cadet_id"], cutoff)
            except InventoryError as exc:
                failures.append(f'{cadet["full_name"]}: {exc}')
            else:
                if result is not None:
                    completed.append(result)
        if completed:
            self.database.note_write()
        return completed, failures

    def _complete_graduation(self, cadet_id, cutoff):
        from .database import utc_now
        from .services import InventoryError

        with closing(self.database.connect()) as connection, connection:
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("BEGIN IMMEDIATE")
            schedule = connection.execute(
                """SELECT g.*,c.email FROM cadet_graduations g JOIN cadets c USING(cadet_id)
                   WHERE cadet_id=? AND completed_at='' AND cleanup_date<=?""", (cadet_id, cutoff)
            ).fetchone()
            if not schedule:
                return None
            owner = (cadet_id, schedule["email"])
            belongs = "cadet_id=? OR (cadet_id IS NULL AND lower(cadet_email)=lower(?))"
            transactions = connection.execute(
                f"SELECT barcode_id,return_time FROM transactions WHERE {belongs}", owner
            ).fetchall()
            acquired = Counter(row["barcode_id"] for row in transactions if row["return_time"] is None)
            for barcode, quantity in acquired.items():
                item = connection.execute("SELECT * FROM items WHERE barcode_id=?", (barcode,)).fetchone()
                open_count = self._open_checkout_count(connection, barcode)
                if not item or item["total_quantity"] < open_count:
                    raise InventoryError(f"Correct the stock balance for {barcode} before cleanup.")
                if item["status"] not in ("Lost", "Retired") and (
                    item["total_quantity"] - open_count != item["available_quantity"]
                ):
                    raise InventoryError(f"Correct the shelf count for {barcode} before cleanup.")
            connection.execute(
                f"DELETE FROM loan_events WHERE transaction_id IN (SELECT transaction_id FROM transactions WHERE {belongs})",
                owner,
            )
            connection.execute("DELETE FROM acquisition_actions WHERE cadet_id=?", (cadet_id,))
            connection.execute(
                """UPDATE cic_lines SET transaction_ids='[]' WHERE card_id IN
                   (SELECT card_id FROM cic_cards WHERE cadet_id=?) AND transaction_ids<>'[]'""", (cadet_id,)
            )
            connection.execute(f"DELETE FROM transactions WHERE {belongs}", owner)
            stamp = utc_now()
            for barcode, quantity in acquired.items():
                last_change = connection.execute("SELECT COALESCE(MAX(change_id),0) FROM inventory_changes").fetchone()[0]
                connection.execute(
                    "UPDATE items SET total_quantity=total_quantity-?,updated_at=? WHERE barcode_id=?",
                    (quantity, stamp, barcode),
                )
                self._sync_item_state(connection, barcode)
                connection.execute(
                    """UPDATE inventory_changes SET action='Graduation Acquisition',details=?,source=?
                       WHERE change_id>? AND barcode_id=?""",
                    (f"{quantity} outstanding unit(s) permanently issued at graduation cleanup.",
                     schedule["approved_by"], last_change, barcode),
                )
            connection.execute(
                """UPDATE cadet_graduations SET completed_at=?,transactions_deleted=?,units_acquired=?
                   WHERE cadet_id=?""",
                (stamp, len(transactions), sum(acquired.values()), cadet_id),
            )
            return {"cadet_id": cadet_id, "transactions_deleted": len(transactions),
                    "units_acquired": sum(acquired.values())}
