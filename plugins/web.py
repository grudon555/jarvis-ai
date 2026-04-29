"""Web search and URL fetching tools for Jarvis."""
from __future__ import annotations

import re
from typing import Optional

import requests
from plugins import jarvis_tool


@jarvis_tool(
    name="web_search",
    description="Sucht im Internet nach aktuellen Informationen. Gibt Titel, URL und Beschreibung der Top-Ergebnisse zurück.",
    params={
        "query": {
            "type": "string",
            "description": "Suchanfrage",
            "required": True,
        },
        "num_results": {
            "type": "integer",
            "description": "Anzahl der Ergebnisse (Standard: 5, max: 10)",
        },
    },
)
def web_search(query: str, num_results: int = 5) -> str:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return "Fehler: duckduckgo-search nicht installiert. Führe aus: pip install duckduckgo-search"

    num_results = min(max(1, num_results), 10)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        if not results:
            return f"Keine Ergebnisse für: {query}"
        lines = [f"🔍 Suchergebnisse für: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', 'Kein Titel')}**")
            lines.append(f"   {r.get('href', '')}")
            lines.append(f"   {r.get('body', '')[:200]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Suchfehler: {e}"


@jarvis_tool(
    name="fetch_url",
    description="Lädt den Inhalt einer Website herunter und gibt den sauberen Text zurück. Nützlich um Artikel, Dokumentationen oder Preise zu lesen.",
    params={
        "url": {
            "type": "string",
            "description": "Die vollständige URL der Website",
            "required": True,
        },
        "max_length": {
            "type": "integer",
            "description": "Maximale Textlänge in Zeichen (Standard: 3000)",
        },
    },
)
def fetch_url(url: str, max_length: int = 3000) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "Fehler: beautifulsoup4 nicht installiert. Führe aus: pip install beautifulsoup4"

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JarvisBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()

        # Get main content — prefer article/main, fallback to body
        main = soup.find("article") or soup.find("main") or soup.find("body")
        if not main:
            return "Konnte Seiteninhalt nicht lesen."

        text = main.get_text(separator="\n", strip=True)
        # Collapse blank lines
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if len(text) > max_length:
            text = text[:max_length] + f"\n\n… (gekürzt, {len(text)} Zeichen gesamt)"

        return f"📄 Inhalt von {url}:\n\n{text}"
    except requests.exceptions.Timeout:
        return f"Timeout: {url} hat nicht geantwortet."
    except requests.exceptions.HTTPError as e:
        return f"HTTP-Fehler {e.response.status_code}: {url}"
    except Exception as e:
        return f"Fehler beim Laden: {e}"


@jarvis_tool(
    name="get_current_weather",
    description="Aktuelles Wetter für eine Stadt abrufen (kostenlos, kein API Key nötig).",
    params={
        "city": {
            "type": "string",
            "description": "Stadtname, z.B. Wien, Berlin, Zürich",
            "required": True,
        },
    },
)
def get_current_weather(city: str) -> str:
    try:
        resp = requests.get(
            f"https://wttr.in/{requests.utils.quote(city)}?format=j1",
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        feels = current["FeelsLikeC"]
        humidity = current["humidity"]
        wind = current["windspeedKmph"]
        return (
            f"🌤 Wetter in {city}:\n"
            f"  Zustand:    {desc}\n"
            f"  Temperatur: {temp_c}°C (gefühlt {feels}°C)\n"
            f"  Luftfeuchte: {humidity}%\n"
            f"  Wind:       {wind} km/h"
        )
    except Exception as e:
        return f"Wetter konnte nicht abgerufen werden: {e}"
