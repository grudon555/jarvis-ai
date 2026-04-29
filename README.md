# ⚡ Jarvis AI

**Dein eigener KI-Assistent — kostenlos, lokal, auf deinem Computer.**

Jarvis ist wie ChatGPT, aber:
- 🏠 **Läuft auf deinem Mac** — deine Daten bleiben bei dir
- 💬 **Erreichbar über WhatsApp & Telegram** — einfach anschreiben
- 🧠 **Wird mit der Zeit klüger** — lernt und speichert Lösungen automatisch
- 💰 **Günstig** — nutzt lokale KI (Ollama) wann immer möglich

---

## 🚀 Installation (5 Minuten)

### Voraussetzungen

Du brauchst nur:
- Einen **Mac** (mit Apple Silicon oder Intel)
- **Python 3.9+** — prüfen mit: `python3 --version`
- Einen **Anthropic API Key** — kostenlos holen auf [console.anthropic.com](https://console.anthropic.com)

### Schritt 1 — Projekt herunterladen

```bash
git clone https://github.com/grudon555/jarvis-ai.git
cd jarvis-ai
```

### Schritt 2 — Automatisch installieren

```bash
bash setup.sh
```

Das Script installiert alles automatisch:
- Ollama (lokale KI)
- Alle Python-Pakete
- Lädt das KI-Modell herunter (~2 GB)
- Erstellt die Konfigurationsdatei

### Schritt 3 — Starten

```bash
./jarvis.sh start
```

Dann öffne deinen Browser und geh auf **http://localhost:8000** ✅

---

## 🎮 Bedienung

### Jarvis steuern

| Befehl | Was passiert |
|--------|-------------|
| `./jarvis.sh start` | Alles starten |
| `./jarvis.sh stop` | Alles stoppen |
| `./jarvis.sh restart` | Neu starten |
| `./jarvis.sh status` | Läuft alles? |
| `./jarvis.sh logs` | Live-Logs ansehen |

### Im Browser (http://localhost:8000)

- Einfach ins Textfeld schreiben und Enter drücken
- **⚙ Einstellungen** — API Keys, Modell, WhatsApp, Telegram alles konfigurierbar
- Gesprächsverlauf wird automatisch gespeichert

---

## 💬 WhatsApp einrichten

So kannst du Jarvis über WhatsApp anschreiben:

**1. Twilio-Konto erstellen (kostenlos)**
- Geh auf [twilio.com](https://www.twilio.com) → kostenlos registrieren
- Nach dem Login: **Account SID** und **Auth Token** kopieren

**2. WhatsApp Sandbox aktivieren**
- Im Twilio-Dashboard: **Messaging → Try it out → Send a WhatsApp message**
- Schicke die angezeigte Nachricht (z.B. `join apple-mango`) von deinem WhatsApp an `+1 415 523 8886`

**3. Webhook eintragen**
- Im Twilio-Dashboard: **Sandbox Settings**
- Feld **"WHEN A MESSAGE COMES IN"** → URL aus `./jarvis.sh start` eintragen

**4. Im Einstellungs-Dashboard konfigurieren**
- Browser öffnen: http://localhost:8000 → ⚙ Einstellungen → WhatsApp
- Account SID, Auth Token und deine Handynummer eintragen → Speichern

---

## ✈ Telegram einrichten

Noch einfacher als WhatsApp — und komplett kostenlos:

**1. Bot erstellen**
- Öffne Telegram, suche nach `@BotFather`
- Schreibe `/newbot`
- Gib einen Namen ein (z.B. `Mein Jarvis`)
- Gib einen Username ein (z.B. `mein_jarvis_bot`)
- Du bekommst einen **Token** — sieht so aus: `7123456789:AAF...`

**2. Token eintragen**
- Browser: http://localhost:8000 → ⚙ Einstellungen → Telegram
- Token einfügen → Speichern → Jarvis neu starten (`./jarvis.sh restart`)

**3. Fertig!**
- Öffne deinen neuen Bot in Telegram
- Schreib `/start` — Jarvis antwortet sofort

---

## ⚙ Einstellungen

Alle Einstellungen kannst du direkt im Browser ändern — **kein Bearbeiten von Dateien nötig**.

http://localhost:8000 → Klick auf **⚙ Einstellungen**

| Einstellung | Beschreibung |
|-------------|-------------|
| **Anthropic API Key** | Für Claude (Cloud-KI) |
| **Cloud Modell** | claude-sonnet (Standard), opus (stärker), haiku (schneller) |
| **Telegram Bot Token** | Für den Telegram-Bot |
| **WhatsApp / Twilio** | Account SID, Auth Token, Nummern |
| **Whisper Sprache** | Sprache für Spracherkennung (de, en, fr…) |

---

## 🧠 Wie Jarvis funktioniert

```
Deine Frage
    │
    ▼
┌─────────────────────────────────────┐
│  Skill-Datenbank                    │  ← Schon mal beantwortet?
│  (ähnliche Fragen aus der          │     Dann: gratis, sofort!
│   Vergangenheit)                    │
└──────────────┬──────────────────────┘
               │ Nein
               ▼
┌─────────────────────────────────────┐
│  SmartRouter                        │  ← Einfache Frage?
│  Einfach → Ollama (lokal, gratis)  │     Ollama antwortet
│  Komplex → Claude (Cloud)          │
└──────────────┬──────────────────────┘
               │ Komplex
               ▼
┌──────────────┬──────────────┬────────┐
│  Research    │  Coder       │ Direct │  ← Spezialisierte Agenten
│  Agent       │  Agent       │        │
└──────────────┴──────────────┴────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Analyst Agent                      │  ← Lösung gut genug zum
│  "Soll ich das als Skill speichern?"│    Speichern? → Nächste
└─────────────────────────────────────┘    Mal gratis!
```

**Ergebnis:** Je mehr du Jarvis nutzt, desto günstiger und schneller wird er.

---

## 🔌 Eigene Tools hinzufügen (Plugins)

Erstelle eine Datei `plugins/mein_tool.py`:

```python
from plugins import jarvis_tool

@jarvis_tool(
    name="wetter",
    description="Aktuelles Wetter für eine Stadt abrufen",
    params={
        "stadt": {
            "type": "string",
            "description": "Name der Stadt",
            "required": True,
        }
    },
)
def wetter(stadt: str) -> str:
    return f"Das Wetter in {stadt} ist sonnig, 22°C."
```

Jarvis lädt das Tool automatisch beim Start — kein weiterer Aufwand.

---

## 🐳 Mit Docker starten (Alternative)

Falls du Docker hast:

```bash
cp .env.example .env
# API Key in .env eintragen
docker compose up
```

Docker startet automatisch Ollama und Jarvis zusammen.

---

## ❓ Häufige Probleme

**„Ollama antwortet nicht"**
```bash
ollama serve
# oder
brew services start ollama
```

**„Server startet nicht"**
```bash
./jarvis.sh logs
# Zeigt dir was schiefgelaufen ist
```

**„Kein Modell gefunden"**
```bash
ollama pull llama3.2
```

**Tunnel-URL ändert sich nach jedem Neustart**
→ Normal — einfach neue URL in Twilio Sandbox Settings eintragen.
→ Für fixe URL: ngrok-Account erstellen (kostenlos auf ngrok.com).

---

## 📁 Projektstruktur

```
jarvis-ai/
├── setup.sh          ← Automatische Installation
├── jarvis.sh         ← Start / Stop / Status
├── server.py         ← Web Server + WhatsApp Webhook
├── main.py           ← Terminal-Version
│
├── agents/           ← KI-Agenten (Manager, Coder, Research, Analyst)
├── core/             ← Router, LLM, Bus, MCP
├── interface/        ← Web UI, WhatsApp, Telegram, Voice
├── plugins/          ← Eigene Tools hinzufügen
├── skills/           ← Automatisch gelernte Lösungen
└── static/           ← Web-Interface (index.html)
```

---

## 🤝 Mitmachen

1. Fork das Projekt auf GitHub
2. Neues Plugin erstellen in `plugins/dein_tool.py`
3. Pull Request erstellen

Fragen oder Probleme? → [GitHub Issues](https://github.com/grudon555/jarvis-ai/issues)

---

<div align="center">
  Made with ❤️ · Self-hosted · Open Source
</div>
