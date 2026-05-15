"""Quick end-to-end proxy test: multi-turn + tool use."""
import json, httpx, os

PROXY = "http://127.0.0.1:4000"
HEADERS = {
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
}

def req(model, messages, **kw):
    body = {"model": model, "max_tokens": kw.pop("max_tokens", 256), "messages": messages}
    body.update(kw)
    r = httpx.post(f"{PROXY}/v1/messages", headers=HEADERS, json=body, timeout=120)
    return r.status_code, r.json()

def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name} {detail}")

print("=== Multi-turn test ===\n")

# Turn 1
msgs = [{"role": "user", "content": "Count the letters in \"anthropic\". Think before answering."}]
status, data = req("claude-sonnet-4-5", msgs, thinking={"type": "enabled", "budget_tokens": 128})
check("Turn 1 HTTP 200", status == 200, f"({status})")
blocks1 = [b["type"] for b in data.get("content", [])]
check("Turn 1 has thinking block", "thinking" in blocks1, str(blocks1))
check("Turn 1 has text block", "text" in blocks1, str(blocks1))

# Turn 2: pass assistant back as-is
msgs.append({"role": "assistant", "content": data["content"]})
msgs.append({"role": "user", "content": "Now count the letters in \"Claude\"."})
status2, data2 = req("claude-sonnet-4-5", msgs, thinking={"type": "enabled", "budget_tokens": 128})
check("Turn 2 HTTP 200", status2 == 200, f"({status2})")
if status2 == 200:
    blocks2 = [b["type"] for b in data2.get("content", [])]
    check("Turn 2 has thinking block", "thinking" in blocks2, str(blocks2))
    text2 = " ".join(b.get("text", "") for b in data2.get("content", []) if b["type"] == "text")
    check("Turn 2 has text", len(text2) > 0, text2[:80])
else:
    err = data2.get("error", {})
    err_msg = err.get("message", str(data2)[:200])
    if "reasoning_content" in err_msg.lower():
        check("NO reasoning_content error", False, f"!! {err_msg}")
    else:
        check("Turn 2 error (not reasoning_content)", True, err_msg)

print("\n=== Tool use test ===\n")

TOOLS = [{
    "name": "get_time",
    "description": "Get the current time in a city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}]

# Tool turn 1
msgs = [{"role": "user", "content": "What time is it in Tokyo? Use the tool."}]
status, data = req("claude-haiku-4-5-20251001", msgs, tools=TOOLS, max_tokens=256)
check("Tool T1 HTTP 200", status == 200, f"({status})")
blocks = [b["type"] for b in data.get("content", [])]
check("Tool T1 has tool_use", "tool_use" in blocks, str(blocks))
check("Tool T1 stop_reason=tool_use", data.get("stop_reason") == "tool_use", str(data.get("stop_reason")))

# Tool turn 2
tool_use_blocks = [b for b in data.get("content", []) if b["type"] == "tool_use"]
if tool_use_blocks:
    tu = tool_use_blocks[0]
    msgs.append({"role": "assistant", "content": data["content"]})
    msgs.append({"role": "user", "content": [{
        "type": "tool_result",
        "tool_use_id": tu["id"],
        "content": "14:30 JST",
    }]})
    status, data = req("claude-haiku-4-5-20251001", msgs, tools=TOOLS, max_tokens=256)
    check("Tool T2 HTTP 200", status == 200, f"({status})")
    blocks = [b["type"] for b in data.get("content", [])]
    check("Tool T2 has text", "text" in blocks, str(blocks))
    text = " ".join(b.get("text", "") for b in data.get("content", []) if b["type"] == "text")
    check("Tool T2 has meaningful text", len(text) > 5, text[:120])

print("\n=== Done ===")
