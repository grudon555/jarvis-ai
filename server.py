"""Jarvis server — Web UI + WhatsApp webhook + Telegram bot.

Start:
    python server.py

Web UI:    http://localhost:8000
WhatsApp:  expose via cloudflared/ngrok → set Twilio webhook to /whatsapp/webhook
Telegram:  set TELEGRAM_BOT_TOKEN in .env
"""
from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Form, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from core.bus import AgentBus
from core.config import settings
from core.llm import CloudLLM, LocalLLM
from core.plugin_loader import PluginLoader
from core.mcp_client import MCPClientManager
from agents import CoderAgent, ResearchAgent
from agents.manager import ManagerAgent
from agents.analyst import AnalystAgent
from skills.registry import SkillRegistry
from interface.conversation import ConversationManager
from interface.whatsapp import RateLimiter, WhatsAppClient, md_to_wa

_STATIC = Path(__file__).parent / "static"

# ── Global state (initialised in lifespan) ─────────────────────────────────────
_manager: Optional[ManagerAgent] = None
_wa: Optional[WhatsAppClient] = None
_conv: ConversationManager = ConversationManager()
_rate: RateLimiter = RateLimiter(settings.whatsapp_rate_limit)
_authorised: set[str] = set()

# ── Startup / shutdown ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _manager, _wa, _authorised

    bus = AgentBus()
    cloud_llm = CloudLLM()
    local_llm = LocalLLM()
    registry = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
    analyst = AnalystAgent(llm=cloud_llm, registry=registry)

    ResearchAgent(bus, project_root=".")
    CoderAgent(bus, llm=cloud_llm, cwd=".")
    _manager = ManagerAgent(
        bus, cloud_llm=cloud_llm, local_llm=local_llm,
        registry=registry, analyst=analyst,
    )

    loader = PluginLoader(plugins_dir="plugins")
    loader.load_all()

    mcp_client = MCPClientManager()
    mcp_client.load_from_config("mcp_servers.json")

    if settings.whatsapp_authorized_numbers:
        _authorised = {
            n.strip()
            for n in settings.whatsapp_authorized_numbers.split(",")
            if n.strip()
        }

    if WhatsAppClient.is_available() and settings.twilio_account_sid:
        _wa = WhatsAppClient(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_whatsapp_number,
        )
        print(f"✓ WhatsApp client ready — from {settings.twilio_whatsapp_number}")
    else:
        print("⚠ WhatsApp client unavailable (check TWILIO_* in .env)")

    # ── Telegram bot (optional) ───────────────────────────────────────────
    if settings.telegram_bot_token:
        _start_telegram_thread(_manager, _conv)

    print(f"✓ Web UI → http://localhost:{settings.server_port}")

    yield  # ← server runs here

    mcp_client.shutdown()


def _start_telegram_thread(manager: ManagerAgent, conv: ConversationManager) -> None:
    from interface.telegram import run_bot

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_bot(settings.telegram_bot_token, manager, conv))
        except Exception as e:
            print(f"⚠ Telegram bot error: {e}")

    t = threading.Thread(target=_run, name="telegram-bot", daemon=True)
    t.start()
    print("✓ Telegram bot starting…")


app = FastAPI(title="Jarvis WhatsApp Gateway", lifespan=lifespan)


# ── Webhook endpoint ────────────────────────────────────────────────────────────

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: str = Form("0"),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
):
    phone = From.replace("whatsapp:", "").strip()

    # ── Security ──────────────────────────────────────────────────────────────
    if _authorised and phone not in _authorised:
        return _twiml("")   # silent reject

    if not _rate.allow(phone):
        if _wa:
            _wa.send(phone, "⏸ Zu viele Nachrichten. Bitte kurz warten.")
        return _twiml("")

    if _wa is None or _manager is None:
        return PlainTextResponse("Service not ready", status_code=503)

    # ── Dispatch to background ────────────────────────────────────────────────
    background_tasks.add_task(
        _handle,
        phone=phone,
        body=Body.strip(),
        num_media=int(NumMedia or 0),
        media_url=MediaUrl0,
        media_type=MediaContentType0 or "",
    )
    return _twiml("")   # immediate empty response to Twilio


def _twiml(body: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'
    return Response(content=xml, media_type="application/xml")


# ── Message handler (runs in background thread) ────────────────────────────────

def _handle(
    phone: str,
    body: str,
    num_media: int,
    media_url: Optional[str],
    media_type: str,
) -> None:
    assert _wa and _manager

    # ── Built-in commands ──────────────────────────────────────────────────────
    if body.startswith("/"):
        _handle_command(phone, body.lower().split()[0], body)
        return

    # ── Voice note ─────────────────────────────────────────────────────────────
    text = body
    if num_media > 0 and media_url and "audio" in media_type:
        _wa.send(phone, "🎤 _Transkribiere…_")
        try:
            transcribed = _wa.transcribe_voice(
                media_url,
                whisper_model=settings.whisper_model,
                language=settings.whisper_language,
            )
        except Exception as e:
            _wa.send(phone, f"❌ Transkription fehlgeschlagen: {e}")
            return
        if not transcribed:
            _wa.send(phone, "❌ Keine Sprache erkannt.")
            return
        _wa.send(phone, f"🎤 _{transcribed}_")
        text = transcribed

    # ── Media without audio (image / document) ─────────────────────────────────
    elif num_media > 0 and media_url:
        text = f"{body}\n[Anhang empfangen: {media_type or 'unbekannter Typ'}]".strip()

    if not text:
        return

    # ── Build prompt with conversation history ──────────────────────────────────
    prompt = _conv.build_prompt(phone, text)

    # ── Run Jarvis ──────────────────────────────────────────────────────────────
    _wa.send(phone, "⏳")
    try:
        content, agent_log, meta = _manager.run(prompt)
    except Exception as e:
        _wa.send(phone, f"❌ Fehler: {str(e)[:300]}")
        return

    # ── Format + send response ──────────────────────────────────────────────────
    _wa.send(phone, md_to_wa(content))

    # ── Metadata notifications ─────────────────────────────────────────────────
    saved = meta.get("skill_saved")
    if saved:
        _wa.send(phone, f"💡 Neuer Skill gelernt: `{saved}`")

    hits = meta.get("skill_hits", [])
    if hits:
        _wa.send(phone, f"♻️ Skill wiederverwendet: `{', '.join(hits)}`")

    # ── Update conversation history ─────────────────────────────────────────────
    _conv.add_turn(phone, text, content)


# ── Command handlers ────────────────────────────────────────────────────────────

_HELP = """\
*Jarvis-Befehle*

/help      – diese Hilfe
/status    – Systemstatus
/skills    – gelernte Skills auflisten
/tools     – verfügbare Tools anzeigen
/reset     – Gesprächskontext löschen
/ping      – Verbindungstest

_Einfach schreiben oder Sprachnachricht senden – Jarvis antwortet._"""


def _handle_command(phone: str, cmd: str, full_body: str) -> None:
    assert _wa and _manager

    if cmd == "/help":
        _wa.send(phone, _HELP)

    elif cmd == "/ping":
        _wa.send(phone, "🟢 Jarvis online.")

    elif cmd == "/reset":
        _conv.reset(phone)
        _wa.send(phone, "🔄 Gesprächskontext gelöscht.")

    elif cmd == "/status":
        _wa.send(phone, _build_status())

    elif cmd == "/skills":
        from skills.registry import SkillRegistry
        reg = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
        all_s = reg.list_all()
        if not all_s:
            _wa.send(phone, "📚 Noch keine Skills gelernt.")
        else:
            lines = [f"*Gelernte Skills ({len(all_s)})*"]
            for s in all_s:
                lines.append(
                    f"• `{s['name']}` — {s['description'][:80]}  "
                    f"_(×{s.get('use_count', 0)})_"
                )
            _wa.send(phone, "\n".join(lines))

    elif cmd == "/tools":
        from core.plugin_loader import PluginLoader
        loader = PluginLoader(plugins_dir="plugins")
        loader.load_all()
        tools = loader.get_tools()
        if not tools:
            _wa.send(phone, "🔧 Keine Tools geladen.")
        else:
            lines = [f"*Verfügbare Tools ({len(tools)})*"]
            for name, tool in tools.items():
                lines.append(f"• `{name}` — {tool.description[:80]}")
            _wa.send(phone, "\n".join(lines))

    else:
        _wa.send(phone, f"Unbekannter Befehl: `{cmd}`\nTippe /help für eine Übersicht.")


def _build_status() -> str:
    from skills.registry import SkillRegistry
    from core.plugin_loader import PluginLoader

    reg = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
    loader = PluginLoader(plugins_dir="plugins")
    loader.load_all()

    try:
        from core.llm import LocalLLM
        llm = LocalLLM()
        model = llm.get_active_model().split(":")[0]
        ollama_status = f"✓ {model}"
    except Exception:
        ollama_status = "✗ offline"

    lines = [
        "*Jarvis Status*",
        f"Ollama    {ollama_status}",
        f"Cloud     {settings.cloud_model}",
        f"Skills    {reg.count} gelernt",
        f"Tools     {len(loader.get_tools())} geladen",
        f"Voice in  {'✓' if settings.whisper_model else '—'}",
        f"Voice out {'✓' if settings.elevenlabs_api_key else '—'}",
    ]
    return "\n".join(lines)


# ── Admin endpoint ──────────────────────────────────────────────────────────────

@app.get("/admin/status")
async def admin_status(request: Request):
    token = request.headers.get("X-Admin-Token", "")
    if settings.twilio_auth_token and token != settings.twilio_auth_token[:16]:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {
        "status": "ok",
        "whatsapp": _wa is not None,
        "authorized_numbers": list(_authorised) if _authorised else "all",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Web UI ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def web_ui():
    return FileResponse(_STATIC / "index.html")


@app.get("/api/status")
async def api_status():
    from core.plugin_loader import PluginLoader
    from skills.registry import SkillRegistry

    loader = PluginLoader(plugins_dir="plugins")
    loader.load_all()
    reg = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")

    ollama_ok, ollama_model = False, ""
    try:
        llm = LocalLLM()
        ollama_model = llm.get_active_model().split(":")[0]
        ollama_ok = True
    except Exception:
        pass

    cloud_ok = bool(settings.anthropic_api_key)

    return {
        "ollama_ok": ollama_ok,
        "ollama_model": ollama_model,
        "cloud_ok": cloud_ok,
        "cloud_model": settings.cloud_model,
        "skills_count": reg.count,
        "tools_count": len(loader.get_tools()),
        "whatsapp": _wa is not None,
        "telegram": bool(settings.telegram_bot_token),
    }


@app.get("/chat/stream")
async def chat_stream(message: str, session_id: str = "default"):
    if _manager is None:
        return PlainTextResponse("Service not ready", status_code=503)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_token(chunk: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("token", chunk))

    def _run():
        try:
            prompt = _conv.build_prompt(session_id, message)
            result = _manager.run(prompt, on_token=on_token)
            loop.call_soon_threadsafe(queue.put_nowait, ("done", result))
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))

    async def generate():
        fut = loop.run_in_executor(None, _run)
        content = ""
        try:
            while True:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=120)
                if kind == "token":
                    content += payload
                    yield f"data: {json.dumps({'token': payload})}\n\n"
                elif kind == "done":
                    result_content, _, meta = payload
                    _conv.add_turn(session_id, message, result_content)
                    agents_used = []
                    yield f"data: {json.dumps({'done': True, 'meta': {**meta, 'agents_used': agents_used}})}\n\n"
                    break
                elif kind == "error":
                    yield f"data: {json.dumps({'error': payload})}\n\n"
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'error': 'Timeout'})}\n\n"
        await fut

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/chat/reset")
async def chat_reset(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    _conv.reset(session_id)
    return {"ok": True}


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
        log_level="info",
    )
