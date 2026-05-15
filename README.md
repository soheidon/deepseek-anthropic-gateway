# DeepSeek Anthropic Gateway

DeepSeek API の Anthropic 互換エンドポイントを Claude Desktop / Claude Code Desktop から利用するための薄型プロキシ + GUI 管理ツール。

## 概要

Claude Desktop からの Anthropic Messages API リクエストを、DeepSeek の Anthropic 互換エンドポイントに透過転送します。変更するのは `model` フィールドのみで、messages / thinking / tool_use / tool_result / streaming SSE は一切改変しません。

GUI 管理ツール（Tauri v2 + React + TypeScript）でプロキシの起動・停止、設定編集、ログ確認、API キー管理が可能です。

## 検証済みモデル経路

| Claude モデル名 | DeepSeek モデル | 実地テスト |
|----------------|----------------|-----------|
| claude-sonnet-4-5 | deepseek-v4-pro | PASS (msgs=43, tools 有, stream 有) |
| claude-haiku-4-5-20251001 | deepseek-v4-flash | PASS (msgs=17, tools 有, stream 有) |

## 必要環境

- **Python** 3.10+
- **Windows 10/11**（日本語環境対応）
- DeepSeek API キー

## クイックスタート

### 1. ダウンロード

[Releases](https://github.com/soheidon/deepseek-anthropic-gateway/releases) から最新の `deepseek-anthropic-gateway.zip` をダウンロードして展開。

### 2. セットアップ

```powershell
setup.bat
```

Python 依存パッケージ（fastapi, httpx, uvicorn）がインストールされます。

### 3. 起動

`deepseek-anthropic-gateway-gui.exe` を起動します。

### 4. API キー設定

GUI の **API キー** タブで DeepSeek API キーを入力し「保存」をクリック。
Windows ユーザー環境変数 `DEEPSEEK_API_KEY` に永続保存されます。

### 5. プロキシ起動

ヘッダーの **Start Gateway** ボタンをクリック。プロキシが `http://127.0.0.1:4000` で起動します。

### 6. Claude Desktop 設定

GUI の **Claude Desktop Setup** タブで設定 JSON をコピーし、Claude Desktop の設定ファイルに貼り付けます。
自動検出された設定ファイルが一覧表示されるので、適切なファイルを開いて貼り付けてください。

## プロキシ単体での使用（GUI なし）

```powershell
# 依存インストール
pip install -r requirements.txt

# API キー設定
setx DEEPSEEK_API_KEY "sk-..."

# 起動
python proxy_server.py
```

## エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| GET | `/health` | 死活確認 |
| GET | `/v1/models` | モデル一覧 |
| POST | `/v1/messages` | Messages API（stream/non-stream） |
| POST | `/v1/messages/count_tokens` | トークン数カウント |

## 設定 (config.json)

```json
{
  "model_map": {
    "claude-sonnet-4-5": "deepseek-v4-pro",
    "claude-haiku-4-5-20251001": "deepseek-v4-flash"
  },
  "default_model": "deepseek-v4-pro",
  "visible_models": ["claude-sonnet-4-5", "claude-haiku-4-5-20251001"],
  "force_anthropic_version": null,
  "enable_cors": false,
  "upstream_url": "https://api.deepseek.com/anthropic"
}
```

> **注意:** 日本語 Windows では `config.json` を **Shift-JIS** で保存する必要があります。GUI の Gateway Settings タブでエンコーディングを切り替えて編集できます。

## プロジェクト構成

```
deepseek-anthropic-gateway/
├── README.md
├── SPEC.md                    仕様書
├── config.json                モデルマップ設定
├── proxy_server.py            FastAPI プロキシ本体
├── requirements.txt           Python 依存
├── run.bat                    起動スクリプト
├── icon/                      アイコンソース (SVG)
├── scripts/
│   ├── phase0_probe.py        Phase 0 検証スクリプト
│   └── proxy_e2e_test.py      プロキシ経由 E2E テスト
├── gui/
│   ├── src/                   React フロントエンド
│   ├── src-tauri/             Tauri (Rust) バックエンド
│   └── package.json
├── Communication-Logs/        プロキシ実行ログ
└── release/                   ビルド済み配布物
```

## 開発

### GUI のビルド

```bash
cd gui
npm install
npm run tauri build
```

ビルドには [Rust](https://rustup.rs/) stable ツールチェーンと Node.js v24+ が必要です。

### GUI の開発モード起動

```bash
# ターミナル 1: プロキシ起動
$env:DEEPSEEK_API_KEY = "sk-..."
python proxy_server.py

# ターミナル 2: GUI 開発モード
cd gui
npm run tauri dev
```

## トラブルシュート

### ポート 4000 が使用中

```powershell
netstat -ano | findstr :4000
taskkill /PID <PID> /F
```

### reasoning_content エラー

ログに `reasoning_content must be passed back` が出た場合は該当ログを保存して Issue 報告してください。

### Invalid model name

`config.json` の `model_map` に対象モデル名を追加してください。

## ライセンス

MIT
