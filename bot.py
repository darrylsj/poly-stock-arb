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
    MAX_POSITIONS,
)
import store
import signal as sig_module
import trader

ET = zoneinfo.ZoneInfo("America/New_York")
LIVE = os.environ.get("LIVE", "0") == "1"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

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

    # Load from DB so restart mid-day doesn't double-trade the same ticker
    fired_today = store.tickers_traded_today()

    log.info("Scanning Polymarket signals...")
    signals = sig_module.scan_all()
    ts = et_now().isoformat()

    for s in signals:
        ticker = s["ticker"]
        if ticker in fired_today:
            continue
        if s.get("error"):
            log.debug("  %s: %s", ticker, s["error"])
            continue

        prob      = s["implied_prob"]
        depth     = s.get("dominant_depth", 0)
        direction = s["direction"]

        log.info("  %s: %s @ %.0f%% depth=$%.0f", ticker, direction, prob * 100, depth)

        fired = 0
        skip_reason = None

        if prob >= SIGNAL_THRESHOLD and depth >= MIN_BOOK_DEPTH_USD:
            price = trader.get_price(ticker)
            if not price:
                skip_reason = "no_price"
            elif len(store.open_positions()) >= MAX_POSITIONS:
                skip_reason = "max_positions"
            else:
                shares = trader.shares_for_notional(price, NOTIONAL_USD)
                side = "buy" if direction == "up" else "sell_short"

                order_id = ""
                status = "shadow"

                if LIVE:
                    result = trader.place_order(ticker, side, shares)
                    if not result["success"]:
                        skip_reason = f"order_failed:{result['status']}"
                        log.warning("  → ORDER FAILED %s %s: %s", ticker, side, result["status"])
                        store.log_signal(ts, ticker, direction, prob,
                                         s["total_depth"], s["up_depth"],
                                         s["down_depth"], s["market_slug"],
                                         fired=0, skip_reason=skip_reason)
                        continue
                    order_id = result["order_id"]
                    status = result["status"]
                    log.info("  → PAPER ORDER %s %s %dsh @ $%.2f | %s #%s",
                             ticker, side, shares, price, status, order_id)
                else:
                    order_id = f"SHADOW-{ticker}-{ts[:10]}"
                    log.info("  → SHADOW (LIVE=0) %s %s %dsh @ $%.2f",
                             ticker, side, shares, price)

                sig_id = store.log_signal(ts, ticker, direction, prob,
                                          s["total_depth"], s["up_depth"],
                                          s["down_depth"], s["market_slug"],
                                          fired=1)
                store.open_position(sig_id, ticker, side, ts, price,
                                    shares, shares * price, order_id, prob)
                fired_today.add(ticker)
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
        direction = pos["direction"]
        entry     = pos["entry_price"]
        shares    = pos["shares"]

        current = trader.get_price(ticker)
        if not current:
            log.warning("  SKIP %s — could not fetch price", ticker)
            continue

        pct_move = (current - entry) / entry
        if direction == "sell_short":
            pct_move = -pct_move

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
            order_ok = True
            if LIVE:
                result = trader.place_order(ticker, close_side, int(shares))
                order_ok = result["success"]
                if not order_ok:
                    log.error("  CLOSE ORDER FAILED %s %s: %s — position left open",
                              ticker, close_side, result["status"])

            if order_ok:
                log.info("  CLOSE %s %s: entry=$%.2f now=$%.2f move=%+.2f%% pnl=$%+.2f",
                         ticker, exit_reason, entry, current, pct_move * 100, pnl)
                store.close_position(pos_id, now_ts, current, exit_reason, pnl)
        else:
            log.info("  HOLD %s: entry=$%.2f now=$%.2f move=%+.2f%% pnl=$%+.2f",
                     ticker, entry, current, pct_move * 100, pnl)


def main():
    store.init_db()
    global _last_signal_scan, _last_position_check

    mode = "LIVE (paper orders)" if LIVE else "SHADOW (no orders)"
    log.info("Poly-Stock Arb Bot started — %s", mode)
    log.info("Signal threshold: %.0f%% | Window: %s–%s ET",
             SIGNAL_THRESHOLD * 100, SIGNAL_WINDOW_START_ET, SIGNAL_WINDOW_END_ET)

    while True:
        now = time.time()

        if not is_market_hours():
            log.info("Market closed — sleeping 5 min")
            time.sleep(300)
            continue

        if now - _last_signal_scan >= POLL_INTERVAL_SEC:
            try:
                _process_signals()
            except Exception as e:
                log.error("Signal scan error: %s", e, exc_info=True)
            _last_signal_scan = now

        if now - _last_position_check >= POSITION_CHECK_SEC:
            try:
                _manage_positions()
            except Exception as e:
                log.error("Position check error: %s", e, exc_info=True)
            _last_position_check = now

        time.sleep(10)


if __name__ == "__main__":
    main()
