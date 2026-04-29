#!/bin/bash
# Jarvis — Start / Stop / Status / Restart
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv/bin"
PIDFILE="$SCRIPT_DIR/.jarvis.pid"
LOG_SERVER="$SCRIPT_DIR/.jarvis_server.log"
LOG_TUNNEL="$SCRIPT_DIR/.jarvis_tunnel.log"
TWILIO_SID=$(grep -E '^TWILIO_ACCOUNT_SID=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
TWILIO_TOKEN=$(grep -E '^TWILIO_AUTH_TOKEN=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
PORT=$(grep -E '^SERVER_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
PORT=${PORT:-8000}

# ── Colors ──────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }
info() { echo -e "${BLUE}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }

# ── Helpers ──────────────────────────────────────────────────────────────────────
pid_of() { cat "$PIDFILE.$1" 2>/dev/null || echo ""; }

is_running() {
  local pid
  pid=$(pid_of "$1")
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

stop_pid() {
  local name=$1
  local pid
  pid=$(pid_of "$name")
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && ok "Gestoppt: $name (PID $pid)"
  fi
  rm -f "$PIDFILE.$name"
}

# ── Commands ─────────────────────────────────────────────────────────────────────
cmd_start() {
  echo ""
  echo -e "${BLUE}⚡ Jarvis wird gestartet…${NC}"
  echo ""

  # Ollama
  if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    info "Starte Ollama…"
    ollama serve > /tmp/ollama.log 2>&1 &
    echo $! > "$PIDFILE.ollama"
    sleep 4
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
      ok "Ollama gestartet"
    else
      warn "Ollama antwortet noch nicht — läuft evtl. schon als Service"
    fi
  else
    ok "Ollama läuft bereits"
  fi

  # Jarvis Server
  if is_running "server"; then
    warn "Server läuft bereits (PID $(pid_of server))"
  else
    info "Starte Jarvis Server (Port $PORT)…"
    "$VENV/python" server.py > "$LOG_SERVER" 2>&1 &
    echo $! > "$PIDFILE.server"
    sleep 5
    if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
      ok "Server läuft — http://localhost:$PORT"
    else
      err "Server-Start fehlgeschlagen. Log: $LOG_SERVER"
      tail -10 "$LOG_SERVER"
      return 1
    fi
  fi

  # Cloudflare Tunnel
  if is_running "tunnel"; then
    local url
    url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)
    warn "Tunnel läuft bereits → $url"
  else
    info "Starte Cloudflare Tunnel…"
    cloudflared tunnel --url "http://localhost:$PORT" > "$LOG_TUNNEL" 2>&1 &
    echo $! > "$PIDFILE.tunnel"
    sleep 5
    local tunnel_url
    tunnel_url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)
    if [[ -n "$tunnel_url" ]]; then
      ok "Tunnel aktiv → $tunnel_url"
      # Update Twilio webhook automatically
      if [[ -n "$TWILIO_SID" && -n "$TWILIO_TOKEN" ]]; then
        local webhook="${tunnel_url}/whatsapp/webhook"
        local result
        result=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
          "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_SID/IncomingPhoneNumbers.json" \
          -u "$TWILIO_SID:$TWILIO_TOKEN" 2>/dev/null || echo "0")
        ok "WhatsApp Webhook URL: $webhook"
        echo -e "     ${YELLOW}→ Trage diese URL in Twilio Console ein (Messaging → Sandbox Settings)${NC}"
      fi
    else
      warn "Tunnel-URL noch nicht verfügbar — warte kurz und prüfe: $LOG_TUNNEL"
    fi
  fi

  echo ""
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN}⚡ Jarvis läuft!${NC}"
  echo -e "   Web UI:    ${BLUE}http://localhost:$PORT${NC}"
  TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)
  [[ -n "$TUNNEL_URL" ]] && echo -e "   Tunnel:    ${BLUE}$TUNNEL_URL${NC}"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

cmd_stop() {
  echo ""
  echo -e "${RED}⏹ Jarvis wird gestoppt…${NC}"
  echo ""
  stop_pid "tunnel"
  stop_pid "server"
  stop_pid "ollama"
  # Kill any leftover processes on port
  lsof -ti:$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
  echo ""
  ok "Alles gestoppt."
  echo ""
}

cmd_status() {
  echo ""
  echo -e "${BLUE}⚡ Jarvis Status${NC}"
  echo ""

  # Ollama
  if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    MODEL=$(curl -sf http://localhost:11434/api/tags | python3 -c "import sys,json; m=json.load(sys.stdin).get('models',[]); print(m[0]['name'].split(':')[0] if m else '(kein Modell)')" 2>/dev/null)
    ok "Ollama      $MODEL"
  else
    err "Ollama      offline"
  fi

  # Server
  if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
    STATUS=$(curl -sf "http://localhost:$PORT/api/status" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f\"cloud={'✓' if d['cloud_ok'] else '✗'}  skills={d['skills_count']}  tools={d['tools_count']}  wa={'✓' if d['whatsapp'] else '✗'}  tg={'✓' if d['telegram'] else '✗'}\")" 2>/dev/null)
    ok "Server      http://localhost:$PORT  [$STATUS]"
  else
    err "Server      offline"
  fi

  # Tunnel
  TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)
  if is_running "tunnel" && [[ -n "$TUNNEL_URL" ]]; then
    ok "Tunnel      $TUNNEL_URL"
  else
    err "Tunnel      offline"
  fi

  echo ""
}

cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

cmd_logs() {
  local target=${1:-server}
  case "$target" in
    server)  tail -f "$LOG_SERVER" ;;
    tunnel)  tail -f "$LOG_TUNNEL" ;;
    ollama)  tail -f /tmp/ollama.log ;;
    *)       echo "Unbekannt: $target (server|tunnel|ollama)" ;;
  esac
}

# ── Main ──────────────────────────────────────────────────────────────────────────
CMD=${1:-help}
case "$CMD" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-server}" ;;
  help|--help|-h)
    echo ""
    echo -e "${BLUE}⚡ Jarvis — Steuerung${NC}"
    echo ""
    echo "  ./jarvis.sh start      — Alles starten (Ollama + Server + Tunnel)"
    echo "  ./jarvis.sh stop       — Alles stoppen"
    echo "  ./jarvis.sh restart    — Neustart"
    echo "  ./jarvis.sh status     — Was läuft gerade?"
    echo "  ./jarvis.sh logs       — Server-Logs (live)"
    echo "  ./jarvis.sh logs tunnel — Tunnel-Logs"
    echo ""
    ;;
  *) err "Unbekannter Befehl: $CMD"; echo "Nutze: start | stop | restart | status | logs"; exit 1 ;;
esac
