#!/bin/bash
# Jarvis — Automatische Installation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
info() { echo -e "${BLUE}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
step() { echo -e "\n${BOLD}${BLUE}[$1/6]${NC} $2"; }

echo ""
echo -e "${BOLD}${BLUE}⚡ Jarvis — Automatische Installation${NC}"
echo -e "────────────────────────────────────────"
echo ""

# ── Schritt 1: Python prüfen ─────────────────────────────────────────────────
step 1 "Python prüfen"
if ! command -v python3 &>/dev/null; then
  err "Python 3 nicht gefunden. Installiere es von https://www.python.org/downloads/"
fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 9 ]]; then
  err "Python $PY_VERSION zu alt. Mindestens Python 3.9 erforderlich."
fi
ok "Python $PY_VERSION gefunden"

# ── Schritt 2: Homebrew + Ollama ─────────────────────────────────────────────
step 2 "Ollama installieren (lokale KI)"
if ! command -v ollama &>/dev/null; then
  if ! command -v brew &>/dev/null; then
    warn "Homebrew nicht gefunden. Installiere Homebrew zuerst:"
    echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    read -r -p "Homebrew ist bereits installiert? (j/n): " ans
    [[ "$ans" != "j" ]] && err "Bitte zuerst Homebrew installieren und dann erneut ausführen."
  fi
  info "Installiere Ollama via Homebrew…"
  brew install ollama
  ok "Ollama installiert"
else
  ok "Ollama bereits installiert"
fi

# ── Schritt 3: Cloudflared ───────────────────────────────────────────────────
step 3 "Cloudflare Tunnel installieren (für WhatsApp/Telegram von außen)"
if ! command -v cloudflared &>/dev/null; then
  info "Installiere cloudflared…"
  brew install cloudflared
  ok "cloudflared installiert"
else
  ok "cloudflared bereits installiert"
fi

# ── Schritt 4: Python Umgebung ───────────────────────────────────────────────
step 4 "Python-Pakete installieren"
if [[ ! -d ".venv" ]]; then
  info "Erstelle virtuelle Umgebung…"
  python3 -m venv .venv
fi
info "Installiere Abhängigkeiten (kann 1-2 Minuten dauern)…"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
ok "Alle Pakete installiert"

# ── Schritt 5: Ollama Modell ─────────────────────────────────────────────────
step 5 "KI-Modell herunterladen (llama3.2 — ~2 GB)"
if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
  info "Starte Ollama…"
  ollama serve > /tmp/ollama_setup.log 2>&1 &
  sleep 4
fi
MODELS=$(curl -sf http://localhost:11434/api/tags | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "0")
if [[ "$MODELS" -eq 0 ]]; then
  info "Lade llama3.2 herunter…"
  ollama pull llama3.2
  ok "llama3.2 heruntergeladen"
else
  ok "Modell bereits vorhanden"
fi

# ── Schritt 6: Konfiguration ─────────────────────────────────────────────────
step 6 "Konfiguration erstellen"
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  ok ".env Datei erstellt"
  echo ""
  warn "WICHTIG: Trage deinen Anthropic API Key in .env ein!"
  echo -e "   Datei öffnen:  ${BLUE}open .env${NC}  oder  ${BLUE}nano .env${NC}"
  echo -e "   API Key holen: ${BLUE}https://console.anthropic.com${NC}"
  echo ""
  read -r -p "API Key jetzt eintragen? (j/n): " ans
  if [[ "$ans" == "j" ]]; then
    read -r -p "Anthropic API Key (sk-ant-...): " api_key
    if [[ -n "$api_key" ]]; then
      sed -i '' "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
      ok "API Key gespeichert"
    fi
  fi
else
  ok ".env bereits vorhanden"
fi

chmod +x jarvis.sh

# ── Fertig ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}⚡ Installation abgeschlossen!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Jarvis starten:   ${BOLD}./jarvis.sh start${NC}"
echo -e "  Jarvis stoppen:   ${BOLD}./jarvis.sh stop${NC}"
echo -e "  Status prüfen:    ${BOLD}./jarvis.sh status${NC}"
echo -e "  Web UI:           ${BLUE}http://localhost:8000${NC}"
echo ""
echo -e "  Einstellungen im Browser unter:"
echo -e "  ${BLUE}http://localhost:8000${NC} → ⚙ Einstellungen"
echo ""
