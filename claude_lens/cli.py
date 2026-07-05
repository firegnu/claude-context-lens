import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .contract import SESSIONS_ROOT
from .ingest import ingest_session
from .launcher import run_session


def _timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _now_iso():
    return datetime.now().astimezone().isoformat()


def _cmd_run(claude_args):
    session_dir, returncode = run_session(claude_args, session_id=_timestamp(), captured_at=_now_iso())
    print(f"Captured session at {session_dir}")
    return returncode


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
    argv = sys.argv[1:] if argv is None else list(argv)

    # `run` takes arbitrary claude args (including dash-prefixed ones like `-p`),
    # which argparse's subparser machinery can't pass through unmangled. Peel it
    # off before argparse ever sees it and route everything after it verbatim.
    if argv and argv[0] == "run":
        claude_args = argv[1:]
        if claude_args and claude_args[0] == "--":
            claude_args = claude_args[1:]
        return _cmd_run(claude_args)

    parser = argparse.ArgumentParser(prog="claude-lens")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest_parser = sub.add_parser("ingest", help="Ingest an existing raw bodies dir")
    ingest_parser.add_argument("raw_dir", type=Path)
    ingest_parser.add_argument("--session-id", default=None)
    ingest_parser.add_argument("--root", type=Path, default=SESSIONS_ROOT)
    ingest_parser.set_defaults(func=_cmd_ingest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
