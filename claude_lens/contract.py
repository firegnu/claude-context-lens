import json
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".claude-context-lens" / "sessions"

REQUIRED_SESSION_KEYS = ["session_id", "captured_at", "launcher_argv", "model", "counts",
                         "turns", "sidechannel", "ambiguities"]
REQUIRED_REQUEST_KEYS = ["index", "raw_request", "raw_response", "breakdown", "order_confidence",
                         "is_sidechannel", "usage", "totals"]
REQUIRED_BREAKDOWN_KEYS = ["request_config", "system", "messages", "tools", "response", "usage", "totals"]


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_problems(req, label):
    return [f"{label} request missing {key}" for key in REQUIRED_REQUEST_KEYS if key not in req]


def validate_session(session):
    problems = []
    for key in REQUIRED_SESSION_KEYS:
        if key not in session:
            problems.append(f"missing session key: {key}")
    for turn in session.get("turns", []):
        if "index" not in turn or "requests" not in turn:
            problems.append(f"malformed turn: {turn.get('index')}")
            continue
        if "user_message_preview" not in turn:
            problems.append(f"turn {turn['index']} missing user_message_preview")
        for req in turn["requests"]:
            problems.extend(_request_problems(req, f"turn {turn['index']}"))
    for req in session.get("sidechannel", []):
        problems.extend(_request_problems(req, "sidechannel"))
    return problems


def validate_breakdown(breakdown):
    return [f"missing breakdown key: {key}" for key in REQUIRED_BREAKDOWN_KEYS if key not in breakdown]
