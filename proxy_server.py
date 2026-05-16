"""
DeepSeek Anthropic Model-Rename Proxy (Phase 1)

Anthropic Messages API form-data wo sono mama DeepSeek Anthropic
endpoint ni tensou si, model mei dake wo kakikae ru usugata proxy.

Usage:
    python proxy_server.py
    # or: python -m uvicorn proxy_server:app --host 127.0.0.1 --port 4000
"""

import json
import os
import sys
import logging
import traceback
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.background import BackgroundTask

# ---------------------------------------------------------------------------
# Early startup logging (before FastAPI app creation)
# ---------------------------------------------------------------------------

_early_log_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Communication-Logs",
    "uvicorn-stdout-stderr.log",
)
os.makedirs(os.path.dirname(_early_log_path), exist_ok=True)

_early_logger = logging.getLogger("proxy_early")
_early_logger.setLevel(logging.DEBUG)
_early_handler = logging.FileHandler(_early_log_path, encoding="utf-8", mode="a")
_early_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_early_logger.handlers.clear()
_early_logger.addHandler(_early_handler)
_early_logger.propagate = False

_early_logger.info("=== proxy_server.py early startup ===")
_early_logger.info("sys.executable: %s", sys.executable)
_early_logger.info("os.getcwd(): %s", os.getcwd())
_early_logger.info("__file__: %s", __file__)
_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
_early_logger.info("config.json exists: %s", os.path.isfile(_config_path))
_key = os.environ.get("DEEPSEEK_API_KEY", "")
_early_logger.info("DEEPSEEK_API_KEY present: %s, length: %d", bool(_key), len(_key))
_early_logger.info("=== early startup done ===")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def _read_config_json(path: str) -> dict:
    """Read config.json, trying UTF-8 first then Shift-JIS (for Japanese Windows)."""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "utf-8-sig", "shift_jis", "cp932"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    # Last resort: replace undecodable bytes
    return json.loads(raw.decode("utf-8", errors="replace"))

config = _read_config_json(CONFIG_PATH)

MODEL_MAP: dict[str, str] = config["model_map"]
DEFAULT_MODEL: str = config["default_model"]
VISIBLE_MODELS: list[str] = config.get("visible_models", list(MODEL_MAP.keys()))
FORCE_ANTHROPIC_VERSION: Optional[str] = config.get("force_anthropic_version")
ENABLE_CORS: bool = config.get("enable_cors", False)
UPSTREAM_URL: str = config["upstream_url"]
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")

TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=300.0,
    write=60.0,
    pool=30.0,
)

# ---------------------------------------------------------------------------
# Logging — never log the API key
# ---------------------------------------------------------------------------

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Communication-Logs")

class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        key = DEEPSEEK_API_KEY
        if key and len(key) > 4:
            msg = msg.replace(key, "<REDACTED>")
        return msg

formatter = RedactingFormatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# File handler — writes to log/proxy-YYYY-MM-DD.log
os.makedirs(LOG_DIR, exist_ok=True)
from datetime import date
file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, f"proxy-{date.today().isoformat()}.log"),
    encoding="utf-8",
)
file_handler.setFormatter(formatter)

logger = logging.getLogger("proxy")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rewrite_model(requested_model: str) -> str:
    """Rewrite model name. Falls back to default if not in map."""
    return MODEL_MAP.get(requested_model, DEFAULT_MODEL)


def upstream_headers(incoming: dict) -> dict:
    """Build headers for upstream DeepSeek request."""
    headers = {}
    # Forward relevant request headers we need
    for k in ("content-type",):
        pass  # handled by httpx via json param

    headers["Authorization"] = f"Bearer {DEEPSEEK_API_KEY}"
    headers["Content-Type"] = "application/json"

    # anthropic-version
    if FORCE_ANTHROPIC_VERSION:
        headers["anthropic-version"] = FORCE_ANTHROPIC_VERSION
    elif "anthropic-version" in incoming:
        headers["anthropic-version"] = incoming["anthropic-version"]

    # anthropic-beta
    if "anthropic-beta" in incoming:
        headers["anthropic-beta"] = incoming["anthropic-beta"]

    return headers


def safe_log_request(method: str, path: str, body: dict):
    """Log request details with model names but without sensitive data."""
    model_in = body.get("model", "?")
    model_out = rewrite_model(model_in)
    stream = body.get("stream", False)
    tools = bool(body.get("tools"))
    msg_count = len(body.get("messages", []))
    logger.info(
        f"{method} {path} | model: {model_in} -> {model_out}"
        f" | stream={stream} | tools={tools} | msgs={msg_count}"
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="DeepSeek Anthropic Gateway", version="0.1.0")

if ENABLE_CORS:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
async def health():
    return {"status": "ok", "upstream": UPSTREAM_URL}


@app.get("/v1/models")
async def list_models():
    """Return Claude-friendly model names only.
    DeepSeek raw names are functional for curl/CLI testing but hidden from Desktop clients
    to avoid model-name validation warnings."""
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "type": "model"}
            for m in VISIBLE_MODELS
        ],
    }


@app.api_route("/v1/messages", methods=["POST"])
async def proxy_messages(request: Request):
    body = await request.json()
    safe_log_request("POST", "/v1/messages", body)

    # Rewrite model name only
    body["model"] = rewrite_model(body.get("model", DEFAULT_MODEL))
    is_stream = body.get("stream", False)

    upstream_req = httpx.Request(
        "POST",
        f"{UPSTREAM_URL}/v1/messages",
        json=body,
        headers=upstream_headers(dict(request.headers)),
    )

    client = _get_client()
    if is_stream:
        return await _handle_stream(client, upstream_req)
    else:
        return await _handle_nonstream(client, upstream_req)


async def _handle_nonstream(client: httpx.AsyncClient, req: httpx.Request):
    try:
        resp = await client.send(req)
    except httpx.RequestError as exc:
        logger.error(f"Upstream request failed: {exc}")
        return JSONResponse(
            {"error": {"type": "proxy_error", "message": str(exc)}},
            status_code=502,
        )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


async def _handle_stream(client: httpx.AsyncClient, req: httpx.Request):
    async def stream_sse():
        try:
            async with client.stream(req.method, req.url, headers=req.headers, content=req.content) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(f"Stream upstream error {resp.status_code}: {body[:300]}")
                    yield f'data: {{"error": "upstream error {resp.status_code}"}}\n\n'
                    return

                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    yield chunk
        except httpx.RequestError as exc:
            logger.error(f"Stream upstream failed: {exc}")
            yield f'data: {{"error": "upstream connection failed: {exc}"}}\n\n'

    return StreamingResponse(
        stream_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.api_route("/v1/messages/count_tokens", methods=["POST"])
async def proxy_count_tokens(request: Request):
    body = await request.json()
    safe_log_request("POST", "/v1/messages/count_tokens", body)

    body["model"] = rewrite_model(body.get("model", DEFAULT_MODEL))

    client = _get_client()
    try:
        resp = await client.post(
            f"{UPSTREAM_URL}/v1/messages/count_tokens",
            json=body,
            headers=upstream_headers(dict(request.headers)),
        )
    except httpx.RequestError as exc:
        logger.error(f"count_tokens request failed: {exc}")
        return JSONResponse(
            {"error": {"type": "proxy_error", "message": str(exc)}},
            status_code=502,
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


async def _shutdown_client():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY environment variable not set!")
        sys.exit(1)
    logger.info(f"Upstream: {UPSTREAM_URL}")
    logger.info(f"Model map: {MODEL_MAP}")
    logger.info(f"Default model: {DEFAULT_MODEL}")


@app.on_event("shutdown")
async def shutdown():
    await _shutdown_client()


# ---------------------------------------------------------------------------
# Main (for direct invocation)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting uvicorn on 127.0.0.1:4000")
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=4000,
            log_level="info",
            access_log=False,
            log_config=None,
        )
    except Exception:
        logger.exception("uvicorn.run() raised an exception")
        # Also write to early log for visibility
        _early_logger.exception("uvicorn.run() raised an exception")
        raise
