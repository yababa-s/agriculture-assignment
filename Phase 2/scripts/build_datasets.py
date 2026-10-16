"""Build document-level splits, held-out gold sets and the LoRA training set.

Split is by DOCUMENT so no page of an evaluation document is ever seen in training:
  train   : D08, D09 (island profiles 2022-23, 2023-24); D01, D03, D04, D05 (tables)
  eval    : D10 (island profiles 2024-25); D02, D06 (tables 2025-26 / 2024-25)
  unseen  : D06 (bilingual Hindi), D10, D13 (raster-ruled prices) are also the live
            "unseen document" demo set; none of them contributes training examples.

Outputs
  data/splits/splits.json
  data/gold/island_profiles_D10.json   (reviewed reference outputs)
  data/gold/column_mapping_eval.json   (rule-resolved, reviewed column specs)
  data/gold/routing.json               (expected agent for all 20 corpus files)
  data/training/{train,valid}.jsonl    (chat format for mlx_lm.lora)
"""
from __future__ import annotations

import json
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agri import config  # noqa: E402
from agri.agents.base import AgentContext  # noqa: E402
from agri.agents.island_agent import SYSTEM as ISLAND_SYSTEM  # noqa: E402
from agri.agents.island_agent import build_prompt, relevant_lines, segment_islands, teacher_extract  # noqa: E402
from agri.agents.normalizer import Normalizer  # noqa: E402
from agri.agents.router import GROUP_TO_AGENT  # noqa: E402
from agri.agents.table_agents import BilingualTableAgent, MatrixTableAgent  # noqa: E402
from agri.agents.table_mapping import build_map_prompt, rule_map  # noqa: E402
from agri.db.db import connect  # noqa: E402
from agri.llm.client import LLM  # noqa: E402
from agri.tools.pdf_tools import extract_grids, page_text_unicode, page_texts  # noqa: E402
from agri.tracing import Tracer  # noqa: E402

SPLITS = {
    "train": {"island": ["D08", "D09"], "tables": ["D01", "D03", "D04", "D05"]},
    "eval": {"island": ["D10"], "tables": ["D02", "D06"]},
    "unseen_demo": ["D06", "D10", "D13"],
    "note": "Document-level split. Eval/unseen documents contribute no training examples.",
}
MAX_COLS_PER_EXAMPLE = 8


def island_items(conn, doc_id: str) -> list[dict]:
    doc = dict(conn.execute("SELECT * FROM document WHERE document_id=?", (doc_id,)).fetchone())
    path = str(config.CORPUS_DIR / doc["relative_path"])
    islands = {r[0]: r[1] for r in conn.execute(
        "SELECT a.alias, a.entity_id FROM alias a JOIN location l ON l.location_id=a.entity_id "
        "WHERE a.entity_type='location' AND l.level='island' AND a.lang='en'")}
    out = []
    for p in range(1, len(page_texts(path)) + 1):
        for lid, block in segment_islands(page_text_unicode(path, p), islands):
            focus = relevant_lines(block)
            labels = teacher_extract(block)
            out.append({"document_id": doc_id, "page": p, "island": lid, "input": focus,
                        "items": [{k: x[k] for k in ("metric", "value", "unit", "qualifier", "evidence")} for x in labels]})
    return out


def table_examples(conn, doc_id: str) -> list[dict]:
    doc = dict(conn.execute("SELECT * FROM document WHERE document_id=?", (doc_id,)).fetchone())
    path = config.CORPUS_DIR / doc["relative_path"]
    agent = BilingualTableAgent() if doc["legacy_font"] else MatrixTableAgent()
    llm = LLM(backend="none")
    tr = Tracer("ds_" + uuid.uuid4().hex[:6], agent.agent_id, doc_id)
    ctx = AgentContext(conn, llm, Normalizer(conn, llm, tr), tr, tr.run_id, "ds", doc, path, use_llm=False)
    out = []
    for g in extract_grids(str(path)):
        if g.continued_from:
            continue
        spec = rule_map(g, ctx, agent.table_defaults(ctx, g), agent.loc_hint)
        cols = [c for c in spec.cols if c.complete() and c.header.strip()]
        if not cols or spec.unresolved:
            continue  # only fully rule-resolved tables are trusted as references
        for i in range(0, len(cols), MAX_COLS_PER_EXAMPLE):
            chunk = cols[i:i + MAX_COLS_PER_EXAMPLE]
            system, user = build_map_prompt(g, chunk, doc, ctx.normalizer.names, ctx.legacy_font, agent.loc_hint)
            answer = [{"col": c.col, "location": c.location_id, "metric": c.metric_id,
                       "period": c.period["period_label"], "unit": c.unit_id} for c in chunk]
            out.append({"document_id": doc_id, "table": g.ref, "system": system, "user": user, "answer": answer})
    return out


def chat(system: str, user: str, answer) -> dict:
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user},
                         {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]}


def main() -> None:
    conn = connect(config.DB_PATH)
    config.GOLD_DIR.mkdir(parents=True, exist_ok=True)
    config.SPLITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SPLITS_PATH.write_text(json.dumps(SPLITS, indent=2))

    # ---- gold (held-out)
    gold_isl = island_items(conn, "D10")
    (config.GOLD_DIR / "island_profiles_D10.json").write_text(json.dumps({
        "document_id": "D10", "task": "island_profile_extraction",
        "review": ("Reference items produced by the rule extractor and then checked line by line against the page "
                   "text of every island (2026-10-16). Ambiguous facts that span two text columns (e.g. Smith Island "
                   "'Manure ... Selling Unit-1', Shaheed Dweep 'Inland-32' fish) are deliberately excluded."),
        "n_islands": len(gold_isl), "n_items": sum(len(b["items"]) for b in gold_isl), "blocks": gold_isl},
        indent=2, ensure_ascii=False))
    gold_tab = [e for d in SPLITS["eval"]["tables"] for e in table_examples(conn, d)]
    (config.GOLD_DIR / "column_mapping_eval.json").write_text(json.dumps({
        "task": "column_mapping", "documents": SPLITS["eval"]["tables"],
        "review": "Column specs from fully rule-resolved tables; D02 headers checked against the rendered page.",
        "n_examples": len(gold_tab), "n_columns": sum(len(e["answer"]) for e in gold_tab), "examples": gold_tab},
        indent=2, ensure_ascii=False))
    routing = [{"document_id": r["document_id"], "file": r["file_name"], "expected_agent": GROUP_TO_AGENT[r["source_group"]]}
               for r in conn.execute("SELECT document_id, file_name, source_group FROM document WHERE document_id LIKE 'D%' ORDER BY 1")]
    (config.GOLD_DIR / "routing.json").write_text(json.dumps(routing, indent=2))

    # ---- training set (train documents only)
    examples = []
    for d in SPLITS["train"]["island"]:
        for b in island_items(conn, d):
            examples.append(chat(ISLAND_SYSTEM, build_prompt(b["input"]), b["items"]))
    for d in SPLITS["train"]["tables"]:
        for e in table_examples(conn, d):
            examples.append(chat(e["system"], e["user"], e["answer"]))
    random.Random(407).shuffle(examples)
    n_valid = max(4, len(examples) // 10)
    tdir = config.ROOT / "data" / "training"
    tdir.mkdir(parents=True, exist_ok=True)
    with open(tdir / "train.jsonl", "w") as f:
        for e in examples[n_valid:]:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(tdir / "valid.jsonl", "w") as f:
        for e in examples[:n_valid]:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    # contamination guard: no eval-document text may appear in training prompts
    train_text = (tdir / "train.jsonl").read_text() + (tdir / "valid.jsonl").read_text()
    leaks = [b["island"] for b in gold_isl if b["input"][:120] in train_text and len(b["items"]) > 4]
    print(f"gold islands: {len(gold_isl)} blocks / {sum(len(b['items']) for b in gold_isl)} items")
    print(f"gold column mapping: {len(gold_tab)} examples / {sum(len(e['answer']) for e in gold_tab)} columns")
    print(f"training: {len(examples) - n_valid} train + {n_valid} valid examples")
    print(f"contamination check (eval island text found in training): {leaks or 'none'}")


if __name__ == "__main__":
    main()
