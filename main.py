from __future__ import annotations

import threading
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt

from core.bus import AgentBus
from core.config import settings
from core.llm import CloudLLM, LocalLLM
from core.plugin_loader import PluginLoader
from core.mcp_client import MCPClientManager
from agents import ManagerAgent, CoderAgent, ResearchAgent
from agents.analyst import AnalystAgent
from skills.registry import SkillRegistry
from interface.tui import JarvisDisplay
from interface.voice_in import VoiceInput
from interface.voice_out import VoiceOutput

console = Console()


def _init_voice_in(display: JarvisDisplay) -> Optional[VoiceInput]:
    if not VoiceInput.is_available():
        display.set_status("voice_in", "sounddevice missing")
        return None
    try:
        vi = VoiceInput(
            model_size=settings.whisper_model,
            language=settings.whisper_language,
        )
        return vi
    except Exception as e:
        display.log(f"[yellow]Voice input init failed:[/yellow] {e}")
        return None


def _init_voice_out(display: JarvisDisplay) -> Optional[VoiceOutput]:
    if not VoiceOutput.is_available():
        display.set_status("voice", "elevenlabs missing")
        return None
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        display.set_status("voice", "no API key/voice ID")
        return None
    try:
        vo = VoiceOutput(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model,
        )
        display.set_status("voice", "ready")
        return vo
    except Exception as e:
        display.log(f"[yellow]Voice output init failed:[/yellow] {e}")
        return None


def _check_ollama(display: JarvisDisplay, local_llm: LocalLLM) -> None:
    try:
        model = local_llm.get_active_model()
        display.set_status("ollama", f"online · {model.split(':')[0]}")
    except Exception:
        display.set_status("ollama", "offline")


def _process(
    prompt: str,
    manager: ManagerAgent,
    display: JarvisDisplay,
    live: Live,
    voice_out: Optional[VoiceOutput],
) -> tuple[str, list, dict]:
    display.set_streaming("")
    stream_buf: list[str] = []

    def on_token(chunk: str) -> None:
        stream_buf.append(chunk)
        display.set_streaming("".join(stream_buf))
        live.update(display.get_layout())

    if voice_out:
        tts_callback = voice_out.stream_speak(on_token)
        content, agent_log, meta = manager.run(prompt, on_token=tts_callback)
        voice_out.flush()
    else:
        content, agent_log, meta = manager.run(prompt, on_token=on_token)

    return content, agent_log, meta


def _log_meta(meta: dict, agent_log: list, display: JarvisDisplay) -> None:
    for msg in agent_log:
        role = msg.sender.value
        display.log(f"→ [cyan]{role}[/cyan] responded")

    hits = meta.get("skill_hits", [])
    if hits:
        display.log(f"[green]★ skill hit:[/green] {', '.join(hits)}")

    saved = meta.get("skill_saved")
    if saved:
        display.log(f"[yellow]↓ learned:[/yellow] {saved}")

    reason = meta.get("analyst_reason")
    if reason and not saved:
        display.log(f"[dim]analyst: {reason}[/dim]")


def run() -> None:
    # ── Boot ──────────────────────────────────────────────────────────────────
    bus = AgentBus()
    cloud_llm = CloudLLM()
    local_llm = LocalLLM()
    registry = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
    analyst = AnalystAgent(llm=cloud_llm, registry=registry)

    ResearchAgent(bus, project_root=".")
    CoderAgent(bus, llm=cloud_llm, cwd=".")
    manager = ManagerAgent(
        bus, cloud_llm=cloud_llm, local_llm=local_llm,
        registry=registry, analyst=analyst,
    )

    # ── Plugins + external MCP ────────────────────────────────────────────────
    loader = PluginLoader(plugins_dir="plugins")
    n_plugins = loader.load_all()

    mcp_client = MCPClientManager()
    n_external = mcp_client.load_from_config("mcp_servers.json")
    if n_external:
        from plugins import _REGISTRY, JarvisTool
        for ext_name, ext_meta in mcp_client.tools.items():
            _REGISTRY[ext_name] = JarvisTool(
                name=ext_name,
                description=f"[{ext_meta['server']}] {ext_meta['description']}",
                params={},
                func=lambda __n=ext_name, **kw: mcp_client.call_tool(__n, kw),
                source="mcp_external",
            )

    display = JarvisDisplay(model=settings.cloud_model)
    display.set_status("skills", f"{registry.count} skills")

    all_tools = loader.get_tools()
    tool_label = f"{len(all_tools)} tools"
    if loader.errors:
        tool_label += f" ({len(loader.errors)} err)"
    display.set_status("tools", tool_label)
    for err in loader.errors:
        display.log(f"[red]Plugin error:[/red] {err}")

    voice_out = _init_voice_out(display)
    voice_in: Optional[VoiceInput] = None  # loaded lazily on /voice

    # ── Live UI ───────────────────────────────────────────────────────────────
    with Live(
        display.get_layout(),
        console=console,
        refresh_per_second=8,
        auto_refresh=True,
    ) as live:
        # Check Ollama status in background
        threading.Thread(
            target=_check_ollama, args=(display, local_llm), daemon=True
        ).start()

        live.update(display.get_layout())

        while True:
            try:
                raw = Prompt.ask("\n[bold cyan]You ▶[/bold cyan]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Bye.[/dim]")
                break

            prompt = raw.strip()
            if not prompt:
                continue

            # ── Built-in commands ──────────────────────────────────────────────
            if prompt.lower() in {"/exit", "exit", "quit", "bye"}:
                console.print("[dim]Bye.[/dim]")
                break

            if prompt.lower() == "/skills":
                skills = registry.list_all()
                if not skills:
                    display.log("No skills learned yet.")
                else:
                    for s in skills:
                        display.log(
                            f"[green]{s['name']}[/green]  "
                            f"[dim]{s['description']} (×{s.get('use_count', 0)})[/dim]"
                        )
                live.update(display.get_layout())
                continue

            if prompt.lower() in {"/voice", "/v"}:
                if voice_in is None:
                    voice_in = _init_voice_in(display)
                if voice_in is None:
                    display.log("[red]Voice input not available.[/red]")
                    live.update(display.get_layout())
                    continue

                display.set_recording(True)
                display.log("🎤 Recording… press Enter to stop")
                live.update(display.get_layout())

                voice_in.start_recording()
                try:
                    input()  # wait for Enter
                except (KeyboardInterrupt, EOFError):
                    pass

                display.set_recording(False)
                live.update(display.get_layout())

                transcription = voice_in.stop_and_transcribe()
                if not transcription:
                    display.log("[dim]No speech detected.[/dim]")
                    live.update(display.get_layout())
                    continue

                display.log(f"🎤 Transcribed: [cyan]{transcription}[/cyan]")
                prompt = transcription

            # ── Process prompt ─────────────────────────────────────────────────
            display.add_message("you", prompt)
            display.log(f"▶ [cyan]{prompt[:60]}{'…' if len(prompt) > 60 else ''}[/cyan]")
            live.update(display.get_layout())

            try:
                content, agent_log, meta = _process(
                    prompt, manager, display, live, voice_out
                )
            except RuntimeError as e:
                display.log(f"[red]Error:[/red] {e}")
                display.set_streaming(None)
                live.update(display.get_layout())
                continue
            except Exception as e:
                display.log(f"[red]{type(e).__name__}:[/red] {e}")
                display.set_streaming(None)
                live.update(display.get_layout())
                continue

            display.add_message("jarvis", content)
            _log_meta(meta, agent_log, display)
            live.update(display.get_layout())


if __name__ == "__main__":
    run()
