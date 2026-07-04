# Capture Service + Data Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `claude-lens` — an isolated launcher that captures a Claude Code research session's raw request/response bodies, then at exit ingests them into an on-disk contract (session → turns → requests, raw bodies + derived breakdown JSON).

**Architecture:** A Python package `claude_lens/`. The launcher runs `claude` in a subprocess with OTel raw-body-dump env vars pointed at a per-session `raw/` dir (daily `claude` untouched). On exit it ingests: pair request↔response via `diagnostics.previous_message_id`, order them, segment into user-turns, emit `derived/req-NNN.breakdown.json` per request, and write `session.json`. Reuses logic proven in the existing `extract_context_window.py` / `analyze_session_requests.py` / `analyze_session_diffs.py`.

**Tech Stack:** Python 3.12, stdlib only (`argparse`, `json`, `subprocess`, `pathlib`, `datetime`, `re`, `shutil`). Tests use stdlib `unittest` run via `python3 -m unittest` — the project convention (README: no pytest dependency). No third-party deps.

Spec: `docs/superpowers/specs/2026-07-04-capture-service-and-data-contract-design.md`

---

## File Structure

```
claude_lens/
  __init__.py       # package marker
  contract.py       # io helpers + SESSIONS_ROOT + session.json validation (schema single source of truth)
  breakdown.py      # raw request/response body -> breakdown dict
  linking.py        # raw dir -> ordered requests, req<->resp pairing, confidence, ambiguities
  turns.py          # ordered request bodies -> user-turn segmentation
  ingest.py         # orchestrate: link -> breakdown -> segment -> write session.json + derived/
  launcher.py       # isolated OTel env + run claude + trigger ingest at exit
  cli.py            # `claude-lens run …` / `claude-lens ingest <raw-dir>`
tests/
  test_contract.py
  test_breakdown.py
  test_linking.py
  test_turns.py
  test_ingest.py
  test_launcher.py
  test_cli.py
pyproject.toml      # add [project.scripts] claude-lens = claude_lens.cli:main
```

Each module has one responsibility and is unit-tested in isolation. `contract.py` is the schema single-source-of-truth the future Swift app mirrors.

All commit steps end the commit message with:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## Task 1: `contract.py` — io helpers + session validation

**Files:**
- Create: `claude_lens/__init__.py` (empty)
- Create: `claude_lens/contract.py`
- Test: `tests/test_contract.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contract.py
import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import contract


class ContractTest(unittest.TestCase):
    def test_read_write_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "x.json"
            contract.write_json(p, {"a": 1, "z": "你好"})
            self.assertEqual(contract.read_json(p), {"a": 1, "z": "你好"})

    def test_validate_session_flags_missing_keys(self):
        problems = contract.validate_session({"turns": []})
        self.assertTrue(any("session_id" in p for p in problems))

    def test_validate_session_accepts_minimal_valid(self):
        session = {
            "session_id": "s", "captured_at": "t", "model": "m",
            "counts": {}, "ambiguities": [],
            "turns": [{"index": 0, "requests": [
                {"index": 0, "raw_request": "raw/a", "breakdown": "derived/b", "order_confidence": "high:start"}
            ]}],
        }
        self.assertEqual(contract.validate_session(session), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_contract -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/__init__.py
```

```python
# claude_lens/contract.py
import json
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".claude-context-lens" / "sessions"

REQUIRED_SESSION_KEYS = ["session_id", "captured_at", "model", "counts", "turns", "ambiguities"]
REQUIRED_REQUEST_KEYS = ["index", "raw_request", "breakdown", "order_confidence"]


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_session(session):
    problems = []
    for key in REQUIRED_SESSION_KEYS:
        if key not in session:
            problems.append(f"missing session key: {key}")
    for turn in session.get("turns", []):
        if "index" not in turn or "requests" not in turn:
            problems.append(f"malformed turn: {turn.get('index')}")
            continue
        for req in turn["requests"]:
            for key in REQUIRED_REQUEST_KEYS:
                if key not in req:
                    problems.append(f"turn {turn['index']} request missing {key}")
    return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_contract -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/__init__.py claude_lens/contract.py tests/test_contract.py
git commit -m "$(printf 'Add claude_lens.contract io + session validation\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: `breakdown.py` — raw body → breakdown dict

**Files:**
- Create: `claude_lens/breakdown.py`
- Test: `tests/test_breakdown.py`

Behavior: decode text blocks, strip ANSI from `tool_result`, normalize string message content to one text block, carry tool_use/tool_result metadata, compute char totals.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_breakdown.py
import unittest

from claude_lens import breakdown


class BuildBreakdownTest(unittest.TestCase):
    def _request(self):
        return {
            "model": "claude-test",
            "betas": ["b-2025-01-01"],
            "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
            "messages": [
                {"role": "user", "content": "plain string"},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1",
                     "content": "[1mMakefile[0m\nREADME", "is_error": False}
                ]},
            ],
            "tools": [{"name": "Read", "description": "read", "input_schema": {"type": "object"}}],
        }

    def test_string_content_becomes_text_block(self):
        bd = breakdown.build_breakdown(self._request(), None)
        first = bd["messages"][0]
        self.assertEqual(first["type"], "text")
        self.assertEqual(first["text"], "plain string")

    def test_tool_result_ansi_stripped_and_metadata_kept(self):
        bd = breakdown.build_breakdown(self._request(), None)
        tr = bd["messages"][1]
        self.assertEqual(tr["tool_use_id"], "toolu_1")
        self.assertIn("Makefile\nREADME", tr["text"])
        self.assertNotIn("", tr["text"])

    def test_totals_and_usage(self):
        resp = {"content": [{"type": "text", "text": "pong"}], "usage": {"input_tokens": 5}}
        bd = breakdown.build_breakdown(self._request(), resp)
        self.assertEqual(bd["totals"]["system_chars"], 3)
        self.assertGreater(bd["totals"]["tool_schema_chars"], 0)
        self.assertEqual(bd["usage"], {"input_tokens": 5})
        self.assertEqual(bd["response"][0]["text"], "pong")
        self.assertEqual(bd["request_config"]["betas"], ["b-2025-01-01"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_breakdown -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens.breakdown'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/breakdown.py
import json
import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

CONFIG_KEYS = [
    "model", "max_tokens", "stream", "thinking", "betas",
    "context_management", "output_config", "metadata", "diagnostics",
]


def clean_text(text):
    return ANSI_RE.sub("", text)


def text_of(block):
    if isinstance(block, str):
        return clean_text(block)
    block_type = block.get("type")
    if block_type == "text":
        return block.get("text", "")
    if block_type == "tool_result":
        content = block.get("content", "")
        if isinstance(content, str):
            return clean_text(content)
        return json.dumps(content, ensure_ascii=False, indent=2)
    return json.dumps(block, ensure_ascii=False)


def block_meta(block):
    meta = {"type": block.get("type")}
    if block.get("type") == "tool_use":
        meta["tool_use_id"] = block.get("id")
        meta["tool_name"] = block.get("name")
    if block.get("type") == "tool_result":
        meta["tool_use_id"] = block.get("tool_use_id")
        meta["is_error"] = block.get("is_error")
    return meta


def build_breakdown(request_body, response_body):
    system = []
    for index, block in enumerate(request_body.get("system", [])):
        body = text_of(block)
        system.append({
            "index": index, "type": block.get("type"),
            "cache_control": block.get("cache_control"), "chars": len(body), "text": body,
        })

    messages = []
    for message_index, message in enumerate(request_body.get("messages", [])):
        content = message.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for content_index, block in enumerate(content):
            body = text_of(block)
            messages.append({
                "message_index": message_index, "content_index": content_index,
                "role": message.get("role"), **block_meta(block),
                "chars": len(body), "text": body,
            })

    tools = []
    for index, tool in enumerate(request_body.get("tools", [])):
        description = tool.get("description") or ""
        schema = tool.get("input_schema")
        tools.append({
            "index": index, "name": tool.get("name"),
            "description": tool.get("description"), "input_schema": schema,
            "description_chars": len(description),
            "schema_chars": len(json.dumps(schema, ensure_ascii=False)),
        })

    response = None
    usage = None
    if response_body:
        response = [
            {"index": i, "type": b.get("type"), "chars": len(text_of(b)), "text": text_of(b)}
            for i, b in enumerate(response_body.get("content", []))
        ]
        usage = response_body.get("usage")

    totals = {
        "system_chars": sum(s["chars"] for s in system),
        "message_chars": sum(m["chars"] for m in messages),
        "tool_description_chars": sum(t["description_chars"] for t in tools),
        "tool_schema_chars": sum(t["schema_chars"] for t in tools),
    }

    return {
        "request_config": {k: request_body.get(k) for k in CONFIG_KEYS},
        "system": system, "messages": messages, "tools": tools,
        "response": response, "usage": usage, "totals": totals,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_breakdown -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/breakdown.py tests/test_breakdown.py
git commit -m "$(printf 'Add claude_lens.breakdown raw-body parser\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: `linking.py` — order requests + pair responses

**Files:**
- Create: `claude_lens/linking.py`
- Test: `tests/test_linking.py`

Behavior: order requests by `messages_count` then link chain; pair each request to its own response via the NEXT request's `previous_message_id`; last request falls back to the latest unmatched response; assign confidence; collect ambiguities. Corrupt files are skipped, not fatal.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_linking.py
import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import linking


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


class LinkRequestsTest(unittest.TestCase):
    def _raw(self, d):
        raw = Path(d) / "raw"
        raw.mkdir()
        # round 0: start (no previous), response id r0
        _write(raw / "a.request.json", {"model": "m", "messages": [{"role": "user", "content": "hi"}]})
        _write(raw / "r0.response.json", {"id": "r0", "stop_reason": "tool_use"})
        # round 1: previous_message_id r0, response id r1
        _write(raw / "b.request.json", {"model": "m", "messages": [1, 2, 3],
                                        "diagnostics": {"previous_message_id": "r0"}})
        _write(raw / "r1.response.json", {"id": "r1", "stop_reason": "end_turn"})
        return raw

    def test_orders_and_pairs(self):
        with tempfile.TemporaryDirectory() as d:
            result = linking.link_requests(self._raw(d))
            ordered = result["ordered"]
            self.assertEqual([o["request_file"] for o in ordered], ["a.request.json", "b.request.json"])
            self.assertEqual(ordered[0]["order_confidence"], "high:start")
            # request 0's own response is inferred from request 1's previous_message_id -> r0
            self.assertEqual(ordered[0]["inferred_response_file"], "r0.response.json")
            # last request falls back to the remaining response r1
            self.assertEqual(ordered[1]["inferred_response_file"], "r1.response.json")

    def test_corrupt_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            raw = self._raw(d)
            (raw / "bad.request.json").write_text("{not json", encoding="utf-8")
            result = linking.link_requests(raw)
            self.assertEqual(len(result["ordered"]), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_linking -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens.linking'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/linking.py
from pathlib import Path

from .contract import read_json


def _previous_message_id(body):
    return body.get("diagnostics", {}).get("previous_message_id")


def _load_responses(raw_dir):
    responses = {}
    files = []
    for path in sorted(raw_dir.glob("*.response.json")):
        try:
            body = read_json(path)
        except (ValueError, OSError):
            files.append({"file": path.name, "corrupt": True})
            continue
        item = {"file": path.name, "mtime_ns": path.stat().st_mtime_ns,
                "id": body.get("id"), "stop_reason": body.get("stop_reason")}
        files.append(item)
        if item["id"]:
            responses[item["id"]] = item
    return responses, files


def _load_requests(raw_dir, responses):
    requests = []
    for path in sorted(raw_dir.glob("*.request.json")):
        try:
            body = read_json(path)
        except (ValueError, OSError):
            continue
        prev = _previous_message_id(body)
        requests.append({
            "request_file": path.name,
            "mtime_ns": path.stat().st_mtime_ns,
            "messages_count": len(body.get("messages", [])),
            "previous_message_id": prev,
            "previous_response_file": responses.get(prev, {}).get("file"),
        })
    return requests


def _sort_key(item):
    prev_rank = 0 if item["previous_message_id"] is None else 1
    return (item["messages_count"], prev_rank, item["mtime_ns"], item["request_file"])


def _confidence(item, index):
    if index == 0 and item["previous_message_id"] is None:
        return "high:start"
    if item["previous_message_id"] and item["previous_response_file"]:
        return "high:linked"
    if item["previous_message_id"] is None:
        return "medium:null-prev"
    return "low:missing-prev-response"


def link_requests(raw_dir):
    raw_dir = Path(raw_dir)
    responses, response_files = _load_responses(raw_dir)
    ordered = sorted(_load_requests(raw_dir, responses), key=_sort_key)

    for index, item in enumerate(ordered):
        item["index"] = index
        item["order_confidence"] = _confidence(item, index)

    for index, item in enumerate(ordered):
        nxt = ordered[index + 1] if index + 1 < len(ordered) else None
        response_id = nxt["previous_message_id"] if nxt else None
        item["inferred_response_file"] = responses.get(response_id, {}).get("file")

    used = {item.get("inferred_response_file") for item in ordered}
    leftover = [r for r in response_files if r.get("id") and r["file"] not in used]
    if ordered and ordered[-1]["inferred_response_file"] is None and leftover:
        ordered[-1]["inferred_response_file"] = max(leftover, key=lambda r: r["mtime_ns"])["file"]

    ambiguities = [
        {"request_file": item["request_file"], "reason": item["order_confidence"]}
        for item in ordered if item["order_confidence"].startswith(("medium", "low"))
    ]
    return {"ordered": ordered, "responses": response_files, "ambiguities": ambiguities}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_linking -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/linking.py tests/test_linking.py
git commit -m "$(printf 'Add claude_lens.linking request ordering + response pairing\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: `turns.py` — segment requests into user turns

**Files:**
- Create: `claude_lens/turns.py`
- Test: `tests/test_turns.py`

Behavior: a "real user message" is a user message with at least one non-`tool_result` block (or a string). The turn index = (count of real user messages) − 1. Requests sharing a count belong to one turn; a tool loop (adds only `tool_result`) stays in the current turn.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_turns.py
import unittest

from claude_lens import turns


def _user_text(t):
    return {"role": "user", "content": [{"type": "text", "text": t}]}


def _assistant_tool(name):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": name, "input": {}}]}


def _tool_result():
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}


class SegmentTurnsTest(unittest.TestCase):
    def test_tool_loop_stays_one_turn_then_new_turn(self):
        # req0: user asks; req1: += assistant tool_use + user tool_result (same turn);
        # req2: += assistant text + new user text (new turn)
        bodies = [
            {"messages": [_user_text("do X")]},
            {"messages": [_user_text("do X"), _assistant_tool("Bash"), _tool_result()]},
            {"messages": [_user_text("do X"), _assistant_tool("Bash"), _tool_result(),
                          {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
                          _user_text("now Y")]},
        ]
        result = turns.segment_turns(bodies)
        self.assertEqual([t["index"] for t in result], [0, 1])
        self.assertEqual(result[0]["request_indices"], [0, 1])
        self.assertEqual(result[1]["request_indices"], [2])
        self.assertEqual(result[0]["user_message_preview"], "do X")
        self.assertEqual(result[1]["user_message_preview"], "now Y")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_turns -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens.turns'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/turns.py
def _is_real_user_message(message):
    if message.get("role") != "user":
        return False
    content = message.get("content", [])
    if isinstance(content, str):
        return True
    return any(isinstance(b, dict) and b.get("type") != "tool_result" for b in content)


def real_user_message_count(request_body):
    return sum(1 for m in request_body.get("messages", []) if _is_real_user_message(m))


def last_real_user_text(request_body):
    text = ""
    for message in request_body.get("messages", []):
        if not _is_real_user_message(message):
            continue
        content = message.get("content", [])
        if isinstance(content, str):
            text = content
            continue
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(p for p in parts if p)
    return text


def segment_turns(request_bodies):
    turns = []
    for index, body in enumerate(request_bodies):
        turn_index = max(real_user_message_count(body) - 1, 0)
        if not turns or turns[-1]["index"] != turn_index:
            preview = last_real_user_text(body)[:120].replace("\n", " ")
            turns.append({"index": turn_index, "user_message_preview": preview, "request_indices": []})
        turns[-1]["request_indices"].append(index)
    return turns
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_turns -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/turns.py tests/test_turns.py
git commit -m "$(printf 'Add claude_lens.turns user-turn segmentation\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: `ingest.py` — orchestrate into the contract

**Files:**
- Create: `claude_lens/ingest.py`
- Test: `tests/test_ingest.py`

Behavior: given a `session_dir` containing `raw/`, write `derived/req-NNN.breakdown.json` per request and `session.json` (turns → requests with refs, usage, condensed totals). Validation problems are appended to `ambiguities`, never fatal.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py
import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import contract, ingest


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class IngestSessionTest(unittest.TestCase):
    def _session_dir(self, d):
        sd = Path(d) / "20260101-000000"
        raw = sd / "raw"
        _write(raw / "a.request.json", {"model": "claude-x", "system": [{"type": "text", "text": "S"}],
                                        "messages": [{"role": "user", "content": "hi"}], "tools": []})
        _write(raw / "r0.response.json", {"id": "r0", "content": [{"type": "text", "text": "pong"}],
                                          "usage": {"input_tokens": 7}, "stop_reason": "end_turn"})
        return sd

    def test_writes_valid_session_and_breakdown(self):
        with tempfile.TemporaryDirectory() as d:
            sd = self._session_dir(d)
            session = ingest.ingest_session(sd, captured_at="2026-01-01T00:00:00Z", launcher_argv=["claude"])
            self.assertEqual(contract.validate_session(session), [])
            self.assertEqual(session["counts"]["turns"], 1)
            self.assertEqual(session["counts"]["requests"], 1)
            self.assertEqual(session["model"], "claude-x")
            req = session["turns"][0]["requests"][0]
            self.assertEqual(req["raw_response"], "raw/r0.response.json")
            self.assertEqual(req["usage"], {"input_tokens": 7})
            self.assertTrue((sd / "derived" / "req-000.breakdown.json").exists())
            self.assertTrue((sd / "session.json").exists())

    def test_empty_session_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "empty"
            (sd / "raw").mkdir(parents=True)
            session = ingest.ingest_session(sd, captured_at="t", launcher_argv=None)
            self.assertEqual(session["counts"]["requests"], 0)
            self.assertEqual(session["turns"], [])
            self.assertIsNone(session["model"])
            self.assertEqual(contract.validate_session(session), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ingest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens.ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/ingest.py
from pathlib import Path

from .contract import read_json, write_json, validate_session
from .breakdown import build_breakdown
from .linking import link_requests
from .turns import segment_turns


def ingest_session(session_dir, captured_at, launcher_argv):
    session_dir = Path(session_dir)
    raw = session_dir / "raw"
    derived = session_dir / "derived"

    linked = link_requests(raw)
    ordered = linked["ordered"]
    request_bodies = [read_json(raw / item["request_file"]) for item in ordered]

    requests_meta = []
    for index, item in enumerate(ordered):
        response_body = None
        if item["inferred_response_file"]:
            response_body = read_json(raw / item["inferred_response_file"])
        bd = build_breakdown(request_bodies[index], response_body)
        bd_name = f"req-{index:03d}.breakdown.json"
        write_json(derived / bd_name, bd)
        requests_meta.append({
            "index": index,
            "raw_request": f"raw/{item['request_file']}",
            "raw_response": f"raw/{item['inferred_response_file']}" if item["inferred_response_file"] else None,
            "breakdown": f"derived/{bd_name}",
            "previous_message_id": item["previous_message_id"],
            "order_confidence": item["order_confidence"],
            "usage": bd["usage"],
            "totals": {
                "system_chars": bd["totals"]["system_chars"],
                "message_chars": bd["totals"]["message_chars"],
                "tool_chars": bd["totals"]["tool_description_chars"] + bd["totals"]["tool_schema_chars"],
            },
        })

    turns = segment_turns(request_bodies)
    for turn in turns:
        turn["requests"] = [requests_meta[i] for i in turn.pop("request_indices")]

    session = {
        "session_id": session_dir.name,
        "captured_at": captured_at,
        "launcher_argv": launcher_argv,
        "model": request_bodies[0].get("model") if request_bodies else None,
        "counts": {"turns": len(turns), "requests": len(ordered), "responses": len(linked["responses"])},
        "turns": turns,
        "ambiguities": linked["ambiguities"],
    }

    problems = validate_session(session)
    session["ambiguities"].extend({"reason": "schema", "detail": p} for p in problems)
    write_json(session_dir / "session.json", session)
    return session
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ingest -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/ingest.py tests/test_ingest.py
git commit -m "$(printf 'Add claude_lens.ingest orchestration into contract store\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: `launcher.py` — isolated OTel env + run + ingest

**Files:**
- Create: `claude_lens/launcher.py`
- Test: `tests/test_launcher.py`

Behavior: `build_otel_env` returns the base env plus the OTel dump vars (pure, testable). `run_session` creates `<root>/<session_id>/raw/`, runs `claude` via an injectable `runner`, then ingests. The test injects a fake `runner` that writes fixture raw files instead of spawning claude.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_launcher.py
import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import launcher


class BuildOtelEnvTest(unittest.TestCase):
    def test_sets_raw_bodies_file_target_without_mutating_base(self):
        base = {"PATH": "/usr/bin"}
        env = launcher.build_otel_env(Path("/tmp/raw"), base)
        self.assertEqual(env["OTEL_LOG_RAW_API_BODIES"], "file:/tmp/raw")
        self.assertEqual(env["OTEL_METRICS_EXPORTER"], "none")
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("OTEL_LOG_RAW_API_BODIES", base)  # base untouched


class RunSessionTest(unittest.TestCase):
    def test_runs_then_ingests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)

            def fake_runner(cmd, env):
                self.assertEqual(cmd[0], "claude")
                raw = Path(env["OTEL_LOG_RAW_API_BODIES"][len("file:"):])
                (raw / "a.request.json").write_text(
                    json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]}), encoding="utf-8")

            sd = launcher.run_session(
                ["-p", "hi"], session_id="20260101-000000",
                captured_at="2026-01-01T00:00:00Z", root=root,
                base_env={"PATH": "/usr/bin"}, runner=fake_runner)

            self.assertTrue((sd / "session.json").exists())
            self.assertEqual(sd, root / "20260101-000000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_launcher -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens.launcher'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/launcher.py
import os
import subprocess
from pathlib import Path

from .contract import SESSIONS_ROOT
from .ingest import ingest_session

OTEL_STATIC = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_LOG_USER_PROMPTS": "1",
    "OTEL_LOG_TOOL_DETAILS": "1",
    "OTEL_LOG_TOOL_CONTENT": "1",
    "OTEL_LOGS_EXPORTER": "console",
    "OTEL_METRICS_EXPORTER": "none",
    "OTEL_TRACES_EXPORTER": "none",
}


def build_otel_env(raw_dir, base_env):
    env = dict(base_env)
    env.update(OTEL_STATIC)
    env["OTEL_LOG_RAW_API_BODIES"] = f"file:{Path(raw_dir)}"
    return env


def run_session(argv, session_id, captured_at, root=SESSIONS_ROOT, base_env=None, runner=subprocess.run):
    base_env = os.environ.copy() if base_env is None else base_env
    session_dir = Path(root) / session_id
    raw = session_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    env = build_otel_env(raw, base_env)
    runner(["claude", *argv], env=env)
    ingest_session(session_dir, captured_at=captured_at, launcher_argv=["claude", *argv])
    return session_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_launcher -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/launcher.py tests/test_launcher.py
git commit -m "$(printf 'Add claude_lens.launcher isolated capture + ingest\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: `cli.py` — `run` and `ingest` subcommands

**Files:**
- Create: `claude_lens/cli.py`
- Test: `tests/test_cli.py`

Behavior: `claude-lens run [claude args…]` → capture+ingest. `claude-lens ingest <raw-dir> [--session-id ID]` → copy raw files into a new session dir and ingest. The test drives `main([...])` directly for the `ingest` path (no claude spawn).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json
import tempfile
import unittest
from pathlib import Path

from claude_lens import cli


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


class CliIngestTest(unittest.TestCase):
    def test_ingest_copies_raw_and_writes_session(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bodies"
            src.mkdir()
            _write(src / "a.request.json", {"model": "m", "messages": [{"role": "user", "content": "hi"}]})
            _write(src / "r0.response.json", {"id": "r0", "content": [], "usage": {}})
            out_root = Path(d) / "store"

            cli.main(["ingest", str(src), "--session-id", "sess1", "--root", str(out_root)])

            session = json.loads((out_root / "sess1" / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(session["session_id"], "sess1")
            self.assertTrue((out_root / "sess1" / "raw" / "a.request.json").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cli -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_lens.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# claude_lens/cli.py
import argparse
import shutil
from datetime import datetime
from pathlib import Path

from .contract import SESSIONS_ROOT
from .ingest import ingest_session
from .launcher import run_session


def _timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _now_iso():
    return datetime.now().astimezone().isoformat()


def _cmd_run(args):
    session_dir = run_session(args.claude_args, session_id=_timestamp(), captured_at=_now_iso())
    print(f"Captured session at {session_dir}")


def _cmd_ingest(args):
    session_id = args.session_id or _timestamp()
    session_dir = Path(args.root) / session_id
    raw = session_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.request.json", "*.response.json"):
        for path in sorted(args.raw_dir.glob(pattern)):
            shutil.copy2(path, raw / path.name)
    ingest_session(session_dir, captured_at=_now_iso(), launcher_argv=None)
    print(f"Ingested into {session_dir}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="claude-lens")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_parser = sub.add_parser("run", help="Launch claude with capture; ingest on exit")
    run_parser.add_argument("claude_args", nargs=argparse.REMAINDER)
    run_parser.set_defaults(func=_cmd_run)

    ingest_parser = sub.add_parser("ingest", help="Ingest an existing raw bodies dir")
    ingest_parser.add_argument("raw_dir", type=Path)
    ingest_parser.add_argument("--session-id", default=None)
    ingest_parser.add_argument("--root", type=Path, default=SESSIONS_ROOT)
    ingest_parser.set_defaults(func=_cmd_ingest)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_cli -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add claude_lens/cli.py tests/test_cli.py
git commit -m "$(printf 'Add claude_lens.cli run/ingest entry points\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 8: Packaging + real-data smoke test + README

**Files:**
- Create: `pyproject.toml` (none exists in the repo yet)
- Modify: `README.md` (document `claude-lens`)

- [ ] **Step 1: Create `pyproject.toml` with a console entry point**

The repo has no `pyproject.toml`; create one. The project is stdlib-only and tests run via `unittest`, so keep it minimal:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-context-lens"
version = "0.1.0"
description = "Capture and inspect Claude Code context windows"
requires-python = ">=3.10"

[project.scripts]
claude-lens = "claude_lens.cli:main"

[tool.setuptools.packages.find]
include = ["claude_lens*"]
```

Then `pip install -e .` so `claude-lens` resolves on PATH. Running via `python3 -m claude_lens.cli …` also works without installing.

- [ ] **Step 2: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — the new `claude_lens` tests (Tasks 1-7) plus the pre-existing `tests/test_extract_context_window.py`, `tests/test_analyze_session_requests.py`, `tests/test_analyze_session_diffs.py`.

- [ ] **Step 3: Real-data smoke test (manual verification, no assertion code)**

Run against a real captured dump already on disk:

```bash
python -m claude_lens.cli ingest ~/claude-otel/bodies-20260504-111512 --session-id smoke --root /tmp/claude-lens-smoke
python - <<'PY'
import json
s = json.load(open("/tmp/claude-lens-smoke/smoke/session.json"))
print("turns:", s["counts"]["turns"], "requests:", s["counts"]["requests"])
print("ambiguities:", len(s["ambiguities"]))
assert s["counts"]["requests"] > 0
assert s["turns"], "expected at least one turn"
print("OK: contract store built from real data")
PY
```

Expected: prints turn/request counts > 0 and `OK`. This exercises real tool loops, string-content messages, and multi-turn data end-to-end.

- [ ] **Step 4: Document in README**

Add a section describing `claude-lens run` (capture a research session without touching daily claude) and `claude-lens ingest <raw-dir>` (build the contract from an existing dump), and the contract layout (`session.json` / `raw/` / `derived/`). Match the existing Chinese prose style of `README.md`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md
git commit -m "$(printf 'Wire up claude-lens entry point and document it\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Notes for the implementer

- **Do not** set OTel env vars globally — isolation to the subprocess is the whole point (spec §3.1).
- `raw/` is the truth source: never rewrite or rename raw files; `derived/` is regenerable.
- Keep everything stdlib — no new dependencies. Tests run via `python3 -m unittest`, not pytest (project convention).
- **PII / redaction:** captured raw bodies contain personal metadata (email, device_id, account_uuid, session_id, local paths) — see README caveats. The local store under `~/.claude-context-lens/` is fine (personal machine, outside the repo, not committed). Never commit real captured data or fixtures derived from it; the unit-test fixtures here are synthetic on purpose, and the Task 8 smoke test writes to `/tmp`.
- The existing `scripts/extract_context_window.py` and its tests stay as-is; `breakdown.py` is a parallel library form. A later cleanup may unify them, but that is out of scope here.
- Pending, unrelated, uncommitted change in the working tree at plan time: the string-content fix in `scripts/extract_context_window.py` + its test. Decide separately whether to commit it; it is not part of this plan.
