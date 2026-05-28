"""Configuration — Polymarket→Stock Arbitrage Signal Bot.

All secrets are loaded from environment variables. Copy .env.example to .env
and fill in your values, then source it before running.
"""
import os
import sys

# ---------------------------------------------------------------------------
# Tradier PAPER account (sandbox.tradier.com — zero real money)
# ---------------------------------------------------------------------------
TRADIER_SANDBOX_TOKEN   = os.environ.get("TRADIER_SANDBOX_TOKEN", "")
TRADIER_SANDBOX_ACCOUNT = os.environ.get("TRADIER_SANDBOX_ACCOUNT", "")
TRADIER_SANDBOX_BASE    = "https://sandbox.tradier.com/v1"

if not TRADIER_SANDBOX_TOKEN or not TRADIER_SANDBOX_ACCOUNT:
    print(
        "ERROR: TRADIER_SANDBOX_TOKEN and TRADIER_SANDBOX_ACCOUNT must be set.\n"
        "  export TRADIER_SANDBOX_TOKEN=<your-sandbox-token>\n"
        "  export TRADIER_SANDBOX_ACCOUNT=<your-sandbox-account-id>",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Polymarket public APIs (no auth required for book reads)
# ---------------------------------------------------------------------------
POLYMARKET_CLOB  = "https://clob.polymarket.com"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"

# ---------------------------------------------------------------------------
# Tickers to watch — must have an active Polymarket "up or down today" market
# ---------------------------------------------------------------------------
TICKERS = ["AAPL", "AMZN", "TSLA", "NVDA", "META", "MSFT", "GOOGL", "COIN", "PLTR"]

# ---------------------------------------------------------------------------
# Signal filter parameters
# ---------------------------------------------------------------------------
SIGNAL_THRESHOLD        = 0.75   # implied probability must exceed this to fire
MIN_BOOK_DEPTH_USD      = 300    # minimum $ depth on the dominant book side
SIGNAL_WINDOW_START_ET  = "09:45"  # no trades before this (post-open flush)
SIGNAL_WINDOW_END_ET    = "11:00"  # no new entries after this
HARD_CLOSE_ET           = "15:45"  # force-close all open positions here

# ---------------------------------------------------------------------------
# Position sizing and risk
# ---------------------------------------------------------------------------
NOTIONAL_USD      = 200    # approximate $ notional per trade
PROFIT_TARGET_PCT = 0.015  # exit long/short at +1.5 %
STOP_LOSS_PCT     = 0.010  # exit long/short at -1.0 %
MAX_POSITIONS     = 3      # maximum concurrent open positions

# ---------------------------------------------------------------------------
# Polling intervals
# ---------------------------------------------------------------------------
POLL_INTERVAL_SEC  = 120  # Polymarket scan cadence (seconds)
POSITION_CHECK_SEC = 60   # open-position management cadence (seconds)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("DB_PATH", "poly_arb.db")
