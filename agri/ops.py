"""Maintenance operations: backup / restore, adding a source, licence checks, log retention, health check.

All of them are exposed through the `agriagent` command (agri/cli.py) and documented in the user manual.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import shutil
import sqlite3
import time
from pathlib import Path

from agri import config

MANIFEST_FIELDS = ["doc_id", "file_name", "relative_path", "source_id", "source_name", "portal_url", "document_url",
                   "source_group", "period", "geography", "modality", "pages", "languages", "scripts",
                   "legacy_font_encoding", "size_bytes", "sha256", "collection_date", "license", "notes"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ backup / restore
def backup(db: Path = config.DB_PATH, dest_dir: Path = config.BACKUP_DIR) -> Path:
    """Consistent online copy (SQLite backup API, safe while the DB is in use) -> gzip -> .sha256."""
    if not Path(db).exists():
        raise FileNotFoundError(f"database not found: {db}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    raw = dest_dir / f"{Path(db).stem}_{stamp}.sqlite"
    src, dst = sqlite3.connect(db), sqlite3.connect(raw)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    gz = raw.with_suffix(".sqlite.gz")
    with raw.open("rb") as fi, gzip.open(gz, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    raw.unlink()
    gz.with_suffix(".gz.sha256").write_text(f"{sha256_file(gz)}  {gz.name}\n", encoding="utf-8")
    return gz


def restore(backup_file: Path, db: Path = config.DB_PATH) -> Path:
    """Verify the checksum, keep the current DB as *.before_restore, then unpack the backup in its place."""
    backup_file = Path(backup_file)
    sumfile = backup_file.with_suffix(backup_file.suffix + ".sha256")
    if sumfile.exists():
        want = sumfile.read_text(encoding="utf-8").split()[0]
        if sha256_file(backup_file) != want:
            raise ValueError(f"checksum mismatch for {backup_file}; the backup is damaged")
    db = Path(db)
    if db.exists():
        shutil.copy2(db, db.with_suffix(".sqlite.before_restore"))
    tmp = db.with_suffix(".sqlite.restoring")
    with gzip.open(backup_file, "rb") as fi, tmp.open("wb") as fo:
        shutil.copyfileobj(fi, fo)
    chk = sqlite3.connect(tmp)
    n = chk.execute("PRAGMA integrity_check").fetchone()[0]
    chk.close()   # Windows cannot replace a file that is still open
    if n != "ok":
        tmp.unlink()
        raise ValueError(f"integrity check failed on the restored file: {n}")
    tmp.replace(db)
    return db


# ------------------------------------------------------------------ licences
def check_licenses(manifest: Path = config.MANIFEST_PATH) -> list[str]:
    """Problems that must be fixed before data is added or redistributed. Empty list = all good."""
    problems = []
    rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
    for r in rows:
        lic = (r.get("license") or "").strip()
        if not lic:
            problems.append(f"{r['doc_id']}: no licence/terms recorded")
        elif "no explicit" in lic.lower() and "academic" not in lic.lower():
            problems.append(f"{r['doc_id']}: terms not stated but not flagged 'academic use only'")
        for col in ("document_url", "collection_date", "sha256", "languages"):
            if not (r.get(col) or "").strip():
                problems.append(f"{r['doc_id']}: missing {col}")
        notes = (r.get("notes") or "").lower()
        if any(w in notes for w in ("aadhaar", "beneficiary list", "farmer name")):
            problems.append(f"{r['doc_id']}: notes mention personal data; exclude or aggregate before use")
    return problems


def license_summary(manifest: Path = config.MANIFEST_PATH) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in csv.DictReader(manifest.open(encoding="utf-8")):
        lic = r["license"] or ""
        key = "no stated licence: flagged academic use only" if "no explicit" in lic.lower() else lic[:70]
        out[key] = out.get(key, 0) + 1
    return out


# ------------------------------------------------------------------ add a source
def add_source(file: Path, source_id: str, source_group: str, document_url: str, license: str, period: str = "",
               languages: str = "en", notes: str = "", copy_into_corpus: bool = True) -> dict:
    """Register a new document: copy it into the corpus, append a manifest row (with sha256), return the row."""
    from agri.sources import SOURCES
    file = Path(file).expanduser().resolve()
    if not file.exists():
        raise FileNotFoundError(file)
    if source_id not in SOURCES:
        raise ValueError(f"unknown source_id {source_id}; add it to agri/sources.py first ({', '.join(SOURCES)})")
    if not license.strip():
        raise ValueError("a licence or terms statement is required (use 'No explicit licence. Flagged: academic use only.')")
    rows = list(csv.DictReader(config.MANIFEST_PATH.open(encoding="utf-8")))
    digest = sha256_file(file)
    if any(r["sha256"] == digest for r in rows):
        raise ValueError("this exact file is already in the manifest")
    nums = [int(r["doc_id"][1:]) for r in rows if r["doc_id"][1:].isdigit()]
    doc_id = f"D{max(nums) + 1:02d}"
    rel = Path("Added") / file.name
    if copy_into_corpus:
        (config.CORPUS_DIR / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, config.CORPUS_DIR / rel)
    pages = 0
    modality = "image" if file.suffix.lower() in (".png", ".jpg", ".jpeg") else "pdf_digital"
    if file.suffix.lower() == ".pdf":
        import pymupdf
        d = pymupdf.open(file)
        pages = len(d)
        if not "".join(p.get_text() for p in d).strip():
            modality = "pdf_scanned"
    row = {k: "" for k in MANIFEST_FIELDS}
    row.update({"doc_id": doc_id, "file_name": file.name, "relative_path": str(rel), "source_id": source_id,
                "source_name": SOURCES[source_id]["name"], "portal_url": SOURCES[source_id]["portal_url"],
                "document_url": document_url, "source_group": source_group, "period": period, "modality": modality,
                "pages": pages, "languages": languages, "scripts": "Devanagari+Latin" if "hi" in languages else "Latin",
                "legacy_font_encoding": "False", "size_bytes": file.stat().st_size, "sha256": digest,
                "collection_date": time.strftime("%Y-%m-%d"), "license": license, "notes": notes})
    fields = list(rows[0].keys()) if rows else MANIFEST_FIELDS
    with config.MANIFEST_PATH.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writerow({k: row.get(k, "") for k in fields})
    return row


# ------------------------------------------------------------------ logs
def prune_logs(days: int = 90, dry_run: bool = False) -> list[Path]:
    """Delete per-run traces and query logs older than `days`. Batch summaries and eval results are kept."""
    cutoff = time.time() - days * 86400
    old = [p for d in (config.TRACE_DIR, config.LOG_DIR / "queries") if d.exists()
           for p in d.glob("*.jsonl") if p.stat().st_mtime < cutoff]
    if not dry_run:
        for p in old:
            p.unlink()
    return old


# ------------------------------------------------------------------ status
def status(db: Path = config.DB_PATH) -> dict:
    out = {"db": str(db), "db_exists": Path(db).exists(), "corpus_dir": str(config.CORPUS_DIR),
           "llm_backend": config.LLM_BACKEND, "base_model": config.BASE_MODEL}
    if Path(db).exists():
        c = sqlite3.connect(db)
        out.update({
            "schema_version": (c.execute("SELECT value FROM meta_schema WHERE key='schema_version'").fetchone() or ["v1"])[0]
            if c.execute("SELECT name FROM sqlite_master WHERE name='meta_schema'").fetchone() else "v1",
            "observations": c.execute("SELECT COUNT(*) FROM observation").fetchone()[0],
            "documents_with_data": c.execute("SELECT COUNT(DISTINCT document_id) FROM observation").fetchone()[0],
            "locations_geocoded": c.execute("SELECT COUNT(*) FROM location WHERE lat IS NOT NULL").fetchone()[0]
            if "lat" in {r[1] for r in c.execute("PRAGMA table_info(location)")} else 0,
            "last_run": c.execute("SELECT MAX(finished_at) FROM extraction_run").fetchone()[0]})
    out["corpus_files"] = sum(1 for r in csv.DictReader(config.MANIFEST_PATH.open(encoding="utf-8"))
                              if (config.CORPUS_DIR / r["relative_path"]).exists())
    out["manifest_rows"] = sum(1 for _ in csv.DictReader(config.MANIFEST_PATH.open(encoding="utf-8")))
    return out
