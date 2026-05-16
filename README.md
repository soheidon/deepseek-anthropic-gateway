# DeepSeek Anthropic Gateway

Thin proxy + GUI manager that routes Claude Desktop / Claude Code API requests to DeepSeek models via DeepSeek's Anthropic-compatible endpoint.

## Overview

A transparent proxy that forwards Anthropic Messages API requests to DeepSeek's Anthropic-compatible endpoint. Only the `model` field is rewritten — messages, thinking blocks, tool_use, tool_result, and streaming SSE pass through untouched.

The GUI management tool (Tauri v2 + React + TypeScript) provides start/stop control, config editing, log viewing, and API key management directly from a native Windows window.

## Verified Model Routes

| Claude Model | DeepSeek Model | Field Test |
|---|---|---|
| claude-sonnet-4-5 | deepseek-v4-pro | PASS (msgs=43, tools, stream) |
| claude-haiku-4-5-20251001 | deepseek-v4-flash | PASS (msgs=17, tools, stream) |

Both routes completed multi-turn tool-use conversations without `reasoning_content` or `Invalid model name` errors.

## Prerequisites

- **Python** 3.10+
- **Windows 10/11** (Japanese locale supported)
- DeepSeek API key

## Quick Start

### 1. Download

Download the latest `deepseek-anthropic-gateway.zip` from [Releases](https://github.com/soheidon/deepseek-anthropic-gateway/releases) and extract.

### 2. Setup

```powershell
setup.bat
```

Installs Python dependencies (fastapi, httpx, uvicorn).

### 3. Launch

Run `deepseek-anthropic-gateway-gui.exe`.

### 4. Set API Key

Go to the **API Key** tab, enter your DeepSeek API key, and click **Save**.
The key is persisted as a Windows user environment variable (`DEEPSEEK_API_KEY`).

### 5. Start Gateway

Click **Start Gateway** in the header. The proxy starts on `http://127.0.0.1:4000` as a background process (no console window).

### 6. Configure Claude Desktop

Go to the **Claude Desktop Setup** tab, copy the JSON config, and paste it into your Claude Desktop settings file. Auto-detected config files are listed — open the appropriate one and paste.

## Proxy-Only Usage (no GUI)

```powershell
pip install -r requirements.txt
setx DEEPSEEK_API_KEY "sk-..."
python proxy_server.py
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/models` | List visible models |
| POST | `/v1/messages` | Messages API (stream + non-stream) |
| POST | `/v1/messages/count_tokens` | Token counting |

## Configuration (config.json)

```json
{
  "model_map": {
    "claude-sonnet-4-6": "deepseek-v4-pro",
    "claude-sonnet-4-5": "deepseek-v4-pro",
    "claude-sonnet": "deepseek-v4-pro",
    "claude-opus-4-7": "deepseek-v4-pro",
    "claude-opus-4-5": "deepseek-v4-pro",
    "claude-opus-4": "deepseek-v4-pro",
    "claude-opus": "deepseek-v4-pro",
    "claude-haiku-4-5-20251001": "deepseek-v4-flash",
    "claude-haiku-4-5": "deepseek-v4-flash",
    "claude-haiku": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek-v4-flash"
  },
  "visible_models": [
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001"
  ],
  "default_model": "deepseek-v4-pro",
  "force_anthropic_version": null,
  "enable_cors": false,
  "upstream_url": "https://api.deepseek.com/anthropic"
}
```

| Key | Description |
|-----|-------------|
| `model_map` | Claude model name → DeepSeek model name mapping |
| `visible_models` | Models exposed via `GET /v1/models` |
| `default_model` | Fallback when model is not in map |
| `force_anthropic_version` | `null` = passthrough; set to override |
| `enable_cors` | Enable/disable CORS middleware |
| `upstream_url` | DeepSeek Anthropic-compatible endpoint URL |

> Japanese Windows requires saving `config.json` as **Shift-JIS**. Use the Gateway Settings tab in the GUI to toggle encoding.

## Project Structure

```
deepseek-anthropic-gateway/
├── README.md
├── SPEC.md                    Specification (Japanese)
├── LICENSE                    MIT License
├── config.json                Model map configuration
├── proxy_server.py            FastAPI proxy server
├── requirements.txt           Python dependencies
├── run.bat / run-logging.bat  Launch scripts
├── .gitignore
├── icon/                      Icon source (SVG, PNG)
├── scripts/
│   ├── phase0_probe.py        Pre-implementation compatibility probe
│   └── proxy_e2e_test.py      End-to-end proxy tests
├── gui/
│   ├── src/                   React frontend (TypeScript)
│   │   ├── components/        UI components (7 files)
│   │   ├── hooks/             Custom hooks (5 files)
│   │   └── i18n/              Japanese/English translations
│   ├── src-tauri/             Tauri backend (Rust)
│   │   ├── src/lib.rs         18 Tauri commands
│   │   └── Cargo.toml
│   └── package.json
├── Communication-Logs/        Proxy runtime logs
├── claude-log/                Development session logs
└── release/                   Built distributable
```

## Dev Build

### GUI

```bash
cd gui
npm install
npm run tauri build
```

Requires [Rust](https://rustup.rs/) stable toolchain and Node.js 24+.

### Dev Mode

```bash
# Terminal 1: Start proxy
$env:DEEPSEEK_API_KEY = "sk-..."
python proxy_server.py

# Terminal 2: Start GUI in dev mode
cd gui
npm run tauri dev
```

## Troubleshooting

### Port 4000 in use

```powershell
netstat -ano | findstr :4000
taskkill /PID <PID> /F
```

### `reasoning_content` error

If the log shows `reasoning_content must be passed back`, save the relevant log and file an issue.

### Invalid model name

Add the model name to `model_map` in `config.json`.

## License

MIT — see [LICENSE](LICENSE) for details.
