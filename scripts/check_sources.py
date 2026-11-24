"""Polite health check of every source URL in the manifest (respects robots.txt, 1 request every 2 s, HEAD first).

Reports which download pages still answer, so a maintainer knows when a portal has moved before the
scheduled refresh. Never downloads documents. Government portals often move or delete files; a document is never
dropped for that. For a link that fails, the nearest Internet Archive snapshot is looked up and reported, so the file
can still be fetched and checked against the SHA-256 in data/manifest.csv (known copies: agri/sources.py ARCHIVE_URLS).

  python scripts/check_sources.py [--out logs/source_health.json] [--delay 2]
"""
from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402

UA = "AgriAgent-course-project-healthcheck/1.0 (academic; low rate)"


def _ssl_context() -> ssl.SSLContext:
    """python.org Python on macOS ships without CA certificates: use certifi's bundle (in requirements.txt), otherwise
    every https portal looks broken (CERTIFICATE_VERIFY_FAILED) although it is up."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CTX = _ssl_context()


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


def _reason(e: Exception) -> str:
    r = getattr(e, "reason", e)
    if isinstance(r, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(r):
        return "ssl: certificate not trusted by this Python (site may be up; open it in a browser)"
    return f"{type(e).__name__}: {str(r)[:80]}"


def probe(url: str) -> tuple[int | str, float]:
    t0 = time.time()
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                return r.status, round(time.time() - t0, 2)
        except urllib.error.HTTPError as e:
            if method == "GET":
                return e.code, round(time.time() - t0, 2)
        except Exception as e:  # noqa: BLE001 - reported, never raised
            if method == "GET":
                return _reason(e), round(time.time() - t0, 2)
    return "unknown", 0.0


def archived_copy(url: str) -> str | None:
    """Nearest Internet Archive snapshot of a broken link (one request to the Wayback availability API)."""
    try:
        api = "https://archive.org/wayback/available?url=" + quote(url.split("://", 1)[-1], safe="")
        with urllib.request.urlopen(urllib.request.Request(api, headers={"User-Agent": UA}), timeout=30, context=CTX) as r:
            snap = json.load(r).get("archived_snapshots", {}).get("closest") or {}
        return snap.get("url") if snap.get("available") else None
    except Exception:  # noqa: BLE001 - the archive is a bonus, not a requirement
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(config.LOG_DIR / "source_health.json"))
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--no-archive", action="store_true", help="do not look up Internet Archive copies of broken links")
    a = ap.parse_args()
    urls = sorted({r["document_url"] for r in csv.DictReader(config.MANIFEST_PATH.open(encoding="utf-8")) if r["document_url"]})
    robots, out = {}, []
    for u in urls:
        if not allowed(u, robots):
            out.append({"url": u, "status": "disallowed by robots.txt (skipped)"})
            continue
        status, secs = probe(u)
        row = {"url": u, "status": status, "seconds": secs}
        if status != 200 and not a.no_archive:
            row["archived_copy"] = archived_copy(u)
        out.append(row)
        print(f"{str(status):<22} {u}")
        if row.get("archived_copy"):
            print(f"{'':<22} archived copy: {row['archived_copy']}")
        time.sleep(a.delay)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": out}, indent=1), encoding="utf-8")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
