"""SQLite store — signals, positions, trades, calibration."""
import sqlite3
import contextlib
from config import DB_PATH


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            direction   TEXT NOT NULL,       -- 'up' or 'down'
            implied_prob REAL NOT NULL,      -- Polymarket implied probability
            book_depth_usd REAL,
            up_depth    REAL,
            down_depth  REAL,
            market_slug TEXT,
            fired       INTEGER DEFAULT 0,   -- 1 if we traded on this signal
            skip_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id    INTEGER REFERENCES signals(id),
            ticker       TEXT NOT NULL,
            direction    TEXT NOT NULL,      -- 'buy' or 'sell_short'
            entry_ts     TEXT NOT NULL,
            entry_price  REAL NOT NULL,
            shares       REAL NOT NULL,
            notional_usd REAL NOT NULL,
            order_id     TEXT,
            status       TEXT DEFAULT 'open',  -- open / closed / error
            exit_ts      TEXT,
            exit_price   REAL,
            exit_reason  TEXT,               -- profit_target / stop_loss / hard_close / manual
            realized_pnl REAL,
            poly_implied_prob REAL,          -- Polymarket prob at signal time (for calibration)
            poly_outcome TEXT                -- 'correct' / 'wrong' / NULL (unresolved)
        );

        CREATE TABLE IF NOT EXISTS calibration (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT NOT NULL,
            ticker           TEXT NOT NULL,
            direction        TEXT NOT NULL,
            implied_prob     REAL NOT NULL,
            stock_moved_pct  REAL,           -- actual % move EOD
            poly_correct     INTEGER,        -- 1=prediction correct, 0=wrong
            stock_pnl        REAL,           -- what we made/lost on the stock trade
            notes            TEXT
        );
        """)


@contextlib.contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
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
             up_depth, down_depth, market_slug, fired, skip_reason)
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
             shares, notional_usd, order_id, 'open', poly_implied_prob)
        )
        return cur.lastrowid


def close_position(pos_id, exit_ts, exit_price, exit_reason, realized_pnl):
    with conn() as c:
        c.execute(
            """UPDATE positions SET status='closed', exit_ts=?, exit_price=?,
               exit_reason=?, realized_pnl=? WHERE id=?""",
            (exit_ts, exit_price, exit_reason, realized_pnl, pos_id)
        )


def open_positions():
    with conn() as c:
        return c.execute(
            "SELECT * FROM positions WHERE status='open' ORDER BY entry_ts"
        ).fetchall()


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
