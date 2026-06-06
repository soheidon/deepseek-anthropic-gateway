"""
DeepSeek Anthropic Model-Rename Proxy (Phase 2 — Image-Aware)

Anthropic Messages API form-data wo sono mama DeepSeek Anthropic
endpoint ni tensou si, model mei dake wo kakikae ru usugata proxy.

Phase 2 addition: non-vision models (e.g. DeepSeek) automatically strip
image blocks from conversation history before forwarding, preventing
"Model does not support image input" errors when switching models mid-thread.

Usage:
    python proxy_server.py
    # or: python -m uvicorn proxy_server:app --host 127.0.0.1 --port 4000
"""

import json
import os
import sys
import logging
import copy
import traceback
from typing import Optional, Any

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

# ---- Image sanitization config ----
MODEL_CAPABILITIES: dict[str, dict[str, bool]] = config.get("model_capabilities", {})
NON_VISION_IMAGE_POLICY: str = config.get("non_vision_image_policy", "replace")

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


def _model_supports_vision(upstream_model: str) -> bool:
    """Check if the upstream model supports image input."""
    caps = MODEL_CAPABILITIES.get(upstream_model, {})
    return caps.get("vision", False)


# -- Image block types (current + future compatibility) --
_IMAGE_CONTENT_TYPES = frozenset({"image", "input_image", "image_url"})


def _is_image_block(block: Any) -> bool:
    """Check if a content block is an image."""
    return isinstance(block, dict) and block.get("type") in _IMAGE_CONTENT_TYPES


def _count_image_blocks_in_content(content: Any) -> int:
    """Recursively count image blocks in a content array or nested structures."""
    count = 0
    if isinstance(content, list):
        for item in content:
            if _is_image_block(item):
                count += 1
            # Recurse: tool_result.content can contain image blocks
            if isinstance(item, dict):
                inner = item.get("content")
                if inner is not None:
                    count += _count_image_blocks_in_content(inner)
    return count


def _count_image_blocks(messages: list) -> int:
    """Count total image blocks across all messages (including nested in tool_result)."""
    total = 0
    for msg in messages:
        content = msg.get("content")
        if content is not None:
            total += _count_image_blocks_in_content(content)
    return total


def _sanitize_content_blocks(content: Any, policy: str) -> Any:
    """
    Recursively sanitize image blocks in a content array or nested structures.

    Returns the sanitized content. For "replace", image blocks become placeholder text.
    For "drop", image blocks are removed (caller ensures non-empty result).
    """
    if not isinstance(content, list):
        return content

    result = []
    for item in content:
        if _is_image_block(item):
            if policy == "replace":
                result.append({
                    "type": "text",
                    "text": "[Image omitted: the selected backend model does not support image input. "
                            "If the image is needed, switch to a vision-capable model.]"
                })
            elif policy == "drop":
                # Skip the image block entirely
                continue
            else:
                # reject handled at a higher level; for safety, treat as replace
                result.append({
                    "type": "text",
                    "text": "[Image omitted: the selected backend model does not support image input. "
                            "If the image is needed, switch to a vision-capable model.]"
                })
        else:
            if isinstance(item, dict):
                inner = item.get("content")
                if inner is not None:
                    item = dict(item)
                    item["content"] = _sanitize_content_blocks(inner, policy)
            result.append(item)

    return result


def _sanitize_messages(messages: list, upstream_model: str, policy: str) -> tuple[list, int]:
    """
    Sanitize image blocks from messages if the upstream model is non-vision.
    Returns (sanitized_messages, image_block_count).
    If policy is "reject" and images exist, returns (None, count) to signal rejection.
    """
    if not messages:
        return messages, 0

    if _model_supports_vision(upstream_model):
        # Vision-capable: pass through unchanged
        return messages, 0

    image_count = _count_image_blocks(messages)
    if image_count == 0:
        return messages, 0

    if policy == "reject":
        return None, image_count

    sanitized = copy.deepcopy(messages)
    for msg in sanitized:
        content = msg.get("content")
        if content is not None:
            msg["content"] = _sanitize_content_blocks(content, policy)

            # After sanitization, ensure content is never an empty array
            if isinstance(msg["content"], list) and len(msg["content"]) == 0:
                msg["content"] = [{
                    "type": "text",
                    "text": "[Image omitted: the selected backend model does not support image input. "
                            "If the image is needed, switch to a vision-capable model.]"
                }]

    return sanitized, image_count


def safe_log_request(method: str, path: str, body: dict, image_count: int = 0, sanitized: bool = False):
    """Log request details with model names but without sensitive data."""
    model_in = body.get("model", "?")
    model_out = rewrite_model(model_in)
    stream = body.get("stream", False)
    tools = bool(body.get("tools"))
    msg_count = len(body.get("messages", []))

    parts = [
        f"{method} {path}",
        f"model: {model_in} -> {model_out}",
        f"stream={stream}",
        f"tools={tools}",
        f"msgs={msg_count}",
    ]
    if image_count > 0:
        parts.append(f"image_blocks={image_count}")
        parts.append(f"image_policy={NON_VISION_IMAGE_POLICY}")
        parts.append(f"sanitized={sanitized}")

    logger.info(" | ".join(parts))


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="DeepSeek Anthropic Gateway", version="0.2.0")

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
    return {
        "status": "ok",
        "upstream": UPSTREAM_URL,
        "non_vision_image_policy": NON_VISION_IMAGE_POLICY,
    }


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

    # 1. Determine the upstream model
    requested_model = body.get("model", DEFAULT_MODEL)
    upstream_model = rewrite_model(requested_model)

    # 2. Sanitize image blocks before forwarding (if non-vision model)
    messages = body.get("messages", [])
    sanitized_messages, image_count = _sanitize_messages(
        messages, upstream_model, NON_VISION_IMAGE_POLICY
    )

    # 3. Reject if policy says so
    if sanitized_messages is None:
        safe_log_request("POST", "/v1/messages", body, image_count=image_count, sanitized=False)
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        f"This conversation contains image input, but the selected backend model "
                        f"'{upstream_model}' does not support vision. Start a text-only thread, "
                        f"switch to a vision-capable model, or set non_vision_image_policy to 'replace'."
                    ),
                }
            },
            status_code=400,
        )

    # 4. Apply sanitized body
    sanitized = image_count > 0
    if sanitized:
        body = dict(body)
        body["messages"] = sanitized_messages

    safe_log_request("POST", "/v1/messages", body, image_count=image_count, sanitized=sanitized)

    # 5. Rewrite model name
    body["model"] = upstream_model
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

    # 1. Determine the upstream model
    requested_model = body.get("model", DEFAULT_MODEL)
    upstream_model = rewrite_model(requested_model)

    # 2. Sanitize image blocks (same logic as proxy_messages)
    messages = body.get("messages", [])
    sanitized_messages, image_count = _sanitize_messages(
        messages, upstream_model, NON_VISION_IMAGE_POLICY
    )

    # 3. Reject if policy says so
    if sanitized_messages is None:
        safe_log_request("POST", "/v1/messages/count_tokens", body, image_count=image_count, sanitized=False)
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        f"This conversation contains image input, but the selected backend model "
                        f"'{upstream_model}' does not support vision. Start a text-only thread, "
                        f"switch to a vision-capable model, or set non_vision_image_policy to 'replace'."
                    ),
                }
            },
            status_code=400,
        )

    # 4. Apply sanitized body
    sanitized = image_count > 0
    if sanitized:
        body = dict(body)
        body["messages"] = sanitized_messages

    safe_log_request("POST", "/v1/messages/count_tokens", body, image_count=image_count, sanitized=sanitized)

    # 5. Rewrite model name
    body["model"] = upstream_model

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
    logger.info(f"Non-vision image policy: {NON_VISION_IMAGE_POLICY}")
    logger.info(f"Model capabilities: {MODEL_CAPABILITIES}")


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
