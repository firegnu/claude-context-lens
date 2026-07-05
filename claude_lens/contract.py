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
