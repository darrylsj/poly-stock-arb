# Poly→Stock Arb

Uses Polymarket prediction-market book imbalance as an alpha signal to enter
intraday long/short positions on Nasdaq stocks via Tradier's **paper** sandbox.
Zero real money is at risk — this is a calibration and research tool.

## Hypothesis

Polymarket runs active "Up or Down today?" markets for major US stocks (AAPL,
TSLA, NVDA, etc.). When a large fraction of bettors are pushing one side above
~75 cents, that crowd signal may lead the underlying stock's intraday move.
If the signal has edge, it can be exploited by buying (Up signal) or shorting
(Down signal) the stock and closing before end of day.

## Architecture

```
Polymarket CLOB  ──►  signal.py  ──►  bot.py  ──►  trader.py  ──►  Tradier sandbox
     (book depth)       (implied        (loop +        (paper
                         prob)          risk mgmt)      orders)
                                          │
                                       store.py  ──►  poly_arb.db (SQLite)
                                          │
                                     dashboard.py  ──►  http://localhost:5050
```

| File | Role |
|------|------|
| `config.py` | All parameters and env-var loading |
| `signal.py` | Polymarket Gamma + CLOB reader; returns implied prob per ticker |
| `trader.py` | Tradier sandbox API wrapper (quotes, orders, positions, balances) |
| `store.py` | SQLite schema and helpers (signals log, positions, daily P&L) |
| `bot.py` | Main loop — scans signals, fires paper orders, manages risk |
| `dashboard.py` | Flask dashboard with live signals, open positions, signal log |

## Quick start

### 1. Get Tradier sandbox credentials

Sign up free at https://developer.tradier.com, go to **Sandbox**, and grab
your API token and account ID.

### 2. Configure

```bash
cp .env.example .env
# Edit .env and fill in TRADIER_SANDBOX_TOKEN + TRADIER_SANDBOX_ACCOUNT
source .env
```

### 3. Install dependencies

```bash
pip install flask requests
```

### 4. Run the bot (shadow mode — no orders placed)

```bash
python3 bot.py
```

### 5. Enable paper orders

```bash
LIVE=1 python3 bot.py
```

### 6. Open the dashboard

```
http://localhost:5050
```

Run the dashboard separately alongside the bot:

```bash
python3 dashboard.py
```

## Signal logic

1. Every `POLL_INTERVAL_SEC` (default 120 s) during the signal window
   (`09:45–11:00 ET`), fetch the Polymarket CLOB book for each ticker's
   "up or down today?" market.
2. Compute the mid price of the **Up** token and the **Down** token.
3. If `implied_prob ≥ 0.75` **and** dominant-side book depth `≥ $300`,
   enter a paper position at `NOTIONAL_USD` (≈ $200).
4. Side: `buy` if Up signal, `sell_short` if Down signal.
5. Only one trade per ticker per day; max `MAX_POSITIONS` (3) concurrent.

## Risk management

| Parameter | Default | Notes |
|-----------|---------|-------|
| `PROFIT_TARGET_PCT` | 1.5 % | Close at profit |
| `STOP_LOSS_PCT` | 1.0 % | Close at loss |
| `HARD_CLOSE_ET` | 15:45 ET | Force-close all before end of day |
| `MAX_POSITIONS` | 3 | Concurrent position cap |
| `NOTIONAL_USD` | $200 | Per-trade size |

## Dashboard panels

- **Account (Paper)** — cash, equity, buying power from Tradier sandbox
- **Live Polymarket Signals** — real-time implied prob + book depth; 🔥 FIRE badge at ≥75 % / ≥$300
- **Open Positions** — current price, unrealised P&L, entry vs now
- **Signal Log** — last 30 signals with fired/skip reason
- **Calibration: Closed Trades** — realised P&L + Polymarket signal accuracy

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML dashboard |
| `GET /api/signals` | Live signal JSON for all tickers |
| `GET /api/positions` | Open positions JSON |

## Configuration reference

All parameters in `config.py`. Key env vars:

| Variable | Required | Description |
|----------|----------|-------------|
| `TRADIER_SANDBOX_TOKEN` | ✅ | Tradier sandbox API bearer token |
| `TRADIER_SANDBOX_ACCOUNT` | ✅ | Tradier sandbox account ID |
| `DB_PATH` | No | Override SQLite file path (default: `poly_arb.db`) |

## Research notes

- Polymarket stock direction markets typically open at ~50 % and drift as
  intraday information arrives. Signals are most useful after the 9:30 open
  flush, hence the `09:45` window start.
- At ≥75 ¢ implied, Polymarket aggregate prediction accuracy historically
  sits around 80–85 % (favourite-longshot bias corrected).
- The 1.5 % profit target is intentionally smaller than the 1 % stop to
  maintain positive EV even at ~55 % directional accuracy.
- Pre-market book is ~50/50 (wide spread, near-zero real depth). Don't
  interpret pre-market 50 % as a signal — it is noise.

## Disclaimer

This is experimental research software. The paper (sandbox) account places
zero real money. Do not connect a live brokerage account without thorough
backtesting and risk review.
