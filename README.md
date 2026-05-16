# DeepSeek Anthropic Gateway

## 日本語

### 概要

DeepSeek API の Anthropic 互換エンドポイントを Claude Desktop / Claude Code Desktop から利用するための薄型プロキシ + GUI 管理ツール。

Anthropic Messages API リクエストを DeepSeek の Anthropic 互換エンドポイントに透過転送します。変更するのは `model` フィールドのみで、messages / thinking / tool_use / tool_result / streaming SSE は一切改変しません。

GUI 管理ツール（Tauri v2 + React + TypeScript）でプロキシの起動・停止、設定編集、ログ確認、API キー管理が可能です。

### 検証済みモデル経路

| Claude モデル名 | DeepSeek モデル | 実地テスト |
|----------------|----------------|-----------|
| claude-sonnet-4-5 | deepseek-v4-pro | PASS (msgs=43, tools 有, stream 有) |
| claude-haiku-4-5-20251001 | deepseek-v4-flash | PASS (msgs=17, tools 有, stream 有) |

### 必要環境

- **Python** 3.10+
- **Windows 10/11**（日本語環境対応）
- DeepSeek API キー

### クイックスタート

#### 1. ダウンロード

[Releases](https://github.com/soheidon/deepseek-anthropic-gateway/releases) から最新の `deepseek-anthropic-gateway.zip` をダウンロードして展開。

#### 2. セットアップ

```powershell
setup.bat
```

Python 依存パッケージ（fastapi, httpx, uvicorn）がインストールされます。

#### 3. 起動

`deepseek-anthropic-gateway-gui.exe` を起動します。

#### 4. API キー設定

GUI の **API キー** タブで DeepSeek API キーを入力し「保存」をクリック。
Windows ユーザー環境変数 `DEEPSEEK_API_KEY` に永続保存されます。

#### 5. プロキシ起動

ヘッダーの **Start Gateway** ボタンをクリック。プロキシが `http://127.0.0.1:4000` で起動します（コンソールウィンドウは表示されません）。

#### 6. Claude Desktop 設定

GUI の **Claude Desktop Setup** タブで設定 JSON をコピーし、Claude Desktop の設定ファイルに貼り付けます。
自動検出された設定ファイルが一覧表示されるので、適切なファイルを開いて貼り付けてください。

### プロキシ単体での使用（GUI なし）

```powershell
pip install -r requirements.txt
setx DEEPSEEK_API_KEY "sk-..."
python proxy_server.py
```

### エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | 死活確認 |
| GET | `/v1/models` | モデル一覧 |
| POST | `/v1/messages` | Messages API（stream/non-stream） |
| POST | `/v1/messages/count_tokens` | トークン数カウント |

### 設定 (config.json)

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

| キー | 説明 |
|-----|------|
| `model_map` | Claude モデル名 → DeepSeek モデル名のマッピング |
| `visible_models` | `GET /v1/models` で公開するモデル名 |
| `default_model` | マップにない場合のフォールバック |
| `force_anthropic_version` | null 時は受信ヘッダを転送、設定時は強制上書き |
| `enable_cors` | CORS 有効/無効 |
| `upstream_url` | DeepSeek Anthropic 互換エンドポイント |

> 日本語 Windows では `config.json` を **Shift-JIS** で保存する必要があります。GUI の Gateway Settings タブでエンコーディングを切り替えて編集できます。

### プロジェクト構成

```
deepseek-anthropic-gateway/
├── README.md
├── SPEC.md                    仕様書（日英）
├── LICENSE                    MIT License
├── config.json                モデルマップ設定
├── proxy_server.py            FastAPI プロキシ本体
├── requirements.txt           Python 依存
├── run.bat / run-logging.bat  起動スクリプト
├── .gitignore
├── icon/                      アイコンソース (SVG, PNG)
├── scripts/
│   ├── phase0_probe.py        事前検証スクリプト
│   └── proxy_e2e_test.py      E2E テスト
├── gui/
│   ├── src/                   React フロントエンド (TypeScript)
│   │   ├── components/        UI コンポーネント (7ファイル)
│   │   ├── hooks/             カスタムフック (5ファイル)
│   │   └── i18n/              日英翻訳
│   ├── src-tauri/             Tauri バックエンド (Rust)
│   │   ├── src/lib.rs         18 Tauri コマンド
│   │   └── Cargo.toml
│   └── package.json
├── Communication-Logs/        プロキシ実行ログ
├── claude-log/                開発セッションログ
└── release/                   ビルド済み配布物
```

### 開発

#### GUI のビルド

```bash
cd gui
npm install
npm run tauri build
```

[Rust](https://rustup.rs/) stable ツールチェーンと Node.js 24+ が必要です。

#### 開発モード

```bash
# ターミナル 1: プロキシ起動
$env:DEEPSEEK_API_KEY = "sk-..."
python proxy_server.py

# ターミナル 2: GUI 開発モード
cd gui
npm run tauri dev
```

### トラブルシュート

#### ポート 4000 が使用中

```powershell
netstat -ano | findstr :4000
taskkill /PID <PID> /F
```

#### reasoning_content エラー

ログに `reasoning_content must be passed back` が出た場合は該当ログを保存して Issue 報告してください。

#### Invalid model name

`config.json` の `model_map` に対象モデル名を追加してください。

### ライセンス

MIT — 詳細は [LICENSE](LICENSE) を参照。

---

## English

### Overview

A thin proxy + GUI manager that routes Claude Desktop / Claude Code API requests through DeepSeek's Anthropic-compatible endpoint.

Anthropic Messages API requests are transparently forwarded to DeepSeek's Anthropic-compatible endpoint. Only the `model` field is rewritten — messages, thinking blocks, tool_use, tool_result, and streaming SSE pass through untouched.

The GUI management tool (Tauri v2 + React + TypeScript) provides start/stop control, config editing, log viewing, and API key management from a native Windows window.

### Verified Model Routes

| Claude Model | DeepSeek Model | Field Test |
|---|---|---|
| claude-sonnet-4-5 | deepseek-v4-pro | PASS (msgs=43, tools, stream) |
| claude-haiku-4-5-20251001 | deepseek-v4-flash | PASS (msgs=17, tools, stream) |

### Prerequisites

- **Python** 3.10+
- **Windows 10/11** (Japanese locale supported)
- DeepSeek API key

### Quick Start

#### 1. Download

Download the latest `deepseek-anthropic-gateway.zip` from [Releases](https://github.com/soheidon/deepseek-anthropic-gateway/releases) and extract.

#### 2. Setup

```powershell
setup.bat
```

Installs Python dependencies (fastapi, httpx, uvicorn).

#### 3. Launch

Run `deepseek-anthropic-gateway-gui.exe`.

#### 4. Set API Key

Go to the **API Key** tab, enter your DeepSeek API key, and click **Save**.
The key is persisted as a Windows user environment variable (`DEEPSEEK_API_KEY`).

#### 5. Start Gateway

Click **Start Gateway** in the header. The proxy starts on `http://127.0.0.1:4000` as a background process (no console window).

#### 6. Configure Claude Desktop

Go to the **Claude Desktop Setup** tab, copy the JSON config, and paste it into your Claude Desktop settings file.
Auto-detected config files are listed — open the appropriate one and paste.

### Proxy-Only Usage (no GUI)

```powershell
pip install -r requirements.txt
setx DEEPSEEK_API_KEY "sk-..."
python proxy_server.py
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/models` | List visible models |
| POST | `/v1/messages` | Messages API (stream + non-stream) |
| POST | `/v1/messages/count_tokens` | Token counting |

### Configuration (config.json)

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
| `default_model` | Fallback when model not in map |
| `force_anthropic_version` | `null` = passthrough; set to override |
| `enable_cors` | Enable/disable CORS middleware |
| `upstream_url` | DeepSeek Anthropic-compatible endpoint URL |

> Japanese Windows requires saving `config.json` as **Shift-JIS**. Use the Gateway Settings tab in the GUI to toggle encoding.

### Project Structure

```
deepseek-anthropic-gateway/
├── README.md
├── SPEC.md                    Specification (JA/EN)
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

### Dev Build

#### GUI

```bash
cd gui
npm install
npm run tauri build
```

Requires [Rust](https://rustup.rs/) stable toolchain and Node.js 24+.

#### Dev Mode

```bash
# Terminal 1: Start proxy
$env:DEEPSEEK_API_KEY = "sk-..."
python proxy_server.py

# Terminal 2: Start GUI in dev mode
cd gui
npm run tauri dev
```

### Troubleshooting

#### Port 4000 in use

```powershell
netstat -ano | findstr :4000
taskkill /PID <PID> /F
```

#### reasoning_content error

If the log shows `reasoning_content must be passed back`, save the relevant log and file an issue.

#### Invalid model name

Add the model name to `model_map` in `config.json`.

### License

MIT — see [LICENSE](LICENSE) for details.
