"""Build the release zips and artifacts.json (names follow TEAMID_STATE_ARTIFACT_vN).

  python scripts/package_release.py            -> release/*.zip + artifacts.json

Corpus licensing: files whose manifest licence forbids redistribution (e.g. D14, MoFPI: "do not
redistribute") are left out of the corpus zip and listed in data/CORPUS_EXCLUDED.txt (tracked in git) with their URL, an archived copy and the SHA-256.
Upload the zips to the GitHub release named in artifacts.json (gh release create phase3-v1 release/*.zip).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402
from agri.sources import ARCHIVE_URLS  # noqa: E402

REL = config.ROOT / "release"
TAG = "phase3-v1"
URL = f"https://github.com/yababa-s/agriculture-assignment/releases/download/{TAG}"
T = f"{config.TEAM_ID}_{config.STATE}"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def zipdir(out: Path, files: list[tuple[Path, str]]) -> Path:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            z.write(src, arc)
    return out


def main() -> None:
    REL.mkdir(exist_ok=True)
    arts = {}
    db = config.DB_PATH
    zp = zipdir(REL / f"{T}_database_v2.zip", [(db, db.name)])
    arts["database"] = {"file": zp.name, "sha256": sha(zp), "unzip_to": "db", "check": [f"db/{db.name}"],
                        "contents": "SQLite knowledge base, schema v2 (geo columns), 32k observations with provenance"}
    files = []
    for name in ("34_AN_qlora_v1", "34_AN_qlora_v2"):
        d = config.ROOT / "adapters" / name
        if d.exists():
            for p in sorted(d.rglob("*")):
                if p.is_file() and not p.name.startswith("00"):       # final weights + config (+ peft), no checkpoints
                    files.append((p, str(p.relative_to(config.ROOT / "adapters"))))
    zp = zipdir(REL / f"{T}_qlora_adapters_v2.zip", files)
    arts["adapters"] = {"file": zp.name, "sha256": sha(zp), "unzip_to": "adapters",
                        "check": sorted({f"adapters/{a.split('/')[0]}/adapters.safetensors" for _, a in files}),
                        "contents": "LoRA adapter weights only (v1 and v2), MLX format plus converted PEFT format"}
    keep, excluded = [], []
    for r in csv.DictReader(config.MANIFEST_PATH.open(encoding="utf-8")):
        p = config.CORPUS_DIR / r["relative_path"]
        if "do not redistribute" in r["license"].lower():
            arch = ARCHIVE_URLS.get(r["doc_id"])
            excluded.append(f"{r['doc_id']}  {r['file_name']}\n    download: {r['document_url']}\n"
                            + (f"    archived copy (use if the link above is broken): {arch}\n" if arch else "")
                            + f"    save as: data/raw/{r['relative_path']}\n    sha256: {r['sha256']}\n    reason: {r['license']}")
        elif p.exists():
            keep.append((p, r["relative_path"]))
    zp = zipdir(REL / f"{T}_corpus_v1.zip", keep)
    (config.ROOT / "data" / "CORPUS_EXCLUDED.txt").write_text(
        "Not redistributed (licence); download from the source and check the SHA-256 "
        "(shasum -a 256 FILE, or certutil -hashfile FILE SHA256 on Windows):\n\n" + "\n".join(excluded) + "\n", encoding="utf-8")
    arts["corpus"] = {"file": zp.name, "sha256": sha(zp), "unzip_to": "data/raw",
                      "check": [f"data/raw/{a}" for _, a in keep[:3]],
                      "contents": f"{len(keep)} of 20 corpus files (see data/CORPUS_EXCLUDED.txt), paths as in data/manifest.csv",
                      "excluded": [e.split()[0] for e in excluded]}
    spec = {"release": TAG, "release_url": URL, "artifacts": arts}
    (config.ROOT / "artifacts.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    for k, v in arts.items():
        print(f"{k:<9} {v['file']:<36} {(REL / v['file']).stat().st_size / 1e6:6.1f} MB  {v['sha256'][:16]}…")
    print("-> artifacts.json; upload release/*.zip to the GitHub release", TAG)


if __name__ == "__main__":
    main()
