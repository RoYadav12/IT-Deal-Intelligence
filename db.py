"""
All SQLite access lives here: one schema, used by every script.

Writes are resilient to "database is locked" errors (WAL mode, a long
busy-timeout, and a commit-retry loop). Older databases (created before the
DealType column existed) are upgraded automatically on first connect.

Row Status values:
  'Pending'  - URL queued, not yet extracted
  'Done'     - extracted successfully
  anything else - the error message from a failed attempt
"""

import sqlite3
import time

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    URL TEXT UNIQUE,
    Customer TEXT,
    CustomerWebsite TEXT,
    Vendor TEXT,
    VendorWebsite TEXT,
    "Deal Value" TEXT,
    Country TEXT,
    Technology TEXT,
    Date TEXT,
    Summary TEXT,
    Confidence TEXT,
    CustomerIndustry TEXT,
    VendorIndustry TEXT,
    SecondaryMarket TEXT,
    Status TEXT,
    DealType TEXT
)
"""

UPDATABLE_FIELDS = [
    "Customer", "CustomerWebsite", "Vendor", "VendorWebsite", "Deal Value",
    "Country", "Technology", "Date", "Summary", "Confidence",
    "CustomerIndustry", "VendorIndustry", "SecondaryMarket", "DealType",
    "Status",
]

COMMIT_MAX_ATTEMPTS = 6
COMMIT_RETRY_BACKOFF_SECONDS = 0.5


def get_connection():
    """Open a connection and make sure the schema exists (idempotent)."""
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(SCHEMA)
    _upgrade_schema(conn)
    _commit_with_retry(conn)
    return conn


def _upgrade_schema(conn):
    """Add any column an older database file is missing."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(deals)")}
    for column in UPDATABLE_FIELDS:
        if column not in existing:
            conn.execute(f'ALTER TABLE deals ADD COLUMN "{column}" TEXT')


def _commit_with_retry(conn):
    for attempt in range(1, COMMIT_MAX_ATTEMPTS + 1):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            is_lock_error = "locked" in str(exc).lower()
            if not is_lock_error or attempt == COMMIT_MAX_ATTEMPTS:
                raise
            time.sleep(COMMIT_RETRY_BACKOFF_SECONDS * attempt)


def url_exists(conn, url):
    row = conn.execute("SELECT 1 FROM deals WHERE URL = ?", (url,)).fetchone()
    return row is not None


def get_deal_id(conn, url):
    """Return the id of the row for this URL, or None if it doesn't exist."""
    row = conn.execute("SELECT id FROM deals WHERE URL = ?", (url,)).fetchone()
    return row[0] if row else None


def get_deal_state(conn, url):
    """Return (id, status) for this URL, or None if it doesn't exist."""
    row = conn.execute(
        "SELECT id, Status FROM deals WHERE URL = ?", (url,)
    ).fetchone()
    return (row[0], row[1]) if row else None


def insert_pending_url(conn, url):
    """Queue a newly discovered URL. Returns True if added, False if it
    already existed (relies on the UNIQUE constraint)."""
    try:
        conn.execute(
            "INSERT INTO deals (URL, Status) VALUES (?, ?)", (url, "Pending")
        )
        _commit_with_retry(conn)
        return True
    except sqlite3.IntegrityError:
        return False


def insert_processed_deal(conn, url, fields):
    """Insert a brand-new row that already has extracted fields.
    Returns the new row's id."""
    columns = ["URL"] + UPDATABLE_FIELDS
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{c}"' for c in columns)
    values = [url] + [fields.get(f, "Unknown") for f in UPDATABLE_FIELDS]
    cursor = conn.execute(
        f"INSERT INTO deals ({quoted_columns}) VALUES ({placeholders})",
        values,
    )
    _commit_with_retry(conn)
    return cursor.lastrowid


def save_deal(conn, url, fields):
    """Insert-or-update the row for `url` and return its id. Safe even if
    another browser session saved the same URL a moment earlier."""
    state = get_deal_state(conn, url)
    if state is None:
        try:
            return insert_processed_deal(conn, url, fields)
        except sqlite3.IntegrityError:
            state = get_deal_state(conn, url)
            if state is None:
                raise
    update_deal(conn, state[0], fields)
    return state[0]


def get_pending_deals(conn, limit=None):
    sql = "SELECT id, URL FROM deals WHERE Status = 'Pending' ORDER BY id"
    if limit and limit > 0:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def count_by_status(conn):
    """Return {'done': n, 'pending': n, 'failed': n}."""
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(Status = 'Done'), 0),
            COALESCE(SUM(Status = 'Pending'), 0),
            COALESCE(SUM(Status IS NOT NULL
                         AND Status NOT IN ('Done', 'Pending')), 0)
        FROM deals
        """
    ).fetchone()
    return {"done": row[0], "pending": row[1], "failed": row[2]}


def requeue_failed(conn):
    """Flip every failed row back to Pending so the next pipeline run
    retries it (e.g. after fixing an API key). Returns how many."""
    cursor = conn.execute(
        "UPDATE deals SET Status = 'Pending' "
        "WHERE Status IS NOT NULL AND Status NOT IN ('Done', 'Pending')"
    )
    _commit_with_retry(conn)
    return cursor.rowcount


def update_deal(conn, deal_id, fields):
    """fields: dict of column -> value, only columns in UPDATABLE_FIELDS."""
    unknown = set(fields) - set(UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown column(s): {sorted(unknown)}")
    columns = ", ".join(f'"{k}" = ?' for k in fields)
    values = list(fields.values()) + [deal_id]
    conn.execute(f"UPDATE deals SET {columns} WHERE id = ?", values)
    _commit_with_retry(conn)


def mark_failed(conn, deal_id, reason):
    update_deal(conn, deal_id, {"Status": str(reason)[:300]})


def fetch_all_deals_df(conn):
    import pandas as pd
    return pd.read_sql("SELECT * FROM deals", conn)
