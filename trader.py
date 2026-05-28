"""Tradier PAPER account execution layer.

Uses sandbox.tradier.com — ZERO real money.
"""
import logging
import requests
from config import TRADIER_SANDBOX_BASE, TRADIER_SANDBOX_TOKEN, TRADIER_SANDBOX_ACCOUNT

log = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {TRADIER_SANDBOX_TOKEN}",
    "Accept": "application/json",
}


def _post(path: str, data: dict) -> dict:
    """POST to Tradier sandbox; raises on HTTP errors."""
    r = requests.post(
        f"{TRADIER_SANDBOX_BASE}{path}",
        data=data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if not r.ok:
        log.error("Tradier POST %s → HTTP %s: %s", path, r.status_code, r.text[:200])
        r.raise_for_status()
    return r.json()


def _get(path: str, params: dict = None) -> dict:
    """GET from Tradier sandbox; raises on HTTP errors."""
    r = requests.get(
        f"{TRADIER_SANDBOX_BASE}{path}",
        params=params or {},
        headers=HEADERS,
        timeout=10,
    )
    if not r.ok:
        log.error("Tradier GET %s → HTTP %s: %s", path, r.status_code, r.text[:200])
        r.raise_for_status()
    return r.json()


def get_quote(ticker: str) -> dict:
    """Return latest quote dict for ticker, or None on failure."""
    try:
        data = _get("/markets/quotes", {"symbols": ticker, "greeks": "false"})
        q = data.get("quotes", {}).get("quote", {})
        if isinstance(q, list):
            q = q[0] if q else {}
        return q or None
    except Exception as e:
        log.warning("get_quote(%s) failed: %s", ticker, e)
        return None


def get_price(ticker: str) -> float:
    """Current last price, or None on failure."""
    try:
        q = get_quote(ticker)
        if not q:
            return None
        last = q.get("last")
        return float(last) if last is not None else None
    except Exception as e:
        log.warning("get_price(%s) failed: %s", ticker, e)
        return None


def account_balances() -> dict:
    """Return cash, equity, and margin info."""
    try:
        data = _get(f"/accounts/{TRADIER_SANDBOX_ACCOUNT}/balances")
        return data.get("balances", {})
    except Exception as e:
        log.warning("account_balances() failed: %s", e)
        return {}


def place_order(ticker: str, side: str, shares: int,
                order_type: str = "market", limit_price: float = None) -> dict:
    """Place a paper order.

    side: 'buy' | 'sell' | 'sell_short' | 'buy_to_cover'
    Returns dict with order_id, status, and success flag.
    """
    payload = {
        "class":    "equity",
        "symbol":   ticker,
        "side":     side,
        "quantity": shares,
        "type":     order_type,
        "duration": "day",
    }
    if order_type == "limit" and limit_price:
        payload["price"] = f"{limit_price:.2f}"

    try:
        data = _post(f"/accounts/{TRADIER_SANDBOX_ACCOUNT}/orders", payload)
        order = data.get("order", {})
        status = order.get("status", "error")
        ok = status in ("ok", "filled", "pending", "open")
        return {
            "order_id": str(order.get("id", "")),
            "status":   status,
            "success":  ok,
            "raw":      data,
        }
    except Exception as e:
        log.error("place_order(%s %s %s) failed: %s", ticker, side, shares, e)
        return {"order_id": "", "status": "error", "success": False, "raw": {}}


def cancel_order(order_id: str) -> bool:
    try:
        r = requests.delete(
            f"{TRADIER_SANDBOX_BASE}/accounts/{TRADIER_SANDBOX_ACCOUNT}/orders/{order_id}",
            headers=HEADERS,
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        log.warning("cancel_order(%s) failed: %s", order_id, e)
        return False


def get_positions() -> list:
    """All open positions in the paper account."""
    try:
        data = _get(f"/accounts/{TRADIER_SANDBOX_ACCOUNT}/positions")
        pos = data.get("positions", {}).get("position", [])
        if isinstance(pos, dict):
            pos = [pos]
        return pos or []
    except Exception as e:
        log.warning("get_positions() failed: %s", e)
        return []


def shares_for_notional(price: float, notional_usd: float) -> int:
    """How many whole shares fit in notional_usd at price."""
    return max(1, int(notional_usd // price))
