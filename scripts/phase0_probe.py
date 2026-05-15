"""
Phase 0: DeepSeek Anthropic互換API 事前検証プローブ

DeepSeekのAnthropic互換エンドポイントが Claude Desktop / Claude Code Desktop
用途に必要な最低限の挙動を満たすかを検証する。

環境変数:
    DEEPSEEK_API_KEY   DeepSeek APIキー (required)
    DEEPSEEK_MODEL     モデル名 (default: deepseek-v4-pro)
"""

import json
import os
import sys
import textwrap
import httpx

# Japanese Windows console may not support UTF-8 emoji; reconfigure if possible.
if sys.stdout.encoding.lower() in ("cp932", "shift_jis"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_URL = "https://api.deepseek.com/anthropic"
DEFAULT_MODEL = "deepseek-v4-pro"

TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=300.0,
    write=60.0,
    pool=30.0,
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"


class ProbeResult:
    def __init__(self, name: str):
        self.name = name
        self.status = None  # "PASS", "FAIL", "WARN"
        self.status_code = None
        self.error_summary = None
        self.details = []

    def add(self, label: str, value):
        self.details.append((label, value))

    def set_pass(self):
        self.status = "PASS"

    def set_fail(self, reason: str):
        self.status = "FAIL"
        self.error_summary = reason

    def set_warn(self, reason: str):
        self.status = "WARN"
        self.error_summary = reason

    def display(self):
        tag = {"PASS": PASS, "FAIL": FAIL, "WARN": WARN}.get(self.status, "???")
        print(f"\n{'='*60}")
        print(f"  [{tag}] {self.name}")
        if self.status_code is not None:
            print(f"  HTTP Status: {self.status_code}")
        if self.error_summary:
            lines = self.error_summary.strip().split("\n")
            print(f"  Summary: {lines[0]}")
            for line in lines[1:]:
                print(f"           {line}")
        for label, value in self.details:
            print(f"  {label}: {value}")
        print(f"{'='*60}")


def _redact(text: str) -> str:
    """Redact API key from text."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key and len(key) > 4:
        return text.replace(key, "<REDACTED>")
    return text


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }


def _body(model: str, messages: list, **kwargs) -> dict:
    b = {
        "model": model,
        "max_tokens": kwargs.pop("max_tokens", 1024),
        "messages": messages,
    }
    b.update(kwargs)
    return b


# ---------------------------------------------------------------------------
# Probe 1: non-stream /v1/messages
# ---------------------------------------------------------------------------
async def probe_nonstream(client: httpx.AsyncClient, model: str) -> ProbeResult:
    r = ProbeResult("/v1/messages (non-stream)")
    messages = [{"role": "user", "content": "Say 'hello' and nothing else."}]

    try:
        resp = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, messages),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.status_code = resp.status_code
    if resp.status_code == 200:
        data = resp.json()
        content_blocks = data.get("content", [])
        text = " ".join(
            b.get("text", "")
            for b in content_blocks
            if b.get("type") == "text"
        )
        r.add("Response text", textwrap.shorten(text, width=200))
        r.set_pass()
    else:
        r.set_fail(_redact(resp.text[:500]))
    return r


# ---------------------------------------------------------------------------
# Probe 2: stream=true /v1/messages
# ---------------------------------------------------------------------------
async def probe_stream(client: httpx.AsyncClient, model: str) -> ProbeResult:
    r = ProbeResult("/v1/messages (stream=true)")
    messages = [{"role": "user", "content": "Count from 1 to 5."}]

    try:
        async with client.stream(
            "POST",
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, messages, stream=True),
        ) as resp:
            r.status_code = resp.status_code
            if resp.status_code != 200:
                body = await resp.aread()
                r.set_fail(_redact(body.decode(errors="replace")[:500]))
                return r

            event_types = set()
            text_chunks = []
            lines_received = 0

            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event_types.add(line.split(":", 1)[1].strip())
                elif line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    lines_received += 1
                    if data_str and data_str != "[DONE]":
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text_chunks.append(delta.get("text", ""))
                        except json.JSONDecodeError:
                            pass

            r.add("SSE event types", sorted(event_types))
            r.add("SSE data lines", lines_received)
            text = "".join(text_chunks)
            r.add("Streamed text", textwrap.shorten(text, width=200))

            if event_types:
                r.set_pass()
            else:
                r.set_warn("No SSE event types detected — may not be Anthropic SSE format")

    except Exception as exc:
        r.set_fail(_redact(str(exc)))
    return r


# ---------------------------------------------------------------------------
# Probe 3: thinking mode → thinking block
# ---------------------------------------------------------------------------
async def probe_thinking(client: httpx.AsyncClient, model: str) -> ProbeResult:
    """Check if DeepSeek returns a thinking block in Anthropic format."""
    r = ProbeResult("thinking mode → thinking block")
    messages = [
        {"role": "user", "content": "What is 123 * 456? First think step by step, then give the answer."}
    ]

    try:
        resp = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, messages, max_tokens=2048, thinking={"type": "enabled", "budget_tokens": 1024}),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.status_code = resp.status_code
    if resp.status_code != 200:
        r.set_fail(_redact(resp.text[:500]))
        return r

    data = resp.json()
    content_blocks = data.get("content", [])
    block_types = [b.get("type") for b in content_blocks]
    has_thinking = any(b.get("type") == "thinking" for b in content_blocks)
    has_reasoning_content_key = any("reasoning_content" in b for b in content_blocks)

    r.add("block types", block_types)
    r.add("has thinking block (Anthropic format)", has_thinking)
    r.add("contains reasoning_content key (OpenAI format)", has_reasoning_content_key)

    if has_thinking and not has_reasoning_content_key:
        r.set_pass()
    elif has_thinking and has_reasoning_content_key:
        r.set_warn("Both thinking block and reasoning_content key present — mixed format")
    elif not has_thinking and has_reasoning_content_key:
        r.set_fail("OpenAI-style reasoning_content returned instead of Anthropic thinking block")
    else:
        r.set_fail("No thinking or reasoning block found — thinking mode may not work")
    return r


# ---------------------------------------------------------------------------
# Probe 4: 2nd turn (reasoning_content must be passed back)
# ---------------------------------------------------------------------------
async def probe_two_turn(client: httpx.AsyncClient, model: str) -> ProbeResult:
    """Turn 1 with thinking → include assistant response in turn 2 → check for error."""
    r = ProbeResult("2nd turn: reasoning_content pass-back")
    messages = [
        {
            "role": "user",
            "content": "What is the capital of France? Please think about it before answering.",
        }
    ]

    # Turn 1: get assistant response with thinking
    try:
        resp1 = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, list(messages), max_tokens=1024, thinking={"type": "enabled", "budget_tokens": 512}),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.status_code = resp1.status_code
    if resp1.status_code != 200:
        r.set_fail(f"Turn 1 failed: {_redact(resp1.text[:300])}")
        return r

    data1 = resp1.json()
    assistant_msg = {
        "role": "assistant",
        "content": data1.get("content", []),
    }

    # Turn 2: pass assistant message as-is + new user message
    messages.append(assistant_msg)
    messages.append({"role": "user", "content": "Thank you. Now what is the capital of Germany?"})

    try:
        resp2 = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, messages, max_tokens=1024, thinking={"type": "enabled", "budget_tokens": 512}),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.add("turn2 HTTP status", resp2.status_code)
    if resp2.status_code == 200:
        data2 = resp2.json()
        text = " ".join(
            b.get("text", "")
            for b in data2.get("content", [])
            if b.get("type") == "text"
        )
        r.add("turn2 response", textwrap.shorten(text, width=200))
        r.set_pass()
    else:
        body = resp2.text
        if "reasoning_content must be passed back" in body.lower():
            r.set_fail("reasoning_content must be passed back — 薄型プロキシでは不十分")
        else:
            r.set_fail(_redact(body[:500]))
    return r


# ---------------------------------------------------------------------------
# Probe 5: tools request → tool_use block
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"],
        },
    }
]


async def probe_tools(client: httpx.AsyncClient, model: str) -> ProbeResult:
    r = ProbeResult("tools request → tool_use block")
    messages = [{"role": "user", "content": "What's the weather in Paris?"}]

    try:
        resp = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, messages, tools=TOOLS),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.status_code = resp.status_code
    if resp.status_code != 200:
        r.set_fail(_redact(resp.text[:500]))
        return r

    data = resp.json()
    content_blocks = data.get("content", [])
    block_types = [b.get("type") for b in content_blocks]
    has_tool_use = any(b.get("type") == "tool_use" for b in content_blocks)
    stop_reason = data.get("stop_reason")

    r.add("block types", block_types)
    r.add("stop_reason", stop_reason)
    r.add("has tool_use block", has_tool_use)

    if has_tool_use:
        r.set_pass()
    else:
        r.set_fail(f"No tool_use block in response. stop_reason={stop_reason}, blocks={block_types}")
    return r


# ---------------------------------------------------------------------------
# Probe 6: tool_result 2nd turn
# ---------------------------------------------------------------------------
async def probe_tool_result(client: httpx.AsyncClient, model: str) -> ProbeResult:
    r = ProbeResult("tool_result 2nd turn")
    messages = [{"role": "user", "content": "What's the weather in Tokyo?"}]

    # Turn 1: get tool_use
    try:
        resp1 = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, list(messages), tools=TOOLS),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.status_code = resp1.status_code
    if resp1.status_code != 200:
        r.set_fail(f"Turn 1 failed: {_redact(resp1.text[:300])}")
        return r

    data1 = resp1.json()
    tool_use_blocks = [b for b in data1.get("content", []) if b.get("type") == "tool_use"]
    if not tool_use_blocks:
        r.set_fail("Turn 1 returned no tool_use block — cannot test tool_result flow")
        return r

    tool_use = tool_use_blocks[0]
    messages.append({"role": "assistant", "content": data1["content"]})
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use["id"],
                "content": "Temperature: 15°C, Condition: Clear sky",
            }
        ],
    })

    # Turn 2: send tool_result
    try:
        resp2 = await client.post(
            f"{BASE_URL}/v1/messages",
            headers=_headers(),
            json=_body(model, messages, tools=TOOLS),
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.add("turn2 HTTP status", resp2.status_code)
    if resp2.status_code == 200:
        data2 = resp2.json()
        text = " ".join(
            b.get("text", "")
            for b in data2.get("content", [])
            if b.get("type") == "text"
        )
        r.add("turn2 response", textwrap.shorten(text, width=200))
        r.set_pass()
    else:
        r.set_fail(_redact(resp2.text[:500]))
    return r


# ---------------------------------------------------------------------------
# Probe 7: /v1/messages/count_tokens
# ---------------------------------------------------------------------------
async def probe_count_tokens(client: httpx.AsyncClient, model: str) -> ProbeResult:
    r = ProbeResult("/v1/messages/count_tokens")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello, how are you?"}],
    }

    try:
        resp = await client.post(
            f"{BASE_URL}/v1/messages/count_tokens",
            headers=_headers(),
            json=body,
        )
    except Exception as exc:
        r.set_fail(_redact(str(exc)))
        return r

    r.status_code = resp.status_code
    if resp.status_code == 200:
        data = resp.json()
        r.add("input_tokens", data.get("input_tokens", "N/A"))
        r.set_pass()
    elif resp.status_code == 404:
        r.set_warn("count_tokens endpoint not available (404)")
    elif resp.status_code == 405:
        r.set_warn("count_tokens endpoint not available (405 Method Not Allowed)")
    else:
        r.set_warn(f"Unexpected status: {resp.status_code} — {_redact(resp.text[:200])}")
    return r


# ---------------------------------------------------------------------------
# Probe 8: Header handling
# ---------------------------------------------------------------------------
async def probe_headers(client: httpx.AsyncClient, model: str) -> ProbeResult:
    """Send various anthropic-version / anthropic-beta headers and observe response."""
    r = ProbeResult("anthropic-version / anthropic-beta headers")

    test_cases = [
        # (headers, description)
        ({"anthropic-version": "2023-06-01"}, "anthropic-version: 2023-06-01"),
        (
            {
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-24",
            },
            "with anthropic-beta: prompt-caching-2024-07-24",
        ),
        (
            {
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "unsupported-beta-feature-test",
            },
            "with unknown anthropic-beta value",
        ),
    ]

    messages = [{"role": "user", "content": "Say 'ok'."}]
    results = []

    for extra_headers, desc in test_cases:
        try:
            h = {**_headers(), **extra_headers}
            resp = await client.post(
                f"{BASE_URL}/v1/messages",
                headers=h,
                json=_body(model, list(messages), max_tokens=64),
            )
            status = resp.status_code
            body_snippet = resp.text[:200] if status >= 400 else "OK"
            results.append((desc, status, body_snippet))
        except Exception as exc:
            results.append((desc, "ERROR", _redact(str(exc))))

    for desc, status, snippet in results:
        r.add(desc, f"status={status}, body={textwrap.shorten(snippet, width=120)}")

    # PASS if standard headers work, WARN if beta headers cause issues
    standard_ok = results[0][1] == 200 if results else False
    beta_ok = results[1][1] == 200 if len(results) > 1 else False

    if standard_ok and beta_ok:
        r.set_pass()
    elif standard_ok:
        r.set_warn("Standard headers OK, but anthropic-beta may cause issues")
    else:
        r.set_fail("Standard anthropic-version header rejected")
    return r


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)

    print(f"Phase 0: DeepSeek Anthropic互換API 事前検証")
    print(f"  Base URL: {BASE_URL}")
    print(f"  Model:    {model}")
    print(f"  API Key:  {'*' * 8}{api_key[-4:]}")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        probes = [
            await probe_nonstream(client, model),
            await probe_stream(client, model),
            await probe_thinking(client, model),
            await probe_two_turn(client, model),
            await probe_tools(client, model),
            await probe_tool_result(client, model),
            await probe_count_tokens(client, model),
            await probe_headers(client, model),
        ]

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    pass_count = sum(1 for p in probes if p.status == "PASS")
    fail_count = sum(1 for p in probes if p.status == "FAIL")
    warn_count = sum(1 for p in probes if p.status == "WARN")

    for p in probes:
        p.display()

    print(f"\n  Total: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")

    if fail_count == 0 and warn_count == 0:
        print("\n  => 薄型プロキシ方式で実装に進んでよい。")
    elif fail_count == 0:
        print("\n  => WARNあり。薄型プロキシで進められる可能性が高いが、要注意項目を確認すること。")
    else:
        print("\n  => FAILあり。薄型プロキシでは不十分。SPEC.md の Phase 2（ロスレス変換プロキシ）を検討せよ。")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
