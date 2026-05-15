# SPEC: DeepSeek Anthropic Gateway

DeepSeek API の Anthropic 互換エンドポイントを Claude Desktop / Claude Code Desktop から利用するための薄型プロキシ + GUI 管理ツール。

## 背景

Claude Desktop / Claude Code Desktop は Anthropic Messages API (`/v1/messages`) に直接リクエストを送る。これを DeepSeek の Anthropic 互換エンドポイントに振り向けることで、DeepSeek モデルを Anthropic クライアントから透過的に利用可能にする。

### 解決できる問題

- Claude Desktop 側のモデル名バリデーション
- LiteLLM の Anthropic→OpenAI 変換による情報ロス
- `claude-haiku-4-5-20251001` などの未登録モデル名問題

### 既知の制限

- DeepSeek Anthropic 互換 API が thinking block を完全に扱えない場合がある
- Claude Code Desktop が DeepSeek の返す thinking 情報を次ターンに正しく戻さない場合がある
- `tool_use` / `tool_result` / streaming SSE の互換性が不十分な場合がある

---

## アーキテクチャ

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

### GUI 管理ツール

```
┌──────────────────────────────────────────┐
│  DeepSeek Anthropic Gateway Manager      │
│  [Gateway: Running] [起動/停止] [EN|JA]  │
├──────────────────────────────────────────┤
│  Dashboard │ Gateway設定 │ Claude設定 │ APIキー │
├──────────────────────────────────────────┤
│  Status      │  最新ログ                 │
│  - ヘルス    │  - ログ切替              │
│  - ポート    │  - 新規ログ              │
│  - APIキー   │  - Pro/Flash 集計        │
│  - URL       │                           │
└──────────────────────────────────────────┘
```

Tauri v2 + React + TypeScript 製。4つのタブで構成：

| タブ | 機能 |
|------|------|
| Dashboard | プロキシ状態、ログ表示、Pro/Flash 使用回数集計 |
| Gateway Settings | config.json 編集、UTF-8/Shift-JIS エンコード切替 |
| Claude Desktop Setup | 設定JSONコピー、設定ファイル自動検出、手動フォルダ参照 |
| API Key | DEEPSEEK_API_KEY の設定（Windows ユーザー環境変数に永続保存） |

---

## Phase 0: 事前検証（結果: 8/8 PASS）

DeepSeek Anthropic 互換 API の互換性を実装前に検証。

| # | 項目 | 結果 | 詳細 |
|---|------|------|------|
| 1 | non-stream /v1/messages | PASS | 200, "hello" |
| 2 | stream=true SSE 形式 | PASS | Anthropic SSE 形式, 全7種 event type |
| 3 | thinking block | PASS | ['thinking', 'text'], reasoning_content 混入なし |
| 4 | 2nd turn pass-back | PASS | reasoning_content エラーなし |
| 5 | tool_use block | PASS | ['thinking', 'tool_use'], stop_reason=tool_use |
| 6 | tool_result 2nd turn | PASS | tool_result 使用応答成功 |
| 7 | count_tokens | PASS | input_tokens=10 |
| 8 | header handling | PASS | anthropic-beta 未知値も200 |

---

## Phase 1: モデル名書換プロキシ + GUI

### プロキシサーバー (proxy_server.py)

**エンドポイント:**

| Method | Path | 動作 |
|--------|------|------|
| GET | `/health` | 死活確認、upstream との疎通状態 |
| GET | `/v1/models` | visible_models のみ返す |
| POST | `/v1/messages` | model 書換後 upstream 転送、stream/non-stream 両対応 |
| POST | `/v1/messages/count_tokens` | model 書換後 upstream 転送 |

**model_map:** Claude 風モデル名を DeepSeek 実モデル名に変換。短縮名・旧世代名のエイリアスを含む。

```
claude-sonnet-4-5, claude-sonnet, claude-opus-4-5 等 → deepseek-v4-pro
claude-haiku-4-5-20251001, claude-haiku → deepseek-v4-flash
```

**visible_models:** `/v1/models` で公開するモデル名。Claude 風名のみに絞り Claude Desktop のバリデーション警告を回避。

**SSE 透過転送:** httpx `client.stream()` で upstream から SSE イベントをバイト単位で受信し、Starlette `StreamingResponse` でそのまま返す。パース・再構築は行わない。

**ログ:** `Communication-Logs/proxy-YYYYMMDD-HHMMSS.log` に出力。API キーは除去、会話内容は含まない。

**エンコーディング:** 日本語 Windows では `config.json` を Shift-JIS で扱う必要がある。GUI の Gateway Settings タブでエンコーディング切替可能。

### 実地テスト結果

| 経路 | モデル | 結果 |
|------|--------|------|
| Pro | claude-sonnet-4-5 → deepseek-v4-pro | PASS (msgs=43, tools 有, stream 有) |
| Flash | claude-haiku-4-5-20251001 → deepseek-v4-flash | PASS (msgs=17, tools 有, stream 有) |

---

## config.json 設定

```json
{
  "model_map": { ... },
  "visible_models": [ ... ],
  "default_model": "deepseek-v4-pro",
  "force_anthropic_version": null,
  "enable_cors": false,
  "upstream_url": "https://api.deepseek.com/anthropic"
}
```

| キー | 説明 |
|------|------|
| `model_map` | Claude モデル名 → DeepSeek モデル名 |
| `visible_models` | `/v1/models` で公開するモデル名 |
| `default_model` | マップにない場合のフォールバック |
| `force_anthropic_version` | null 時は受信ヘッダを転送、設定時は強制上書き |
| `enable_cors` | CORS 有効/無効 |
| `upstream_url` | DeepSeek Anthropic 互換エンドポイント |

---

## Claude Desktop 設定

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

GUI の Claude Desktop Setup タブで自動検出・コピーが可能。

---

## Phase 2（フォールバック）: 未実装

Phase 0 が 8/8 PASS したため現時点では不要。DeepSeek の応答形式を完全な Anthropic 互換に変換するロスレス変換プロキシ。
