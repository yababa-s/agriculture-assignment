from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from krutidev import decode_kruti_label
from run_pipeline import DB, ROOT, load_manifest, now

PHASE2 = Path(__file__).resolve().parent

GOLD = [
    ("basic statistics report 2024-25.pdf", "area_cultivated", "Paddy", "2024-25", 4365.2, "hectare"),
    ("basic statistics report 2024-25.pdf", "production", "Paddy", "2024-25", 13490.2, "MT"),
    ("basic statistics report 2024-25.pdf", "area_cultivated", "Coconut", "2024-25", 17902.0, "hectare"),
    ("basic statistics report 2024-25.pdf", "production", "Coconut", "2024-25", 112.1167, "million nuts"),
]


def main() -> int:
    if not DB.exists():
        raise SystemExit("Database not found. Run: python phase2/run_pipeline.py --fresh")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    run = conn.execute("SELECT * FROM extraction_run ORDER BY started_at DESC LIMIT 1").fetchone()
    run_summary_path = PHASE2 / "logs" / f"run_{run['run_id']}.json"
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    docs = conn.execute("SELECT COUNT(*) FROM source_document").fetchone()[0]
    cells = conn.execute("SELECT COUNT(*) FROM table_cell WHERE run_id=?", (run["run_id"],)).fetchone()[0]
    observations = conn.execute("SELECT COUNT(*) FROM observation WHERE run_id=?", (run["run_id"],)).fetchone()[0]
    checks = []
    for file_name, metric, commodity, period, expected, unit in GOLD:
        row = conn.execute("""SELECT o.value,o.unit,o.value_raw,o.page,o.table_no,o.row_no,o.col_no,d.doc_id
          FROM observation o JOIN source_document d USING(doc_id)
          WHERE d.file_name=? AND o.metric=? AND o.commodity=? AND o.period=? AND o.unit=?
          ORDER BY o.page,o.table_no,o.row_no,o.col_no LIMIT 1""",
          (file_name, metric, commodity, period, unit)).fetchone()
        ok = row is not None and abs(row["value"] - expected) < 1e-8
        checks.append({"file": file_name, "metric": metric, "commodity": commodity, "period": period,
                       "expected": expected, "found": row["value"] if row else None, "unit": unit,
                       "correct": bool(ok), "source": dict(row) if row else None})
    examples = [
        ("Qlyksa dk uke", "फसलों का नाम", "D03 source example"),
        ("Ukkfj;y", "नारियल", "D03 source example"),
        ("/kku", "धान", "D03 source example"),
        ("frygu", "तिलहन", "D04 held-out source example"),
        ("nf{k.k v.Meku", "दक्षिण अण्डमान", "D04 held-out source example"),
    ]
    decoder = [{"legacy": a, "expected": b, "found": decode_kruti_label(a), "source_split": src,
                "correct": decode_kruti_label(a) == b} for a, b, src in examples]
    manifest = load_manifest()
    mapping_ok = len(manifest) == docs and all((ROOT / "corpus" / d["relative_path"]).exists() for d in manifest)
    route_map = {"G1_AREA_PRODUCTION": "pdf_table_agent", "G2_BASIC_STATS": "pdf_table_agent",
                 "G3_ISLAND_PROFILES": "pdf_text_agent", "G4_NARRATIVE": "pdf_text_agent",
                 "G5_PRICES": "pdf_table_agent", "G6_CENSUS_IMAGE": "pending_image_ocr",
                 "G7_LULC": "pdf_table_agent", "G8_RASTER_MAPS": "skip_agent"}
    manifest_by_id = {d["doc_id"]: d for d in manifest}
    traces = {}
    with (ROOT / run_summary["trace"]).open(encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            traces.setdefault(event["doc_id"], []).append(event)
    route_rows = []
    trajectory_rows = []
    tool_inputs = []
    grounded_rows = []
    tool_by_agent = {}
    for item in run_summary["documents"]:
        doc_id = item["doc_id"]
        events = traces.get(doc_id, [])
        route_event = next((e for e in events if e["event"] == "route"), None)
        expected_agent = route_map[item["group"]]
        routed_agent = (route_event or {}).get("detail", {}).get("agent")
        route_ok = routed_agent == expected_agent == item["agent"]
        route_rows.append({"doc_id": doc_id, "expected": expected_agent, "found": item["agent"], "correct": route_ok})
        actual_calls = [e["detail"] for e in events if e["event"] == "tool_call"]
        expected_tools = (["pdfplumber_extract_tables"] if expected_agent == "pdf_table_agent" else
                          ["pdfplumber_extract_text"] if expected_agent == "pdf_text_agent" else [])
        found_tools = [call.get("tool") for call in actual_calls]
        trajectory_ok = found_tools == expected_tools
        trajectory_rows.append({"doc_id": doc_id, "expected_tools": expected_tools,
                                "found_tools": found_tools, "correct": trajectory_ok})
        tool_by_agent.setdefault(item["agent"], {"tool_calls": 0, "valid_inputs": 0, "matching_trajectories": 0, "documents": 0})
        agent_summary = tool_by_agent[item["agent"]]
        agent_summary["documents"] += 1
        agent_summary["tool_calls"] += len(actual_calls)
        agent_summary["matching_trajectories"] += int(trajectory_ok)
        rel = manifest_by_id[doc_id]["relative_path"]
        expected_path = str((ROOT / "corpus" / rel).resolve())
        for call in actual_calls:
            ok = call.get("path") == expected_path and call.get("args_validated") is True
            tool_inputs.append({"doc_id": doc_id, "tool": call.get("tool"), "valid": ok})
            agent_summary["valid_inputs"] += int(ok)
    for row in conn.execute("""SELECT o.doc_id,o.value_raw,o.page,o.table_no,o.row_no,o.col_no,
            c.value_raw AS cell_value
        FROM observation o JOIN table_cell c ON c.doc_id=o.doc_id AND c.page=o.page AND c.table_no=o.table_no
          AND c.row_no=o.row_no AND c.col_no=o.col_no
        WHERE o.run_id=?""", (run["run_id"],)):
        grounded_rows.append({"doc_id": row["doc_id"], "raw_value": row["value_raw"],
                              "table_cell": row["cell_value"], "grounded": row["value_raw"] == row["cell_value"]})
    source_groups = {}
    for group in sorted({d["group"] for d in run_summary["documents"]}):
        records = [d for d in run_summary["documents"] if d["group"] == group]
        source_groups[group] = {"attempted": len(records), "loaded": sum(d["status"] == "loaded" for d in records),
                                "partial": sum(d["status"] == "partial" for d in records),
                                "pending": sum(d["status"] == "pending" for d in records),
                                "skipped": sum(d["status"] == "skipped" for d in records),
                                "failed": sum(d["status"] == "failed" for d in records)}
    status_counts = run_summary.get("status_counts", {})
    fully_handled = run_summary.get("completed_without_intervention", 0)
    workflow = {"run_id": run["run_id"], "sources_in_manifest": len(manifest), "sources_in_database": docs,
                "manifest_paths_valid": mapping_ok, "table_cells_saved": cells,
                "route_selection_correct": sum(x["correct"] for x in route_rows),
                "route_selection_cases": len(route_rows),
                "trajectory_match_correct": sum(x["correct"] for x in trajectory_rows),
                "trajectory_cases": len(trajectory_rows),
                "tool_inputs_correct": sum(x["valid"] for x in tool_inputs),
                "tool_input_cases": len(tool_inputs),
                "grounded_observations": sum(x["grounded"] for x in grounded_rows),
                "groundedness_cases": len(grounded_rows),
                "structured_observations": observations, "gold_values_correct": sum(x["correct"] for x in checks),
                "gold_value_checks": len(checks), "decoder_examples_correct": sum(x["correct"] for x in decoder),
                "decoder_examples": len(decoder), "manual_interventions": run["manual_interventions"],
                "fully_handled_without_manual_intervention": fully_handled,
                "inputs_attempted": run["attempted"],
                "automation_completion_ratio": f"{fully_handled}/{run['attempted']}",
                "status_counts": status_counts,
                "full_automation_claim": False}
    report = {"generated_at": now(), "workflow": workflow, "per_source_group": source_groups,
        "per_agent": {**{row[0]: dict(row) for row in conn.execute("""SELECT agent_id,COUNT(*) AS records FROM (
          SELECT agent_id FROM table_cell WHERE run_id=? UNION ALL SELECT agent_id FROM text_fact WHERE run_id=?
        ) GROUP BY agent_id""", (run["run_id"], run["run_id"]))},
          **tool_by_agent},
        "routing_checks": route_rows, "trajectory_checks": trajectory_rows, "tool_input_checks": tool_inputs,
        "groundedness_checks": grounded_rows,
        "checked_values": checks, "decoder_checks": decoder,
        "pending_sources": [d["file_name"] for d in manifest if d["implementation_status"].startswith("pending")],
        "skipped_sources": [d["file_name"] for d in manifest if d["implementation_status"].startswith("out of scope")],
        "limitations": ["Only the supplied Phase 1 corpus was used.", "No model fine-tuning was run.",
                        "The local evaluator checks trajectories against fixed tool sequences; AgentEvals and hosted LangSmith still require installation/configuration."]}
    out = PHASE2 / "evaluation" / "latest_evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(workflow, ensure_ascii=False, indent=2))
    print(f"Evaluation details: {out}")
    conn.close()
    return 0 if mapping_ok and all(x["correct"] for x in checks) and all(x["correct"] for x in decoder) else 1


if __name__ == "__main__":
    raise SystemExit(main())
