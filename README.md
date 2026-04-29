# Jarvis-Core

A local-first AI assistant with a multi-agent architecture, automatic skill learning, voice I/O, and a built-in MCP server.

```
python main.py          # Terminal dashboard (Rich TUI)
python jarvis_mcp_server.py   # MCP server for Claude Desktop / VS Code
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Terminal UI (Rich)  ·  MCP Server  ·  Claude Desktop            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
               ┌───────────▼───────────┐
               │     ManagerAgent      │  SmartRouter: local vs cloud
               │   (Supervisor)        │  Skill registry check first
               └──┬────────┬────────┬──┘
                  │        │        │
           ┌──────▼─┐  ┌───▼──┐  ┌──▼──────┐
           │Research│  │Coder │  │Analyst  │  ← saves skills after complex tasks
           │Agent   │  │Agent │  │Agent   │
           └──────┬─┘  └───┬──┘  └──┬──────┘
                  │        │        │
        ┌─────────▼────────▼────────▼──────┐
        │   ChromaDB  ·  SkillRegistry      │
        │   PluginLoader  ·  MCPClient      │
        └───────────────────────────────────┘
```

**Routing logic** (in order of priority):

1. **Skill hit** (≥ 72% similarity in `/skills`) → LocalLLM, zero cloud cost
2. **SmartRouter LOCAL** (short/simple query) → Ollama, zero cloud cost  
3. **SmartRouter CLOUD** → Manager classifies → sub-agents → Claude synthesis  
4. **Analyst** evaluates the response → saves reusable Python function to `/skills`

---

## Setup

```bash
git clone https://github.com/yourname/jarvis-core
cd jarvis-core
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

brew services start ollama
ollama pull llama3.2   # or any model you prefer

python main.py
```

### Requirements

| Dependency | Purpose |
|---|---|
| `anthropic` | Claude API (cloud LLM) |
| `ollama` | Local LLM via Ollama |
| `langchain` / `langgraph` | Agent orchestration |
| `chromadb` | Embedding-based skill + document search |
| `faster-whisper` | Local speech-to-text |
| `elevenlabs` | Text-to-speech (streaming) |
| `sounddevice` | Microphone input + audio playback |
| `rich` | Terminal UI |
| `pydantic-settings` | Config via `.env` |

---

## Terminal UI Commands

| Command | Action |
|---|---|
| *(any text)* | Send message to Jarvis |
| `/voice` | Start voice recording (press Enter to stop) |
| `/skills` | List all learned skills |
| `/exit` | Quit |

---

## Plugin Development

Add your own tools to Jarvis in three steps.

### 1. Create a plugin file

Create `plugins/my_tool.py`:

```python
from plugins import jarvis_tool

@jarvis_tool(
    name="fetch_stock_price",
    description="Get the current stock price for a ticker symbol",
    params={
        "ticker": {
            "type": "string",
            "description": "Stock ticker symbol, e.g. AAPL",
            "required": True,
        },
        "currency": {
            "type": "string",
            "description": "Currency code (default: USD)",
        },
    },
)
def fetch_stock_price(ticker: str, currency: str = "USD") -> str:
    # Your implementation here
    import urllib.request, json
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    return f"{ticker}: {price} {currency}"
```

### 2. Rules for plugins

| Rule | Why |
|---|---|
| One `@jarvis_tool` per logical action | Tools are matched individually by the MCP client |
| Return a plain `str` | MCP protocol passes text content |
| No side-effects on import | `PluginLoader` imports the file on startup |
| Parameters use JSON Schema types: `string`, `integer`, `boolean`, `number` | Matches MCP `inputSchema` |
| No required external state | Tools must be self-contained |

### 3. Restart Jarvis

```bash
python main.py
# or for MCP server:
python jarvis_mcp_server.py
```

The `PluginLoader` auto-discovers every `*.py` file in `/plugins/` that doesn't start with `_`.

---

## Skill System (Automatic Learning)

After every complex cloud response, the **AnalystAgent** evaluates the solution:

- **Saves** → if the solution is generic, reusable, and non-trivial  
- **Skips** → one-off tasks, pure conversation, trivially simple code  

Saved skills appear in `skills/<name>.py` and are indexed by embedding similarity. On future similar requests, Jarvis uses the local skill instead of calling Claude — **zero cloud tokens**.

```bash
# View learned skills inside Jarvis
/skills

# Or inspect directly
ls skills/
cat skills/parse_csv_rows.py
```

**Difference between plugins and skills:**

| | Plugins | Skills |
|---|---|---|
| Written by | Developer | Jarvis (automatically) |
| Location | `/plugins/*.py` | `/skills/*.py` |
| Triggered | Always available | Similarity search |
| Format | `@jarvis_tool` decorated function | Plain Python function with header comments |

---

## MCP Server

Jarvis exposes all its tools as an MCP server, compatible with **Claude Desktop**, **VS Code Copilot**, and any MCP-compliant client.

### Connect to Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "jarvis": {
      "command": "/path/to/Jarvis/.venv/bin/python",
      "args": ["/path/to/Jarvis/jarvis_mcp_server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "OLLAMA_HOST": "http://localhost:11434"
      }
    }
  }
}
```

Restart Claude Desktop. You will see these tools available:

| Tool | Description |
|---|---|
| `ask_jarvis` | Full Jarvis pipeline — multi-agent, skill reuse, voice-capable |
| `list_directory` | List files in a directory |
| `read_file_excerpt` | Read first N lines of a file |
| `get_system_info` | macOS system information |
| `get_env_variable` | Read an environment variable |
| *(your plugins)* | Auto-discovered from `/plugins/` |

### Load external MCP servers

Create `mcp_servers.json` (see `mcp_servers.json.example`):

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/Documents"],
    "env": {}
  },
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..." }
  }
}
```

Jarvis will connect to each server on startup, import their tools, and expose them via its own MCP interface. Tools from external servers are prefixed with `[server_name]` in their descriptions.

---

## Project Structure

```
jarvis-core/
├── main.py                    # Terminal UI entry point
├── jarvis_mcp_server.py       # MCP server entry point
├── requirements.txt
├── .env.example
├── mcp_servers.json.example   # Template for external MCP servers
│
├── core/
│   ├── config.py              # pydantic-settings (.env)
│   ├── llm.py                 # LocalLLM (Ollama) + CloudLLM (Anthropic)
│   ├── router.py              # SmartRouter (score-based local/cloud classification)
│   ├── bus.py                 # AgentBus (message passing between agents)
│   ├── plugin_loader.py       # Auto-discovers /plugins/*.py
│   ├── mcp_server.py          # JSON-RPC 2.0 MCP server (no SDK required)
│   └── mcp_client.py          # Connect to external MCP servers
│
├── agents/
│   ├── manager.py             # ManagerAgent (supervisor, skill lookup, analyst trigger)
│   ├── coder.py               # CoderAgent (files, terminal, code generation)
│   ├── research.py            # ResearchAgent (ChromaDB document search)
│   └── analyst.py             # AnalystAgent (evaluates responses, saves skills)
│
├── skills/                    # Auto-generated learned skills
│   └── _registry.json         # Skill index
│
├── plugins/                   # Developer-added tools
│   ├── __init__.py            # @jarvis_tool decorator
│   ├── system_info.py         # Built-in: system info, env vars
│   └── file_utils.py          # Built-in: list_directory, read_file_excerpt
│
└── interface/
    ├── tui.py                 # Rich dashboard (thread-safe state + layout)
    ├── voice_in.py            # faster-whisper local speech recognition
    └── voice_out.py           # ElevenLabs streaming TTS
```

---

## Contributing

1. **New plugin** → add `plugins/your_tool.py` with `@jarvis_tool` decorator  
2. **New agent** → extend `agents/base.py`, register on the `AgentBus`  
3. **New skill** → just use Jarvis; the Analyst handles it automatically  

Open a pull request with a description of what problem the plugin solves and an example invocation.
