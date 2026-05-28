"""Main bot loop — Polymarket signal → Tradier paper execution.

Run: python3 bot.py
Shadow-only until LIVE=1 env var is set.
"""
import os
import time
import datetime
import zoneinfo
import logging
from config import (
    SIGNAL_THRESHOLD, MIN_BOOK_DEPTH_USD, POLL_INTERVAL_SEC,
    POSITION_CHECK_SEC, HARD_CLOSE_ET, SIGNAL_WINDOW_START_ET,
    SIGNAL_WINDOW_END_ET, NOTIONAL_USD, PROFIT_TARGET_PCT, STOP_LOSS_PCT,
    MAX_POSITIONS
)
import store
import signal as sig_module
import trader

ET = zoneinfo.ZoneInfo("America/New_York")
LIVE = os.environ.get("LIVE", "0") == "1"  # set LIVE=1 to actually place paper orders

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

_fired_today: set[str] = set()   # tickers we already traded today
_last_signal_scan = 0
_last_position_check = 0


def et_now() -> datetime.datetime:
    return datetime.datetime.now(ET)


def et_time_str() -> str:
    return et_now().strftime("%H:%M")


def in_signal_window() -> bool:
    t = et_time_str()
    return SIGNAL_WINDOW_START_ET <= t <= SIGNAL_WINDOW_END_ET


def past_hard_close() -> bool:
    return et_time_str() >= HARD_CLOSE_ET


def is_market_hours() -> bool:
    now = et_now()
    if now.weekday() >= 5:
        return False
    t = et_time_str()
    return "09:30" <= t <= "16:00"


def _process_signals():
    if not in_signal_window():
        return
    open_pos = store.open_positions()
    if len(open_pos) >= MAX_POSITIONS:
        return

    log.info("Scanning Polymarket signals...")
    signals = sig_module.scan_all()
    ts = et_now().isoformat()

    for s in signals:
        ticker = s["ticker"]
        if ticker in _fired_today:
            continue
        if s.get("error"):
            log.debug(f"  {ticker}: {s['error']}")
            continue

        prob = s["implied_prob"]
        depth = s.get("dominant_depth", 0)
        direction = s["direction"]

        log.info(f"  {ticker}: {direction} @ {prob:.0%} depth=${depth:.0f}")

        fired = 0
        skip_reason = None

        if prob >= SIGNAL_THRESHOLD and depth >= MIN_BOOK_DEPTH_USD:
            # Signal qualifies — enter position
            price = trader.get_price(ticker)
            if not price:
                skip_reason = "no_price"
            elif len(store.open_positions()) >= MAX_POSITIONS:
                skip_reason = "max_positions"
            else:
                shares = trader.shares_for_notional(price, NOTIONAL_USD)
                side = "buy" if direction == "up" else "sell_short"

                if LIVE:
                    result = trader.place_order(ticker, side, shares)
                    order_id = result.get("order_id", "")
                    status = result.get("status", "")
                    log.info(f"  → PAPER ORDER {ticker} {side} {shares}sh @ ${price:.2f} | {status} #{order_id}")
                else:
                    order_id = f"SHADOW-{ticker}-{ts[:10]}"
                    status = "shadow"
                    log.info(f"  → SHADOW (LIVE=0) {ticker} {side} {shares}sh @ ${price:.2f}")

                sig_id = store.log_signal(ts, ticker, direction, prob,
                                          s["total_depth"], s["up_depth"],
                                          s["down_depth"], s["market_slug"],
                                          fired=1)
                store.open_position(sig_id, ticker, side, ts, price,
                                    shares, shares * price, order_id, prob)
                _fired_today.add(ticker)
                fired = 1
        else:
            if prob < SIGNAL_THRESHOLD:
                skip_reason = f"prob_{prob:.2f}_below_{SIGNAL_THRESHOLD}"
            else:
                skip_reason = f"depth_{depth:.0f}_below_{MIN_BOOK_DEPTH_USD}"

        if not fired:
            store.log_signal(ts, ticker, direction, prob,
                             s["total_depth"], s["up_depth"],
                             s["down_depth"], s["market_slug"],
                             fired=0, skip_reason=skip_reason)


def _manage_positions():
    positions = store.open_positions()
    if not positions:
        return

    now_ts = et_now().isoformat()
    force_close = past_hard_close()

    for pos in positions:
        pos_id    = pos["id"]
        ticker    = pos["ticker"]
        direction = pos["direction"]   # 'buy' or 'sell_short'
        entry     = pos["entry_price"]
        shares    = pos["shares"]

        current = trader.get_price(ticker)
        if not current:
            continue

        pct_move = (current - entry) / entry
        if direction == "sell_short":
            pct_move = -pct_move    # profit when price falls

        pnl = round(pct_move * entry * shares, 2)

        exit_reason = None
        if force_close:
            exit_reason = "hard_close"
        elif pct_move >= PROFIT_TARGET_PCT:
            exit_reason = "profit_target"
        elif pct_move <= -STOP_LOSS_PCT:
            exit_reason = "stop_loss"

        if exit_reason:
            close_side = "sell" if direction == "buy" else "buy_to_cover"
            if LIVE:
                trader.place_order(ticker, close_side, int(shares))
            log.info(f"  CLOSE {ticker} {exit_reason}: entry=${entry:.2f} "
                     f"now=${current:.2f} move={pct_move:+.2%} pnl=${pnl:+.2f}")
            store.close_position(pos_id, now_ts, current, exit_reason, pnl)
        else:
            log.info(f"  HOLD {ticker}: entry=${entry:.2f} now=${current:.2f} "
                     f"move={pct_move:+.2%} pnl=${pnl:+.2f}")


def main():
    store.init_db()
    global _last_signal_scan, _last_position_check

    mode = "LIVE (paper orders)" if LIVE else "SHADOW (no orders)"
    log.info(f"Poly-Stock Arb Bot started — {mode}")
    log.info(f"Signal threshold: {SIGNAL_THRESHOLD:.0%} | Window: {SIGNAL_WINDOW_START_ET}–{SIGNAL_WINDOW_END_ET} ET")

    while True:
        now = time.time()

        if not is_market_hours():
            log.info("Market closed — sleeping 5 min")
            time.sleep(300)
            continue

        # Signal scan every POLL_INTERVAL_SEC
        if now - _last_signal_scan >= POLL_INTERVAL_SEC:
            try:
                _process_signals()
            except Exception as e:
                log.error(f"Signal scan error: {e}", exc_info=True)
            _last_signal_scan = now

        # Position management every POSITION_CHECK_SEC
        if now - _last_position_check >= POSITION_CHECK_SEC:
            try:
                _manage_positions()
            except Exception as e:
                log.error(f"Position check error: {e}", exc_info=True)
            _last_position_check = now

        time.sleep(30)


if __name__ == "__main__":
    main()
