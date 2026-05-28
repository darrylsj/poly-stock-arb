"""Flask dashboard — Polymarket→Stock Arb Bot.

Run: python3 dashboard.py
Open: http://localhost:5050
"""
import datetime
from flask import Flask, render_template_string, jsonify
import store
import trader
import signal as sig_module

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html>
<head>
<title>Poly→Stock Arb Dashboard</title>
<meta http-equiv="refresh" content="60">
<style>
  body { font-family: monospace; background:#0d0d0d; color:#e0e0e0; padding:20px; }
  h1 { color:#00ff88; margin-bottom:4px; }
  .sub { color:#888; font-size:13px; margin-bottom:24px; }
  .panel { background:#181818; border:1px solid #333; border-radius:6px; padding:16px; margin-bottom:20px; }
  h2 { color:#aaa; font-size:14px; text-transform:uppercase; letter-spacing:1px; margin:0 0 12px 0; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { color:#666; text-align:left; padding:4px 8px; border-bottom:1px solid #222; }
  td { padding:5px 8px; border-bottom:1px solid #1a1a1a; }
  .up   { color:#00ff88; }
  .down { color:#ff4466; }
  .hold { color:#ffaa00; }
  .pnl-pos { color:#00ff88; }
  .pnl-neg { color:#ff4466; }
  .dim  { color:#555; }
  .stat { display:inline-block; margin-right:32px; }
  .stat-val { font-size:22px; font-weight:bold; }
  .stat-lbl { font-size:11px; color:#666; }
  .badge { display:inline-block; padding:2px 8px; border-radius:3px; font-size:11px; }
  .badge-open   { background:#1a3a1a; color:#00ff88; }
  .badge-closed { background:#1a1a2a; color:#4488ff; }
  .badge-shadow { background:#2a2a1a; color:#ffaa00; }
</style>
</head>
<body>
<h1>📊 Poly→Stock Arb</h1>
<div class="sub">Polymarket book imbalance → Tradier PAPER trades &nbsp;|&nbsp;
  Auto-refresh 60s &nbsp;|&nbsp; <span id="ts">{{ ts }}</span></div>

<!-- Account + Daily Stats -->
<div class="panel">
  <h2>Account (Paper)</h2>
  <div>
    {% for k, v in acct.items() %}
    <div class="stat">
      <div class="stat-val">{{ v }}</div>
      <div class="stat-lbl">{{ k }}</div>
    </div>
    {% endfor %}
    <div class="stat">
      <div class="stat-val {% if daily.net_pnl and daily.net_pnl > 0 %}pnl-pos{% elif daily.net_pnl and daily.net_pnl < 0 %}pnl-neg{% endif %}">
        ${{ "%.2f"|format(daily.net_pnl or 0) }}</div>
      <div class="stat-lbl">Today P&L ({{ daily.wins or 0 }}/{{ daily.trades or 0 }} wins)</div>
    </div>
  </div>
</div>

<!-- Live Signals -->
<div class="panel">
  <h2>Live Polymarket Signals</h2>
  <table>
    <tr><th>Ticker</th><th>Direction</th><th>Implied Prob</th><th>Book Depth</th><th>Signal</th></tr>
    {% for s in live_signals %}
    <tr>
      <td>{{ s.ticker }}</td>
      <td class="{{ s.direction or 'dim' }}">{{ (s.direction or '—').upper() }}</td>
      <td>{{ "%.1f%%"|format((s.implied_prob or 0)*100) }}</td>
      <td>${{ "%.0f"|format(s.total_depth or 0) }}</td>
      <td>
        {% if s.implied_prob and s.implied_prob >= 0.75 and (s.dominant_depth or 0) >= 300 %}
          <span class="badge badge-open">🔥 FIRE</span>
        {% elif s.implied_prob and s.implied_prob >= 0.65 %}
          <span class="badge badge-shadow">⚡ WATCH</span>
        {% else %}
          <span class="dim">—</span>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </table>
</div>

<!-- Open Positions -->
<div class="panel">
  <h2>Open Positions</h2>
  {% if open_pos %}
  <table>
    <tr><th>Ticker</th><th>Side</th><th>Shares</th><th>Entry</th><th>Current</th><th>Move</th><th>P&L</th><th>Signal Prob</th></tr>
    {% for p in open_pos %}
    <tr>
      <td><b>{{ p.ticker }}</b></td>
      <td class="{{ 'up' if p.direction == 'buy' else 'down' }}">{{ p.direction.upper() }}</td>
      <td>{{ p.shares }}</td>
      <td>${{ "%.2f"|format(p.entry_price) }}</td>
      <td>${{ "%.2f"|format(p.current_price or 0) }}</td>
      <td class="{{ 'pnl-pos' if (p.pct_move or 0) > 0 else 'pnl-neg' }}">
        {{ "%+.2f%%"|format((p.pct_move or 0)*100) }}</td>
      <td class="{{ 'pnl-pos' if (p.unrealized_pnl or 0) > 0 else 'pnl-neg' }}">
        ${{ "%+.2f"|format(p.unrealized_pnl or 0) }}</td>
      <td>{{ "%.0f%%"|format((p.poly_implied_prob or 0)*100) }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <div class="dim">No open positions</div>
  {% endif %}
</div>

<!-- Recent Signals Log -->
<div class="panel">
  <h2>Signal Log (last 30)</h2>
  <table>
    <tr><th>Time</th><th>Ticker</th><th>Dir</th><th>Prob</th><th>Depth</th><th>Fired</th><th>Reason</th></tr>
    {% for s in signal_log %}
    <tr>
      <td class="dim">{{ s.ts[11:16] }}</td>
      <td>{{ s.ticker }}</td>
      <td class="{{ s.direction or '' }}">{{ (s.direction or '—').upper() }}</td>
      <td>{{ "%.1f%%"|format((s.implied_prob or 0)*100) }}</td>
      <td>${{ "%.0f"|format(s.book_depth_usd or 0) }}</td>
      <td>{% if s.fired %}<span class="badge badge-open">✓</span>{% else %}<span class="dim">—</span>{% endif %}</td>
      <td class="dim">{{ s.skip_reason or '' }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<!-- Calibration Panel -->
<div class="panel">
  <h2>Calibration: Closed Trades</h2>
  <table>
    <tr><th>Date</th><th>Ticker</th><th>Side</th><th>Entry</th><th>Exit</th><th>Reason</th><th>P&L</th><th>Signal Prob</th></tr>
    {% for t in closed_trades %}
    <tr>
      <td class="dim">{{ t.entry_ts[:10] }}</td>
      <td>{{ t.ticker }}</td>
      <td>{{ t.direction.upper() }}</td>
      <td>${{ "%.2f"|format(t.entry_price) }}</td>
      <td>${{ "%.2f"|format(t.exit_price or 0) }}</td>
      <td class="dim">{{ t.exit_reason or '—' }}</td>
      <td class="{{ 'pnl-pos' if (t.realized_pnl or 0) > 0 else 'pnl-neg' }}">
        ${{ "%+.2f"|format(t.realized_pnl or 0) }}</td>
      <td>{{ "%.0f%%"|format((t.poly_implied_prob or 0)*100) }}</td>
    </tr>
    {% endfor %}
  </table>
</div>
</body>
</html>"""


@app.route("/")
def index():
    today = datetime.date.today().isoformat()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Account
    try:
        bal = trader.account_balances()
        margin = bal.get("margin", {}) or bal.get("pdt", {}) or {}
        acct = {
            "Cash": f"${float(bal.get('total_cash', 0)):,.2f}",
            "Equity": f"${float(bal.get('total_equity', 0)):,.2f}",
            "Buying Power": f"${float(margin.get('stock_buying_power', 0)):,.2f}",
        }
    except Exception:
        acct = {"Status": "Unavailable"}

    # Daily P&L
    daily_row = store.daily_summary(today)
    daily = {"trades": 0, "wins": 0, "net_pnl": 0.0}
    if daily_row:
        daily = dict(daily_row)

    # Live signals (last scan)
    live_signals = sig_module.scan_all()

    # Open positions enriched with current price
    open_pos = []
    for p in store.open_positions():
        p = dict(p)
        price = trader.get_price(p["ticker"])
        p["current_price"] = price
        if price:
            move = (price - p["entry_price"]) / p["entry_price"]
            if p["direction"] == "sell_short":
                move = -move
            p["pct_move"] = move
            p["unrealized_pnl"] = round(move * p["entry_price"] * p["shares"], 2)
        open_pos.append(p)

    # Signal log
    signal_log = [dict(s) for s in store.recent_signals(30)]

    # Closed trades
    with store.conn() as c:
        closed_trades = [dict(r) for r in c.execute(
            "SELECT * FROM positions WHERE status='closed' ORDER BY entry_ts DESC LIMIT 50"
        ).fetchall()]

    return render_template_string(HTML,
        ts=ts, acct=acct, daily=daily,
        live_signals=live_signals, open_pos=open_pos,
        signal_log=signal_log, closed_trades=closed_trades)


@app.route("/api/signals")
def api_signals():
    return jsonify(sig_module.scan_all())


@app.route("/api/positions")
def api_positions():
    return jsonify([dict(p) for p in store.open_positions()])


if __name__ == "__main__":
    store.init_db()
    app.run(host="0.0.0.0", port=5050, debug=False)
