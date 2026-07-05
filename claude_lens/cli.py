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
