"""Download the large artifacts (database, adapter, corpus) and verify their SHA-256 checksums.

The files are attached to the GitHub release named in artifacts.json; they are not in git.

  python scripts/fetch_artifacts.py                 # database + adapter + corpus
  python scripts/fetch_artifacts.py --only database # just the knowledge base (enough for queries/figures)
  python scripts/fetch_artifacts.py --from-dir release/   # use zips already on disk (offline)
  python scripts/fetch_artifacts.py --verify        # only check what is already unpacked
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "artifacts.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dst: Path) -> None:
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "agriagent-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, dst.open("wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    except Exception as e:  # noqa: BLE001 - turned into a readable instruction
        dst.unlink(missing_ok=True)
        sys.exit(f"ERROR: could not download {url}\n  {e}\n"
                 f"  Fix: check your internet connection, or download the file in a browser into release/ "
                 f"and run: python scripts/fetch_artifacts.py --from-dir release/")


def fetch(name: str, art: dict, release_url: str, from_dir: Path | None, cache: Path) -> None:
    zip_name = art["file"]
    src = (from_dir / zip_name) if from_dir else (cache / zip_name)
    if not src.exists():
        if from_dir:
            sys.exit(f"ERROR: {src} not found (expected because of --from-dir)")
        cache.mkdir(parents=True, exist_ok=True)
        download(f"{release_url}/{zip_name}", src)
    got = sha256(src)
    if got != art["sha256"]:
        sys.exit(f"ERROR: checksum mismatch for {zip_name}\n  expected {art['sha256']}\n  got      {got}\n"
                 f"  Fix: delete {src} and run the command again.")
    dest = ROOT / art["unzip_to"]
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        z.extractall(dest)
    print(f"[ok] {name:<9} {zip_name}  sha256 verified  -> {art['unzip_to']}/")


def verify(spec: dict) -> bool:
    ok = True
    for name, art in spec["artifacts"].items():
        for rel in art["check"]:
            p = ROOT / rel
            status = "ok" if p.exists() else "MISSING"
            ok &= p.exists()
            print(f"[{status}] {name:<9} {rel}")
    return ok


def main() -> None:
    spec = json.loads(SPEC.read_text())
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=list(spec["artifacts"]), help="fetch only these artifacts")
    ap.add_argument("--from-dir", type=Path, help="directory holding the release zips (no download)")
    ap.add_argument("--verify", action="store_true", help="only report which unpacked files exist")
    a = ap.parse_args()
    if a.verify:
        sys.exit(0 if verify(spec) else 1)
    names = a.only or list(spec["artifacts"])
    print(f"release {spec['release']}  ({spec['release_url']})")
    for n in names:
        fetch(n, spec["artifacts"][n], spec["release_url"], a.from_dir, ROOT / ".cache" / "release")
    if not verify({"artifacts": {n: spec["artifacts"][n] for n in names}}):
        sys.exit(1)
    shutil.rmtree(ROOT / ".cache" / "release" / "__tmp__", ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
