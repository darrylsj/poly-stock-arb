"""Tradier PAPER account execution layer.

Uses sandbox.tradier.com — ZERO real money.
"""
import requests
from config import TRADIER_SANDBOX_BASE, TRADIER_SANDBOX_TOKEN, TRADIER_SANDBOX_ACCOUNT

HEADERS = {
    "Authorization": f"Bearer {TRADIER_SANDBOX_TOKEN}",
    "Accept": "application/json",
}


def _post(path: str, data: dict) -> dict:
    r = requests.post(
        f"{TRADIER_SANDBOX_BASE}{path}",
        data=data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    return r.json()


def _get(path: str, params: dict = None) -> dict:
    r = requests.get(
        f"{TRADIER_SANDBOX_BASE}{path}",
        params=params or {},
        headers=HEADERS,
        timeout=10
    )
    return r.json()


def get_quote(ticker: str) -> dict:
    """Return latest quote dict for ticker."""
    data = _get("/markets/quotes", {"symbols": ticker, "greeks": "false"})
    q = data.get("quotes", {}).get("quote", {})
    if isinstance(q, list):
        q = q[0] if q else {}
    return q or None


def get_price(ticker: str) -> float:
    """Current last price."""
    q = get_quote(ticker)
    return float(q["last"]) if q and q.get("last") else None


def account_balances() -> dict:
    """Return cash, equity, and margin info."""
    data = _get(f"/accounts/{TRADIER_SANDBOX_ACCOUNT}/balances")
    return data.get("balances", {})


def place_order(ticker: str, side: str, shares: int,
                order_type: str = "market", limit_price: float = None) -> dict:
    """Place a paper order.
    side: 'buy' | 'sell' | 'sell_short' | 'buy_to_cover'
    Returns dict with order_id and status.
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

    data = _post(f"/accounts/{TRADIER_SANDBOX_ACCOUNT}/orders", payload)
    order = data.get("order", {})
    return {
        "order_id": str(order.get("id", "")),
        "status":   order.get("status", "error"),
        "raw":      data,
    }


def cancel_order(order_id: str) -> bool:
    r = requests.delete(
        f"{TRADIER_SANDBOX_BASE}/accounts/{TRADIER_SANDBOX_ACCOUNT}/orders/{order_id}",
        headers=HEADERS,
        timeout=10
    )
    return r.status_code == 200


def get_positions() -> list:
    """All open positions in the paper account."""
    data = _get(f"/accounts/{TRADIER_SANDBOX_ACCOUNT}/positions")
    pos = data.get("positions", {}).get("position", [])
    if isinstance(pos, dict):
        pos = [pos]
    return pos or []


def shares_for_notional(price: float, notional_usd: float) -> int:
    """How many whole shares for a given notional."""
    return max(1, int(notional_usd // price))
