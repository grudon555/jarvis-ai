#!/bin/bash
# ⚡ Jarvis AI — Control Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv/bin"
PIDFILE="$SCRIPT_DIR/.jarvis.pid"
LOG_SERVER="$SCRIPT_DIR/.jarvis_server.log"
LOG_TUNNEL="$SCRIPT_DIR/.jarvis_tunnel.log"
PORT=$(grep -E '^SERVER_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
PORT=${PORT:-8000}
TWILIO_SID=$(grep -E '^TWILIO_ACCOUNT_SID=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
TWILIO_TOKEN=$(grep -E '^TWILIO_AUTH_TOKEN=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')

# ── Colors & Styles ───────────────────────────────────────────────────────────
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

BLACK='\033[0;30m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[0;37m'

BRED='\033[1;31m'
BGREEN='\033[1;32m'
BYELLOW='\033[1;33m'
BBLUE='\033[1;34m'
BPURPLE='\033[1;35m'
BCYAN='\033[1;36m'
BWHITE='\033[1;37m'

# Box chars
TL='╔'; TR='╗'; BL='╚'; BR='╝'; H='═'; V='║'
TL2='┌'; TR2='┐'; BL2='└'; BR2='┘'; H2='─'; V2='│'
ML='╠'; MR='╣'; ML2='├'; MR2='┤'
DOT_ON='●'; DOT_OFF='○'

# ── Terminal width ────────────────────────────────────────────────────────────
TW=$(tput cols 2>/dev/null || echo 60)
[[ $TW -gt 70 ]] && TW=70
INNER=$((TW - 2))

# ── Spinner ───────────────────────────────────────────────────────────────────
SPINNER_PID=""
SPIN_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

spinner_start() {
  local msg="$1"
  (
    local i=0
    while true; do
      printf "\r  ${BPURPLE}${SPIN_FRAMES[$i]}${RESET}  ${WHITE}%s${RESET}   " "$msg"
      i=$(( (i+1) % 10 ))
      sleep 0.08
    done
  ) &
  SPINNER_PID=$!
}

spinner_stop() {
  local status="${1:-ok}"
  local msg="${2:-}"
  if [[ -n "$SPINNER_PID" ]]; then
    kill "$SPINNER_PID" 2>/dev/null
    wait "$SPINNER_PID" 2>/dev/null || true
    SPINNER_PID=""
  fi
  if [[ "$status" == "ok" ]]; then
    printf "\r  ${BGREEN}✓${RESET}  ${WHITE}%s${RESET}%*s\n" "$msg" 20 ""
  elif [[ "$status" == "warn" ]]; then
    printf "\r  ${BYELLOW}⚠${RESET}  ${YELLOW}%s${RESET}%*s\n" "$msg" 20 ""
  else
    printf "\r  ${BRED}✗${RESET}  ${RED}%s${RESET}%*s\n" "$msg" 20 ""
  fi
}

# ── Drawing helpers ───────────────────────────────────────────────────────────
hline() {
  local char="${1:-$H}"; local tl="${2:-$TL}"; local tr="${3:-$TR}"
  printf "${BPURPLE}%s" "$tl"
  printf "%0.s$char" $(seq 1 $INNER)
  printf "%s${RESET}\n" "$tr"
}

hline2() {
  local tl="${1:-$ML2}"; local tr="${2:-$MR2}"
  printf "${DIM}${PURPLE}%s" "$tl"
  printf "%0.s$H2" $(seq 1 $INNER)
  printf "%s${RESET}\n" "$tr"
}

row() {
  local content="$1"
  local vis_len
  # Strip ANSI for length calc
  local plain
  plain=$(echo -e "$content" | sed 's/\x1b\[[0-9;]*m//g')
  vis_len=${#plain}
  local pad=$(( INNER - vis_len ))
  [[ $pad -lt 0 ]] && pad=0
  printf "${BPURPLE}${V}${RESET} %b%*s ${BPURPLE}${V}${RESET}\n" "$content" "$pad" ""
}

empty_row() {
  printf "${BPURPLE}${V}${RESET}%*s${BPURPLE}${V}${RESET}\n" $((INNER+2)) ""
}

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
  echo ""
  hline "$H" "$TL" "$TR"
  empty_row
  row "  ${BPURPLE}⚡  J A R V I S   A I${RESET}${DIM}  ·  Multi-Agent Intelligence${RESET}"
  row "     ${DIM}${PURPLE}Self-hosted · Local-first · Always learning${RESET}"
  empty_row
  hline "$H" "$BL" "$BR"
  echo ""
}

# ── Status badge ──────────────────────────────────────────────────────────────
badge_ok()   { echo -e "${BGREEN}${DOT_ON} ONLINE${RESET}"; }
badge_off()  { echo -e "${RED}${DOT_OFF} OFFLINE${RESET}"; }
badge_act()  { echo -e "${BCYAN}${DOT_ON} AKTIV${RESET}"; }
badge_none() { echo -e "${DIM}${DOT_OFF} —${RESET}"; }

pad_to() {
  local s="$1" w="$2"
  local plain; plain=$(echo -e "$s" | sed 's/\x1b\[[0-9;]*m//g')
  local p=$(( w - ${#plain} ))
  [[ $p -lt 0 ]] && p=0
  echo -e "$s$(printf '%*s' $p '')"
}

# ── Helpers ───────────────────────────────────────────────────────────────────
pid_of()    { cat "$PIDFILE.$1" 2>/dev/null || echo ""; }
is_running() {
  local pid; pid=$(pid_of "$1")
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}
stop_pid() {
  local pid; pid=$(pid_of "$1")
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null
  fi
  rm -f "$PIDFILE.$1"
}

# ── START ─────────────────────────────────────────────────────────────────────
cmd_start() {
  print_banner

  # Header
  hline2 "$TL2" "$TR2"
  printf "${DIM}${PURPLE}${V2}${RESET} ${BWHITE}%-*s${RESET} ${DIM}${PURPLE}${V2}${RESET}\n" "$INNER" "  SYSTEM HOCHFAHREN"
  hline2 "$ML2" "$MR2"
  echo ""

  # Ollama
  if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    spinner_start "Ollama starten…"
    ollama serve > /tmp/ollama.log 2>&1 &
    echo $! > "$PIDFILE.ollama"
    sleep 4
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
      spinner_stop ok "Ollama gestartet"
    else
      spinner_stop warn "Ollama antwortet noch nicht"
    fi
  else
    printf "  ${BGREEN}✓${RESET}  ${WHITE}Ollama läuft bereits${RESET}\n"
  fi

  # Server
  if is_running "server"; then
    printf "  ${BYELLOW}⚠${RESET}  ${YELLOW}Server läuft bereits (PID $(pid_of server))${RESET}\n"
  else
    spinner_start "Jarvis Server starten (Port $PORT)…"
    "$VENV/python" server.py > "$LOG_SERVER" 2>&1 &
    echo $! > "$PIDFILE.server"
    sleep 5
    if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
      spinner_stop ok "Server bereit  →  http://localhost:$PORT"
    else
      spinner_stop err "Server-Start fehlgeschlagen"
      echo ""
      tail -5 "$LOG_SERVER" | while IFS= read -r line; do
        printf "     ${DIM}%s${RESET}\n" "$line"
      done
      exit 1
    fi
  fi

  # Tunnel
  if is_running "tunnel"; then
    local url; url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)
    printf "  ${BYELLOW}⚠${RESET}  ${YELLOW}Tunnel läuft bereits${RESET}  ${DIM}→ %s${RESET}\n" "$url"
  else
    spinner_start "Cloudflare Tunnel aufbauen…"
    cloudflared tunnel --url "http://localhost:$PORT" > "$LOG_TUNNEL" 2>&1 &
    echo $! > "$PIDFILE.tunnel"
    sleep 5
    local TUNNEL_URL
    TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)
    if [[ -n "$TUNNEL_URL" ]]; then
      spinner_stop ok "Tunnel aktiv"
    else
      spinner_stop warn "Tunnel-URL noch nicht verfügbar"
    fi
  fi

  echo ""
  # Final status box
  local TUNNEL_URL
  TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1)

  hline "$H" "$TL" "$TR"
  row "  ${BPURPLE}⚡  JARVIS LÄUFT${RESET}"
  hline "$H" "$ML" "$MR"
  row "  ${DIM}Web UI    ${RESET}  ${BCYAN}http://localhost:${PORT}${RESET}"
  [[ -n "$TUNNEL_URL" ]] && row "  ${DIM}Tunnel    ${RESET}  ${CYAN}${TUNNEL_URL}${RESET}"
  [[ -n "$TUNNEL_URL" ]] && row "  ${DIM}Webhook   ${RESET}  ${DIM}${TUNNEL_URL}/whatsapp/webhook${RESET}"
  hline "$H" "$BL" "$BR"
  echo ""
}

# ── STOP ──────────────────────────────────────────────────────────────────────
cmd_stop() {
  echo ""
  hline2 "$TL2" "$TR2"
  printf "${DIM}${PURPLE}${V2}${RESET} ${BWHITE}%-*s${RESET} ${DIM}${PURPLE}${V2}${RESET}\n" "$INNER" "  SYSTEM HERUNTERFAHREN"
  hline2 "$BL2" "$BR2"
  echo ""

  spinner_start "Tunnel beenden…";  sleep 0.5; stop_pid "tunnel"; spinner_stop ok "Tunnel gestoppt"
  spinner_start "Server beenden…";  sleep 0.5; stop_pid "server"; spinner_stop ok "Server gestoppt"
  spinner_start "Ollama beenden…";  sleep 0.5; stop_pid "ollama"; spinner_stop ok "Ollama gestoppt"
  lsof -ti:$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true

  echo ""
  printf "  ${DIM}Alle Prozesse beendet.${RESET}\n\n"
}

# ── STATUS ────────────────────────────────────────────────────────────────────
cmd_status() {
  echo ""
  hline "$H" "$TL" "$TR"
  row "  ${BPURPLE}⚡  JARVIS STATUS${RESET}"
  hline "$H" "$ML" "$MR"
  empty_row

  # Ollama
  local ollama_model="—" ollama_b
  if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    ollama_model=$(curl -sf http://localhost:11434/api/tags | python3 -c \
      "import sys,json; m=json.load(sys.stdin).get('models',[]); print(m[0]['name'].split(':')[0] if m else '(kein Modell)')" 2>/dev/null)
    ollama_b=$(badge_ok)
  else
    ollama_b=$(badge_off)
  fi
  row "  $(pad_to "${DIM}Ollama${RESET}" 18)  $(pad_to "${CYAN}${ollama_model}${RESET}" 22)  ${ollama_b}"

  # Server
  local server_b cloud_b skills_n tools_n
  if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
    server_b=$(badge_ok)
    local s
    s=$(curl -sf "http://localhost:$PORT/api/status" 2>/dev/null || echo "{}")
    skills_n=$(echo "$s" | python3 -c "import sys,json; print(json.load(sys.stdin).get('skills_count','—'))" 2>/dev/null)
    tools_n=$(echo "$s"  | python3 -c "import sys,json; print(json.load(sys.stdin).get('tools_count','—'))" 2>/dev/null)
    local cloud_ok
    cloud_ok=$(echo "$s" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cloud_ok',False))" 2>/dev/null)
    [[ "$cloud_ok" == "True" ]] && cloud_b=$(badge_act) || cloud_b=$(badge_off)
  else
    server_b=$(badge_off); skills_n="—"; tools_n="—"; cloud_b=$(badge_off)
  fi
  row "  $(pad_to "${DIM}Server${RESET}" 18)  $(pad_to "${CYAN}localhost:${PORT}${RESET}" 22)  ${server_b}"

  # Tunnel
  local tunnel_url tunnel_b
  tunnel_url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_TUNNEL" 2>/dev/null | head -1 || echo "")
  if is_running "tunnel" && [[ -n "$tunnel_url" ]]; then
    local short_url; short_url=$(echo "$tunnel_url" | sed 's|https://||' | cut -c1-28)
    tunnel_b=$(badge_ok)
    row "  $(pad_to "${DIM}Tunnel${RESET}" 18)  $(pad_to "${CYAN}${short_url}…${RESET}" 22)  ${tunnel_b}"
  else
    row "  $(pad_to "${DIM}Tunnel${RESET}" 18)  $(pad_to "${DIM}—${RESET}" 22)  $(badge_off)"
  fi

  # Telegram / WhatsApp
  local tg_token wa_sid
  tg_token=$(grep -E '^TELEGRAM_BOT_TOKEN=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
  wa_sid=$(grep -E '^TWILIO_ACCOUNT_SID=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
  if [[ -n "$tg_token" ]]; then
    local tg_name; tg_name=$(curl -sf "https://api.telegram.org/bot${tg_token}/getMe" | python3 -c \
      "import sys,json; print('@'+json.load(sys.stdin)['result']['username'])" 2>/dev/null || echo "@bot")
    row "  $(pad_to "${DIM}Telegram${RESET}" 18)  $(pad_to "${CYAN}${tg_name}${RESET}" 22)  $(badge_act)"
  else
    row "  $(pad_to "${DIM}Telegram${RESET}" 18)  $(pad_to "${DIM}kein Token${RESET}" 22)  $(badge_none)"
  fi
  if [[ -n "$wa_sid" ]]; then
    row "  $(pad_to "${DIM}WhatsApp${RESET}" 18)  $(pad_to "${CYAN}Twilio Sandbox${RESET}" 22)  $(badge_act)"
  else
    row "  $(pad_to "${DIM}WhatsApp${RESET}" 18)  $(pad_to "${DIM}nicht konfiguriert${RESET}" 22)  $(badge_none)"
  fi

  # Cloud
  row "  $(pad_to "${DIM}Cloud KI${RESET}" 18)  $(pad_to "${CYAN}claude-sonnet${RESET}" 22)  ${cloud_b}"

  empty_row
  hline "$H" "$ML" "$MR"
  row "  ${DIM}Skills: ${BPURPLE}${skills_n}${RESET}${DIM}   Tools: ${BPURPLE}${tools_n}${RESET}${DIM}   Web: ${BCYAN}localhost:${PORT}${RESET}"
  hline "$H" "$BL" "$BR"
  echo ""
}

# ── RESTART ───────────────────────────────────────────────────────────────────
cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

# ── LOGS ─────────────────────────────────────────────────────────────────────
cmd_logs() {
  local target="${1:-server}"
  echo ""
  hline2 "$TL2" "$TR2"
  printf "${DIM}${PURPLE}${V2}${RESET} ${BWHITE}%-*s${RESET} ${DIM}${PURPLE}${V2}${RESET}\n" "$INNER" "  LOGS — ${target^^}  (Ctrl+C zum Beenden)"
  hline2 "$BL2" "$BR2"
  echo ""
  case "$target" in
    server) tail -f "$LOG_SERVER" ;;
    tunnel) tail -f "$LOG_TUNNEL" ;;
    ollama) tail -f /tmp/ollama.log ;;
    *)      echo "Unbekannt: $target"; echo "Optionen: server | tunnel | ollama" ;;
  esac
}

# ── HELP ──────────────────────────────────────────────────────────────────────
cmd_help() {
  print_banner

  hline2 "$TL2" "$TR2"
  printf "${DIM}${PURPLE}${V2}${RESET} ${BWHITE}%-*s${RESET} ${DIM}${PURPLE}${V2}${RESET}\n" "$INNER" "  BEFEHLE"
  hline2 "$ML2" "$MR2"

  local cmds=(
    "start    │ Alles starten  (Ollama · Server · Tunnel)"
    "stop     │ Alles stoppen"
    "restart  │ Neustart"
    "status   │ Live-Übersicht aller Dienste"
    "logs     │ Server-Logs live ansehen"
    "logs tunnel │ Tunnel-Logs"
  )
  for c in "${cmds[@]}"; do
    local cmd; cmd=$(echo "$c" | cut -d'│' -f1 | xargs)
    local desc; desc=$(echo "$c" | cut -d'│' -f2 | xargs)
    printf "${DIM}${PURPLE}${V2}${RESET}   ${BPURPLE}%-12s${RESET}  ${DIM}%s${RESET}%*s${DIM}${PURPLE}${V2}${RESET}\n" "$cmd" "$desc" $(( INNER - 14 - ${#desc} - 2 )) ""
  done

  hline2 "$BL2" "$BR2"
  echo ""
  printf "  ${DIM}Tipp: Funktioniert in jedem Terminal-Fenster — kein cd nötig.${RESET}\n\n"
}

# ── Main ──────────────────────────────────────────────────────────────────────
CMD="${1:-help}"
case "$CMD" in
  start)            cmd_start ;;
  stop)             cmd_stop ;;
  restart)          cmd_restart ;;
  status)           cmd_status ;;
  logs)             cmd_logs "${2:-server}" ;;
  help|--help|-h)   cmd_help ;;
  *)
    echo ""
    printf "  ${RED}Unbekannter Befehl: %s${RESET}\n" "$CMD"
    echo ""
    cmd_help
    exit 1
    ;;
esac
