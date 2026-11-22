"""`agriagent` command: one entry point for setup, daily use and maintenance.

  agriagent status                       what is installed, database size, backend
  agriagent fetch [--only database]      download + verify the release artifacts
  agriagent ask "question" [--show-source] [--no-llm]
  agriagent run --docs D02 | --files new.pdf [--no-llm] [--adapter DIR]
  agriagent eval queries|fields|agents|llm
  agriagent add-source FILE --source-id SRC_DES --group G1_MATRIX_TABLES --url URL --license "..."
  agriagent backup | restore FILE | check-licenses | prune-logs [--days 90]
  agriagent figures | app

(Without installing the package, use `python -m agri.cli <command>`.)
"""
from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path

from agri import config, ops

SCRIPTS = config.ROOT / "scripts"


def _script(name: str, args: list[str]) -> None:
    sys.argv = [str(SCRIPTS / name), *args]
    runpy.run_path(str(SCRIPTS / name), run_name="__main__")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="agriagent", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show installation and database status")
    for name, help_ in (("fetch", "download and verify artifacts"), ("ask", "ask a question"),
                        ("run", "run the extraction pipeline"), ("figures", "rebuild figures and animations")):
        sub.add_parser(name, help=help_, add_help=False)
    ev = sub.add_parser("eval", help="run an evaluation", add_help=False)
    ev.add_argument("which", choices=["queries", "fields", "agents", "llm"])
    a_s = sub.add_parser("add-source", help="register a new document in the corpus and manifest")
    a_s.add_argument("file")
    a_s.add_argument("--source-id", required=True)
    a_s.add_argument("--group", required=True, help="source group, e.g. G1_MATRIX_TABLES (decides the agent)")
    a_s.add_argument("--url", required=True, help="where the file was downloaded from")
    a_s.add_argument("--license", required=True)
    a_s.add_argument("--period", default="")
    a_s.add_argument("--languages", default="en")
    a_s.add_argument("--notes", default="")
    sub.add_parser("backup", help="back up the database to backups/")
    rs = sub.add_parser("restore", help="restore a backup file")
    rs.add_argument("file")
    sub.add_parser("check-licenses", help="check the manifest before adding or sharing data")
    pl = sub.add_parser("prune-logs", help="delete traces older than N days")
    pl.add_argument("--days", type=int, default=90)
    pl.add_argument("--dry-run", action="store_true")
    sub.add_parser("app", help="start the web app (Streamlit)")

    if argv and argv[0] in ("fetch", "ask", "run", "figures"):
        script = {"fetch": "fetch_artifacts.py", "ask": "ask.py", "run": "run_pipeline.py", "figures": "make_figures.py"}[argv[0]]
        return _script(script, argv[1:])
    if argv and argv[0] == "eval" and len(argv) > 1:
        script = {"queries": "eval_queries.py", "fields": "eval_fields.py", "agents": "eval_agents.py",
                  "llm": "eval_llm_tasks.py"}.get(argv[1])
        if script:
            return _script(script, argv[2:])
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(ops.status(), indent=2))
    elif a.cmd == "add-source":
        row = ops.add_source(Path(a.file), a.source_id, a.group, a.url, a.license, a.period, a.languages, a.notes)
        print(f"added {row['doc_id']} ({row['file_name']}, {row['modality']}, {row['pages']} pages) to data/manifest.csv")
        print(f"next: agriagent run --docs {row['doc_id']}   then add test cases to data/gold/ and run agriagent eval fields")
    elif a.cmd == "backup":
        p = ops.backup()
        print(f"backup written: {p}\nchecksum:      {p.with_suffix('.gz.sha256')}")
    elif a.cmd == "restore":
        print(f"restored {ops.restore(Path(a.file))} (previous file kept as *.before_restore)")
    elif a.cmd == "check-licenses":
        probs = ops.check_licenses()
        for k, v in ops.license_summary().items():
            print(f"{v:>3}  {k}")
        if probs:
            print("\nPROBLEMS:")
            print("\n".join(f"  - {p}" for p in probs))
            sys.exit(1)
        print("\nall manifest rows have licence, URL, date, checksum and language: OK")
    elif a.cmd == "prune-logs":
        old = ops.prune_logs(a.days, a.dry_run)
        print(f"{'would delete' if a.dry_run else 'deleted'} {len(old)} trace/query log files older than {a.days} days")
    elif a.cmd == "app":
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(config.ROOT / "app" / "streamlit_app.py")], check=False)


if __name__ == "__main__":
    main()
