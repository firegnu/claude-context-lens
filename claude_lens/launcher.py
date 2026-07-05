import os
import signal
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

    # The terminal delivers Ctrl-C (SIGINT) to the whole foreground process
    # group, including the claude child, which handles its own interrupt.
    # Ignore it here so a Ctrl-C during the session doesn't also kill the
    # launcher and skip the exit-time ingest below.
    previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        result = runner(["claude", *argv], env=env)
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        ingest_session(session_dir, captured_at=captured_at, launcher_argv=["claude", *argv])

    returncode = getattr(result, "returncode", 0)
    return session_dir, returncode
