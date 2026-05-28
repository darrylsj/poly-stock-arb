"""SQLite store — signals, positions, trades, calibration."""
import sqlite3
import contextlib
import datetime
from config import DB_PATH

_CONNECT_TIMEOUT = 10  # seconds to wait for a locked DB before giving up


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ts             TEXT NOT NULL,
            ticker         TEXT NOT NULL,
            direction      TEXT NOT NULL,
            implied_prob   REAL NOT NULL,
            book_depth_usd REAL,
            up_depth       REAL,
            down_depth     REAL,
            market_slug    TEXT,
            fired          INTEGER DEFAULT 0,
            skip_reason    TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id         INTEGER REFERENCES signals(id),
            ticker            TEXT NOT NULL,
            direction         TEXT NOT NULL,
            entry_ts          TEXT NOT NULL,
            entry_price       REAL NOT NULL,
            shares            REAL NOT NULL,
            notional_usd      REAL NOT NULL,
            order_id          TEXT,
            status            TEXT DEFAULT 'open',
            exit_ts           TEXT,
            exit_price        REAL,
            exit_reason       TEXT,
            realized_pnl      REAL,
            poly_implied_prob REAL,
            poly_outcome      TEXT
        );

        CREATE TABLE IF NOT EXISTS calibration (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT NOT NULL,
            ticker           TEXT NOT NULL,
            direction        TEXT NOT NULL,
            implied_prob     REAL NOT NULL,
            stock_moved_pct  REAL,
            poly_correct     INTEGER,
            stock_pnl        REAL,
            notes            TEXT
        );
        """)


@contextlib.contextmanager
def conn():
    """Context manager that yields a Row-factory connection and commits on exit."""
    c = sqlite3.connect(DB_PATH, timeout=_CONNECT_TIMEOUT)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def log_signal(ts, ticker, direction, implied_prob, book_depth_usd,
               up_depth, down_depth, market_slug, fired, skip_reason=None):
    with conn() as c:
        cur = c.execute(
            """INSERT INTO signals
               (ts, ticker, direction, implied_prob, book_depth_usd,
                up_depth, down_depth, market_slug, fired, skip_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ts, ticker, direction, implied_prob, book_depth_usd,
             up_depth, down_depth, market_slug, fired, skip_reason),
        )
        return cur.lastrowid


def open_position(signal_id, ticker, direction, entry_ts, entry_price,
                  shares, notional_usd, order_id, poly_implied_prob):
    with conn() as c:
        cur = c.execute(
            """INSERT INTO positions
               (signal_id, ticker, direction, entry_ts, entry_price,
                shares, notional_usd, order_id, status, poly_implied_prob)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (signal_id, ticker, direction, entry_ts, entry_price,
             shares, notional_usd, order_id, "open", poly_implied_prob),
        )
        return cur.lastrowid


def close_position(pos_id, exit_ts, exit_price, exit_reason, realized_pnl):
    with conn() as c:
        c.execute(
            """UPDATE positions SET status='closed', exit_ts=?, exit_price=?,
               exit_reason=?, realized_pnl=? WHERE id=?""",
            (exit_ts, exit_price, exit_reason, realized_pnl, pos_id),
        )


def open_positions():
    with conn() as c:
        return c.execute(
            "SELECT * FROM positions WHERE status='open' ORDER BY entry_ts"
        ).fetchall()


def tickers_traded_today() -> set:
    """Return set of tickers that have an open or closed position entered today."""
    today = datetime.date.today().isoformat()
    with conn() as c:
        rows = c.execute(
            "SELECT ticker FROM positions WHERE DATE(entry_ts)=?", (today,)
        ).fetchall()
    return {r["ticker"] for r in rows}


def recent_signals(limit=50):
    with conn() as c:
        return c.execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def daily_summary(date):
    with conn() as c:
        return c.execute("""
            SELECT COUNT(*) as trades,
                   SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(COALESCE(realized_pnl,0)),2) as net_pnl
            FROM positions WHERE DATE(entry_ts)=? AND status='closed'
        """, (date,)).fetchone()
