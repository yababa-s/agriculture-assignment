"""Polite health check of every source URL in the manifest (respects robots.txt, 1 request every 2 s, HEAD first).

Reports which download pages still answer, so a maintainer knows when a portal has moved before the
scheduled refresh. Never downloads documents.

  python scripts/check_sources.py [--out logs/source_health.json] [--delay 2]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402

UA = "AgriAgent-course-project-healthcheck/1.0 (academic; low rate)"


def allowed(url: str, cache: dict) -> bool:
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if root not in cache:
        rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
        try:
            rp.read()
        except Exception:  # noqa: BLE001 - unreachable robots.txt: treat as allowed for a single HEAD request
            rp = None
        cache[root] = rp
    rp = cache[root]
    return True if rp is None else rp.can_fetch(UA, url)


def probe(url: str) -> tuple[int | str, float]:
    t0 = time.time()
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, round(time.time() - t0, 2)
        except urllib.error.HTTPError as e:
            if method == "GET":
                return e.code, round(time.time() - t0, 2)
        except Exception as e:  # noqa: BLE001
            if method == "GET":
                return type(e).__name__, round(time.time() - t0, 2)
    return "unknown", 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(config.LOG_DIR / "source_health.json"))
    ap.add_argument("--delay", type=float, default=2.0)
    a = ap.parse_args()
    urls = sorted({r["document_url"] for r in csv.DictReader(config.MANIFEST_PATH.open()) if r["document_url"]})
    robots, out = {}, []
    for u in urls:
        if not allowed(u, robots):
            out.append({"url": u, "status": "disallowed by robots.txt (skipped)"})
            continue
        status, secs = probe(u)
        out.append({"url": u, "status": status, "seconds": secs})
        print(f"{str(status):<22} {u}")
        time.sleep(a.delay)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": out}, indent=1))
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
