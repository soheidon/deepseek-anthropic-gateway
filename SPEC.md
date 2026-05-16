# SPEC: DeepSeek Anthropic Gateway / 仕様書

## 日本語

### 概要

DeepSeek API の Anthropic 互換エンドポイントを Claude Desktop / Claude Code Desktop から利用するための薄型プロキシ + GUI 管理ツール。

### 背景

Claude Desktop / Claude Code Desktop は Anthropic Messages API (`/v1/messages`) に直接リクエストを送る。これを DeepSeek の Anthropic 互換エンドポイントに振り向けることで、DeepSeek モデルを Anthropic クライアントから透過的に利用可能にする。

#### 解決する問題

- Claude Desktop 側のモデル名バリデーション
- LiteLLM の Anthropic→OpenAI 変換による情報ロス
- `claude-haiku-4-5-20251001` などの未登録モデル名問題

#### 既知の制限

- DeepSeek Anthropic 互換 API が thinking block を完全に扱えない場合がある
- `tool_use` / `tool_result` / streaming SSE の互換性が不十分な場合がある

### アーキテクチャ

```
Claude Desktop / Claude Code
       │
       ▼
proxy_server.py (127.0.0.1:4000)
       │
       │ model フィールドのみ書き換え
       │ 他は完全透過転送（messages / thinking / tool_use / tool_result / SSE）
       ▼
DeepSeek Anthropic-compatible API (api.deepseek.com/anthropic)
```

#### 設計方針

- **薄型プロキシ**: model フィールドの書換え以外は一切手を加えない。SSE もパースせずバイト単位で透過転送。
- **ロスレス転送**: メッセージ本文やツール呼び出し、thinking block を一切加工しない。
- **Windows ネイティブ GUI**: Tauri v2 + React + TypeScript。バックエンドは Rust、フロントエンドは Vite + React 19。

### GUI 管理ツール

Tauri v2 + React + TypeScript 製。4タブ構成。

```
┌──────────────────────────────────────────┐
│  DeepSeek Anthropic Gateway Manager      │
│  [Gateway: Running] [起動/停止] [EN|JA]  │
├──────────────────────────────────────────┤
│  Dashboard │ Gateway設定 │ Claude設定 │ APIキー │
├──────────────────────────────────────────┤
│  Status      │  最新ログ                 │
│  - Port 4000 │  - ログ切替              │
│  - APIキー   │  - 新規ログ              │
│  - URL       │  - Pro/Flash 集計        │
└──────────────────────────────────────────┘
```

| タブ | 機能 |
|------|------|
| Dashboard | Port 4000 状態、APIキー設定状態、Gateway URL、最新ログ表示、Pro/Flash 使用回数集計 |
| Gateway Settings | config.json の直接編集、UTF-8/Shift-JIS エンコード切替、保存/再読込 |
| Claude Desktop Setup | 設定JSONの表示とクリップボードコピー、設定ファイル自動検出、手動フォルダ参照 |
| API Key | DEEPSEEK_API_KEY の設定（Windows ユーザー環境変数に setx で永続保存） |

#### プロキシプロセス管理

- **起動**: `start_proxy` コマンドが `python proxy_server.py` をバックグラウンドで spawn。`CREATE_NO_WINDOW` フラグによりコンソールウィンドウは表示されない。stdout/stderr は `Communication-Logs/uvicorn-stdout-stderr.log` にリダイレクト。起動後ポート 4000 を最大 8 秒間 300ms 間隔でポーリングし、listen を確認。
- **停止**: `stop_proxy` コマンドが管理中の子プロセスを kill + wait。停止後ポート 4000 の開放を確認。
- **状態監視**: 3 秒間隔で `proxy_status` をポーリングし、予期せぬプロセス終了を検知。

### Tauri コマンド一覧

| # | コマンド名 | 種別 | 説明 |
|---|-----------|------|------|
| 1 | `check_health` | async | `GET http://127.0.0.1:4000/health` でプロキシ死活確認 |
| 2 | `check_gateway_status` | sync | ポート 4000 の listen 状態 + 管理子プロセスの生存確認 |
| 3 | `check_api_key` | sync | `DEEPSEEK_API_KEY` 環境変数の設定有無を返す |
| 4 | `set_env_api_key` | sync | `setx` コマンドで API キーをユーザー環境変数に永続保存 |
| 5 | `get_port_4000_process` | sync | `netstat` でポート 4000 を listen しているプロセスの PID を取得 |
| 6 | `read_config` | sync | `config.json` をパースして返す |
| 7 | `read_config_raw` | sync | `config.json` を生テキストで読み取り、エンコーディング自動判定 |
| 8 | `write_config` | sync | `config.json` を指定エンコーディング（UTF-8 / Shift-JIS）で保存 |
| 9 | `read_latest_log` | sync | `Communication-Logs/` 内の最新ログファイルを読み取り |
| 10 | `read_log` | sync | 指定ログファイルを読み取り（パストラバーサル対策あり） |
| 11 | `list_logs` | sync | `Communication-Logs/` 内のログファイル一覧を返す |
| 12 | `create_new_log` | sync | 新しい空ログファイルを作成 |
| 13 | `open_logs_folder` | sync | `Communication-Logs/` をエクスプローラで開く |
| 14 | `open_path` | sync | 任意パスをエクスプローラで開く（`%ENV_VAR%` 展開対応） |
| 15 | `find_claude_configs` | sync | Claude Desktop 設定ファイルを既知のパスから自動検出 |
| 16 | `start_proxy` | sync | Python プロキシを起動、ポート listen を確認 |
| 17 | `stop_proxy` | sync | 管理中の Python プロキシを停止、ポート開放を確認 |
| 18 | `proxy_status` | sync | 管理子プロセスの生存状態を返す |

全コマンドとも `CREATE_NO_WINDOW` (`0x08000000`) フラグ付きで外部プロセスを起動し、コンソールウィンドウが表示されないよう制御している。

### プロキシサーバー (proxy_server.py)

#### エンドポイント

| Method | Path | 動作 |
|--------|------|------|
| GET | `/health` | 死活確認、`{"status": "ok", "upstream": "..."}` を返す |
| GET | `/v1/models` | `visible_models` に列挙されたモデル名のみ返す |
| POST | `/v1/messages` | `model` を書換え後 upstream へ転送、stream / non-stream 両対応 |
| POST | `/v1/messages/count_tokens` | `model` を書換え後 upstream へ転送 |

#### モデル名書換え

`config.json` の `model_map` に従い、リクエストの `model` フィールドを DeepSeek 実モデル名に変換。マップにない場合は `default_model` にフォールバック。

#### モデルマップ（現在）

```json
{
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
}
```

Pro 系（Sonnet/Opus）は `deepseek-v4-pro`、Flash 系（Haiku）は `deepseek-v4-flash` にマップ。生の DeepSeek モデル名もパススルー可能。

#### visible_models

`GET /v1/models` で公開するモデル名。Claude Desktop のバリデーション警告を回避するため、Claude 風名のみに絞っている。

```json
["claude-sonnet-4-6", "claude-sonnet-4-5", "claude-opus-4-7", "claude-haiku-4-5-20251001"]
```

#### SSE 透過転送

httpx `client.stream()` で upstream から SSE イベントをバイト単位で受信し、Starlette `StreamingResponse` でそのまま返す。パース・再構築は行わない。

#### ログ

- 実行時ログ: `Communication-Logs/proxy-YYYY-MM-DD.log`（日付単位でローテート）
- 起動時ログ: `Communication-Logs/uvicorn-stdout-stderr.log`
- API キーは `RedactingFormatter` でマスク済み
- 会話内容は含まない（モデル名・stream 有無・メッセージ数のみ記録）

#### エンコーディング

日本語 Windows では `config.json` を Shift-JIS で扱う必要がある。プロキシ起動時は UTF-8 → UTF-8 BOM → Shift-JIS → cp932 の順にフォールバック。GUI の Gateway Settings タブでエンコーディング切替 + 直接編集が可能。

#### HTTP クライアント

`httpx.AsyncClient`（遅延シングルトン）:
- 接続タイムアウト: 30 秒
- 読み取りタイムアウト: 300 秒
- 書き込みタイムアウト: 60 秒
- プールタイムアウト: 30 秒

### config.json リファレンス

```json
{
  "model_map": { "...": "..." },
  "visible_models": [ "..." ],
  "default_model": "deepseek-v4-pro",
  "force_anthropic_version": null,
  "enable_cors": false,
  "upstream_url": "https://api.deepseek.com/anthropic"
}
```

| キー | 型 | 説明 |
|------|-----|------|
| `model_map` | object | Claude モデル名 → DeepSeek 実モデル名のマッピング |
| `visible_models` | string[] | `GET /v1/models` で公開するモデル名一覧 |
| `default_model` | string | マップにないモデル名のフォールバック先 |
| `force_anthropic_version` | string\|null | null 時はリクエストの `anthropic-version` ヘッダをそのまま転送。設定時は強制上書き |
| `enable_cors` | boolean | CORS ミドルウェアの有効/無効 |
| `upstream_url` | string | DeepSeek Anthropic 互換 API のベース URL |

### Claude Desktop 設定

```json
{
  "inferenceProvider": "gateway",
  "inferenceGatewayBaseUrl": "http://127.0.0.1:4000",
  "inferenceGatewayApiKey": "sk-local-gateway",
  "inferenceGatewayAuthScheme": "bearer",
  "inferenceModels": [
    {
      "name": "claude-sonnet-4-5",
      "labelOverride": "DeepSeek V4 Pro via Gateway"
    },
    {
      "name": "claude-haiku-4-5-20251001",
      "labelOverride": "DeepSeek V4 Flash via Gateway"
    }
  ]
}
```

設定ファイルの場所（Windows）:
- `%APPDATA%\Claude\claude_desktop_config.json`
- `%USERPROFILE%\.claude\settings.json`
- `%LOCALAPPDATA%\Claude-3p\configLibrary\`

GUI の Claude Desktop Setup タブで自動検出・クリップボードコピーが可能。

### 実地テスト結果

| 経路 | モデル | stream | tools | msgs | 結果 |
|------|--------|--------|-------|------|------|
| Pro | claude-sonnet-4-5 → deepseek-v4-pro | ✓ | ✓ | 43 | PASS |
| Flash | claude-haiku-4-5-20251001 → deepseek-v4-flash | ✓ | ✓ | 17 | PASS |

両経路ともツール利用を含む長めの会話が最後まで完了。`reasoning_content` エラー・`Invalid model name` エラーは発生していない。

### 事前検証

DeepSeek Anthropic 互換 API の互換性を実装前に検証。全項目 PASS。

| # | 項目 | 結果 | 詳細 |
|---|------|------|------|
| 1 | non-stream `/v1/messages` | PASS | 200, "hello" |
| 2 | stream=true SSE 形式 | PASS | Anthropic SSE 形式, 全 7 種 event type |
| 3 | thinking block | PASS | ['thinking', 'text'], reasoning_content 混入なし |
| 4 | 2nd turn pass-back | PASS | reasoning_content エラーなし |
| 5 | tool_use block | PASS | ['thinking', 'tool_use'], stop_reason=tool_use |
| 6 | tool_result 2nd turn | PASS | tool_result 使用応答成功 |
| 7 | count_tokens | PASS | input_tokens=10 |
| 8 | header handling | PASS | anthropic-beta 未知値も 200 |

---

## English

### Overview

A thin proxy + GUI management tool that routes Claude Desktop / Claude Code API requests through DeepSeek's Anthropic-compatible endpoint.

### Background

Claude Desktop / Claude Code sends requests directly to the Anthropic Messages API (`/v1/messages`). By routing these through DeepSeek's Anthropic-compatible endpoint, DeepSeek models can be used transparently from Anthropic clients.

#### Problems Solved

- Claude Desktop model name validation
- Information loss from LiteLLM Anthropic→OpenAI conversion
- Unregistered model names such as `claude-haiku-4-5-20251001`

#### Known Limitations

- DeepSeek Anthropic-compatible API may not fully support thinking blocks in all cases
- `tool_use` / `tool_result` / streaming SSE compatibility may be incomplete in edge cases

### Architecture

```
Claude Desktop / Claude Code
       │
       ▼
proxy_server.py (127.0.0.1:4000)
       │
       │ Rewrites only the model field
       │ Everything else passes through untouched
       │ (messages / thinking / tool_use / tool_result / SSE)
       ▼
DeepSeek Anthropic-compatible API (api.deepseek.com/anthropic)
```

#### Design Principles

- **Thin proxy**: Nothing is modified except the `model` field. SSE events are forwarded byte-for-byte without parsing or reconstruction.
- **Lossless forwarding**: Message bodies, tool calls, and thinking blocks pass through unmodified.
- **Windows-native GUI**: Tauri v2 + React + TypeScript. Rust backend, Vite + React 19 frontend.

### GUI Manager

Built with Tauri v2 + React + TypeScript. Four-tab layout.

```
┌──────────────────────────────────────────┐
│  DeepSeek Anthropic Gateway Manager      │
│  [Gateway: Running] [Start/Stop] [EN|JA] │
├──────────────────────────────────────────┤
│  Dashboard │ Settings │ ClaudeSetup │ API Key │
├──────────────────────────────────────────┤
│  Status      │  Latest Log               │
│  - Port 4000 │  - Log switcher           │
│  - API Key   │  - New log                │
│  - URL       │  - Pro/Flash counts       │
└──────────────────────────────────────────┘
```

| Tab | Function |
|-----|----------|
| Dashboard | Port 4000 status, API key status, Gateway URL, latest log viewer, Pro/Flash usage counters |
| Gateway Settings | Raw config.json editor, UTF-8/Shift-JIS encoding toggle, save/reload |
| Claude Desktop Setup | Config JSON display + clipboard copy, auto-detect config files, manual folder browse |
| API Key | Set DEEPSEEK_API_KEY (persisted via `setx` to Windows user environment variable) |

#### Proxy Process Management

- **Start**: The `start_proxy` command spawns `python proxy_server.py` in the background. The `CREATE_NO_WINDOW` flag prevents any console window from appearing. stdout/stderr are redirected to `Communication-Logs/uvicorn-stdout-stderr.log`. After spawning, port 4000 is polled every 300ms for up to 8 seconds to confirm the proxy is listening.
- **Stop**: The `stop_proxy` command kills the managed child process, waits for it to exit, and verifies port 4000 is released.
- **Status monitoring**: The frontend polls `proxy_status` every 3 seconds to detect unexpected process termination.

### Tauri Commands

| # | Command | Type | Description |
|---|---------|------|-------------|
| 1 | `check_health` | async | Proxies `GET http://127.0.0.1:4000/health` |
| 2 | `check_gateway_status` | sync | Checks port 4000 listen state + managed child process liveness |
| 3 | `check_api_key` | sync | Returns whether `DEEPSEEK_API_KEY` environment variable is set |
| 4 | `set_env_api_key` | sync | Persists API key via `setx` to user environment variable |
| 5 | `get_port_4000_process` | sync | Gets PID of process listening on port 4000 via `netstat` |
| 6 | `read_config` | sync | Reads and parses `config.json` |
| 7 | `read_config_raw` | sync | Reads `config.json` as raw text with auto encoding detection |
| 8 | `write_config` | sync | Saves `config.json` with specified encoding (UTF-8 / Shift-JIS) |
| 9 | `read_latest_log` | sync | Reads the latest log file from `Communication-Logs/` |
| 10 | `read_log` | sync | Reads a specific log file by name (path traversal safe) |
| 11 | `list_logs` | sync | Lists all log files in `Communication-Logs/` |
| 12 | `create_new_log` | sync | Creates a new empty log file |
| 13 | `open_logs_folder` | sync | Opens `Communication-Logs/` in Explorer |
| 14 | `open_path` | sync | Opens an arbitrary path in Explorer (supports `%ENV_VAR%` expansion) |
| 15 | `find_claude_configs` | sync | Auto-discovers Claude Desktop config files from known paths |
| 16 | `start_proxy` | sync | Starts the Python proxy and confirms port listen |
| 17 | `stop_proxy` | sync | Stops the managed Python proxy and confirms port release |
| 18 | `proxy_status` | sync | Returns the managed child process liveness |

All commands that spawn external processes use the `CREATE_NO_WINDOW` (`0x08000000`) flag to suppress console windows.

### Proxy Server (proxy_server.py)

#### Endpoints

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/health` | Health check, returns `{"status": "ok", "upstream": "..."}` |
| GET | `/v1/models` | Returns only models listed in `visible_models` |
| POST | `/v1/messages` | Rewrites `model` field, forwards to upstream (stream + non-stream) |
| POST | `/v1/messages/count_tokens` | Rewrites `model` field, forwards to upstream |

#### Model Name Rewriting

The `model` field in requests is rewritten according to `config.json`'s `model_map`. Unmapped models fall back to `default_model`.

#### Model Map (current)

```json
{
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
}
```

Pro-tier models (Sonnet/Opus) map to `deepseek-v4-pro`. Flash-tier models (Haiku) map to `deepseek-v4-flash`. Raw DeepSeek model names also pass through.

#### visible_models

Models exposed by `GET /v1/models`. Limited to Claude-style names to avoid validation warnings in Claude Desktop.

```json
["claude-sonnet-4-6", "claude-sonnet-4-5", "claude-opus-4-7", "claude-haiku-4-5-20251001"]
```

#### SSE Transparent Forwarding

SSE events are received byte-by-byte from upstream via `httpx client.stream()` and returned directly via Starlette `StreamingResponse` without parsing or reconstruction.

#### Logging

- Runtime: `Communication-Logs/proxy-YYYY-MM-DD.log` (daily rotation)
- Startup: `Communication-Logs/uvicorn-stdout-stderr.log`
- API key is masked by `RedactingFormatter`
- Conversation content is not logged (only model name, stream flag, and message count)

#### Encoding

Japanese Windows requires `config.json` to be handled as Shift-JIS. On startup, the proxy tries UTF-8 → UTF-8 BOM → Shift-JIS → cp932 with fallback. The GUI's Gateway Settings tab allows encoding toggle and direct editing.

#### HTTP Client

`httpx.AsyncClient` (lazy singleton):
- Connect timeout: 30s
- Read timeout: 300s
- Write timeout: 60s
- Pool timeout: 30s

### config.json Reference

```json
{
  "model_map": { "...": "..." },
  "visible_models": [ "..." ],
  "default_model": "deepseek-v4-pro",
  "force_anthropic_version": null,
  "enable_cors": false,
  "upstream_url": "https://api.deepseek.com/anthropic"
}
```

| Key | Type | Description |
|-----|------|-------------|
| `model_map` | object | Claude model name → DeepSeek model name mapping |
| `visible_models` | string[] | Models exposed via `GET /v1/models` |
| `default_model` | string | Fallback when model is not in map |
| `force_anthropic_version` | string\|null | `null` = forward request header; set to override |
| `enable_cors` | boolean | Enable/disable CORS middleware |
| `upstream_url` | string | DeepSeek Anthropic-compatible endpoint URL |

### Claude Desktop Configuration

```json
{
  "inferenceProvider": "gateway",
  "inferenceGatewayBaseUrl": "http://127.0.0.1:4000",
  "inferenceGatewayApiKey": "sk-local-gateway",
  "inferenceGatewayAuthScheme": "bearer",
  "inferenceModels": [
    {
      "name": "claude-sonnet-4-5",
      "labelOverride": "DeepSeek V4 Pro via Gateway"
    },
    {
      "name": "claude-haiku-4-5-20251001",
      "labelOverride": "DeepSeek V4 Flash via Gateway"
    }
  ]
}
```

Config file locations (Windows):
- `%APPDATA%\Claude\claude_desktop_config.json`
- `%USERPROFILE%\.claude\settings.json`
- `%LOCALAPPDATA%\Claude-3p\configLibrary\`

The GUI's Claude Desktop Setup tab provides auto-detection and clipboard copy.

### Field Test Results

| Route | Model | stream | tools | msgs | Result |
|-------|-------|--------|-------|------|--------|
| Pro | claude-sonnet-4-5 → deepseek-v4-pro | ✓ | ✓ | 43 | PASS |
| Flash | claude-haiku-4-5-20251001 → deepseek-v4-flash | ✓ | ✓ | 17 | PASS |

Both routes completed multi-turn tool-use conversations with no `reasoning_content` or `Invalid model name` errors.

### Pre-Implementation Verification

All compatibility probes against DeepSeek's Anthropic-compatible API passed before implementation.

| # | Test | Result | Detail |
|---|------|--------|--------|
| 1 | non-stream `/v1/messages` | PASS | 200, "hello" |
| 2 | stream=true SSE format | PASS | Anthropic SSE format, all 7 event types |
| 3 | thinking block | PASS | ['thinking', 'text'], no reasoning_content leakage |
| 4 | 2nd turn pass-back | PASS | No reasoning_content error |
| 5 | tool_use block | PASS | ['thinking', 'tool_use'], stop_reason=tool_use |
| 6 | tool_result 2nd turn | PASS | tool_result response successful |
| 7 | count_tokens | PASS | input_tokens=10 |
| 8 | header handling | PASS | Unknown anthropic-beta values return 200 |
