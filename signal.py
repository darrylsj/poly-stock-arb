"""Polymarket book imbalance signal reader.

For each ticker, finds the "up or down today" Polymarket market,
reads the CLOB order book, and returns implied probability.
"""
import requests
import datetime
from config import POLYMARKET_CLOB, POLYMARKET_GAMMA, TICKERS

# Slug patterns Polymarket uses for stock direction markets
def _today_slug(ticker: str) -> list[str]:
    today = datetime.date.today()
    dt = today.strftime("%B-%-d-%Y").lower()        # e.g. may-28-2026
    dt2 = today.strftime("%b-%-d-%Y").lower()       # e.g. may-28-2026 (same)
    base = ticker.lower()
    return [
        f"{base}-up-or-down-on-{dt}",
        f"will-{base}-be-up-or-down-on-{dt}",
        f"{base}-up-or-down-{dt}",
    ]


def _find_market(ticker: str) -> dict:
    """Search Gamma API for today's up/down market for ticker."""
    today = datetime.date.today().isoformat()
    slugs = _today_slug(ticker)
    for slug in slugs:
        try:
            r = requests.get(
                f"{POLYMARKET_GAMMA}/markets",
                params={"slug": slug},
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                markets = data if isinstance(data, list) else data.get("markets", [])
                for m in markets:
                    if m.get("endDate", "")[:10] == today or m.get("end_date_iso", "")[:10] == today:
                        return m
                if markets:
                    return markets[0]
        except Exception:
            pass

    # Fallback: search by keyword
    try:
        r = requests.get(
            f"{POLYMARKET_GAMMA}/markets",
            params={"q": f"{ticker} up or down", "limit": 5},
            timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            markets = data if isinstance(data, list) else data.get("markets", [])
            for m in markets:
                if ticker.upper() in m.get("question", "").upper() and "up or down" in m.get("question", "").lower():
                    return m
    except Exception:
        pass
    return None


def _book_imbalance(token_id: str) -> dict:
    """Read CLOB order book for a token and return depth + implied mid price."""
    try:
        r = requests.get(
            f"{POLYMARKET_CLOB}/book",
            params={"token_id": token_id},
            timeout=8
        )
        if r.status_code != 200:
            return {}
        book = r.json()
        bids = book.get("bids", [])
        asks = book.get("asks", [])

        bid_depth = sum(float(b["size"]) * float(b["price"]) for b in bids[:10])
        ask_depth = sum(float(a["size"]) * float(a["price"]) for a in asks[:10])
        best_bid = float(bids[0]["price"]) if bids else None
        best_ask = float(asks[0]["price"]) if asks else None
        mid = round((best_bid + best_ask) / 2, 4) if (best_bid and best_ask) else None

        return {
            "bid_depth_usd": round(bid_depth, 2),
            "ask_depth_usd": round(ask_depth, 2),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": mid,
        }
    except Exception:
        return {}


def get_signal(ticker: str) -> dict:
    """Return signal dict for ticker. Keys:
       ticker, direction, implied_prob, up_depth, down_depth,
       total_depth, market_slug, raw_up_mid, raw_down_mid, error
    """
    result = {"ticker": ticker, "direction": None, "implied_prob": None,
              "up_depth": 0, "down_depth": 0, "total_depth": 0,
              "market_slug": None, "error": None}

    market = _find_market(ticker)
    if not market:
        result["error"] = "market_not_found"
        return result

    result["market_slug"] = market.get("slug") or market.get("conditionId", "")[:12]

    # Get token IDs for Up and Down outcomes
    tokens = market.get("clobTokenIds") or market.get("tokens") or []
    if isinstance(tokens, str):
        import json
        try:
            tokens = json.loads(tokens)
        except Exception:
            tokens = []

    outcomes = market.get("outcomes", ["Up", "Down"])
    if isinstance(outcomes, str):
        import json
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = ["Up", "Down"]

    up_token = down_token = None
    if len(tokens) >= 2:
        for i, outcome in enumerate(outcomes):
            if str(outcome).lower() in ("up", "yes") and i < len(tokens):
                up_token = tokens[i]
            elif str(outcome).lower() in ("down", "no") and i < len(tokens):
                down_token = tokens[i]
        if not up_token:
            up_token = tokens[0]
        if not down_token:
            down_token = tokens[1]

    if not up_token or not down_token:
        result["error"] = "no_tokens"
        return result

    up_book   = _book_imbalance(str(up_token))
    down_book = _book_imbalance(str(down_token))

    up_mid   = up_book.get("mid")
    down_mid = down_book.get("mid")

    if not up_mid or not down_mid:
        result["error"] = "no_book_data"
        return result

    # Depth: proxy using bid_depth_usd on the dominant side
    up_depth   = up_book.get("bid_depth_usd", 0)
    down_depth = down_book.get("bid_depth_usd", 0)

    result.update({
        "up_depth": up_depth,
        "down_depth": down_depth,
        "total_depth": up_depth + down_depth,
        "raw_up_mid": up_mid,
        "raw_down_mid": down_mid,
    })

    # Implied probability of Up = up_mid (Polymarket prices ARE probabilities)
    implied_up   = round(up_mid, 4)
    implied_down = round(down_mid, 4)

    if implied_up > implied_down:
        result["direction"] = "up"
        result["implied_prob"] = implied_up
        result["dominant_depth"] = up_depth
    else:
        result["direction"] = "down"
        result["implied_prob"] = implied_down
        result["dominant_depth"] = down_depth

    return result


def scan_all() -> list:
    """Scan all configured tickers and return list of signal dicts."""
    return [get_signal(t) for t in TICKERS]
