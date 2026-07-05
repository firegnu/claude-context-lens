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
