import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .contract import SESSIONS_ROOT
from .ingest import ingest_session
from .codex_ingest import (ingest_codex_session, discover_codex_rollouts,
                           read_codex_session_index, sync_codex_sessions, CODEX_HOME)
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


def _cmd_ingest_codex(args):
    # Default the session dir to the rollout's own name (already carries an ISO
    # timestamp + uuid), so it reads clearly next to Claude sessions in the store.
    session_id = args.session_id or args.rollout.stem
    session_dir = Path(args.root) / session_id
    ingest_codex_session(args.rollout, session_dir, captured_at=_now_iso())
    print(f"Ingested Codex rollout into {session_dir}")


def _cmd_list_codex(args):
    rollouts = discover_codex_rollouts(args.codex_dir)
    print(f"{len(rollouts)} Codex rollout(s) under {args.codex_dir}/sessions:")
    for path in rollouts:
        print(f"  {path}")
    index = read_codex_session_index(args.codex_dir)
    if index:
        print(f"\nsession_index.jsonl ({len(index)} sessions):")
        for entry in index:
            print(f"  {entry.get('id')}  {entry.get('updated_at')}  {entry.get('thread_name')}")


def _cmd_sync_codex(args):
    stats = sync_codex_sessions(args.codex_dir, args.root, limit=args.limit)
    print(f"Synced {stats['ingested']} new Codex session(s); "
          f"skipped {stats['skipped_existing']} already in store, "
          f"{stats['skipped_empty']} empty.")


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

    ingest_codex_parser = sub.add_parser("ingest-codex", help="Ingest a Codex rollout jsonl")
    ingest_codex_parser.add_argument("rollout", type=Path)
    ingest_codex_parser.add_argument("--session-id", default=None)
    ingest_codex_parser.add_argument("--root", type=Path, default=SESSIONS_ROOT)
    ingest_codex_parser.set_defaults(func=_cmd_ingest_codex)

    list_codex_parser = sub.add_parser("list-codex", help="List/discover Codex sessions")
    list_codex_parser.add_argument("--codex-dir", type=Path, default=CODEX_HOME)
    list_codex_parser.set_defaults(func=_cmd_list_codex)

    sync_codex_parser = sub.add_parser("sync-codex",
                                       help="Ingest all new Codex rollouts into the store")
    sync_codex_parser.add_argument("--codex-dir", type=Path, default=CODEX_HOME)
    sync_codex_parser.add_argument("--root", type=Path, default=SESSIONS_ROOT)
    sync_codex_parser.add_argument("--limit", type=int, default=None,
                                   help="Cap how many new sessions to ingest (newest first)")
    sync_codex_parser.set_defaults(func=_cmd_sync_codex)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
