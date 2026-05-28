#!/bin/bash
# Run bot.py and dashboard.py as persistent background processes.
# Usage: bash run_bot.sh [start|stop|status]
DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_LOG=/tmp/poly-arb-bot.log
DASH_LOG=/tmp/poly-arb-dash.log
BOT_PID=/tmp/poly-arb-bot.pid
DASH_PID=/tmp/poly-arb-dash.pid

export TRADIER_SANDBOX_TOKEN=GaoXg4HrU7Lma1IxQuNdg3Fpazm6
export TRADIER_SANDBOX_ACCOUNT=VA75691022
export LIVE=1

start() {
  cd "$DIR"
  python3 bot.py >>"$BOT_LOG" 2>&1 & echo $! > "$BOT_PID"
  echo "Bot started — PID $(cat $BOT_PID)"
  python3 dashboard.py >>"$DASH_LOG" 2>&1 & echo $! > "$DASH_PID"
  echo "Dashboard started — PID $(cat $DASH_PID)  http://localhost:5050"
}

stop() {
  [ -f "$BOT_PID" ]  && kill "$(cat $BOT_PID)"  2>/dev/null && echo "Bot stopped"
  [ -f "$DASH_PID" ] && kill "$(cat $DASH_PID)" 2>/dev/null && echo "Dashboard stopped"
  rm -f "$BOT_PID" "$DASH_PID"
}

status() {
  if [ -f "$BOT_PID" ] && kill -0 "$(cat $BOT_PID)" 2>/dev/null; then
    echo "Bot running — PID $(cat $BOT_PID)"
  else
    echo "Bot NOT running"
  fi
  if [ -f "$DASH_PID" ] && kill -0 "$(cat $DASH_PID)" 2>/dev/null; then
    echo "Dashboard running — PID $(cat $DASH_PID)"
  else
    echo "Dashboard NOT running"
  fi
  echo "--- last 10 bot log lines ---"
  tail -10 "$BOT_LOG" 2>/dev/null | grep -v NotOpenSSL | grep -v "warnings.warn"
}

case "${1:-start}" in
  start)  stop 2>/dev/null; start ;;
  stop)   stop ;;
  status) status ;;
  *)      echo "Usage: $0 [start|stop|status]" ;;
esac
