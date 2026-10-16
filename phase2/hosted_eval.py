"""Optional AgentEvals + LangSmith trajectory check for the latest local run.

This sends only source-group labels and tool names to LangSmith. It deliberately
does not upload PDF text, extracted values, or local filesystem paths.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agentevals.trajectory.match import create_trajectory_match_evaluator
from langsmith import Client

PHASE2 = Path(__file__).resolve().parent
ROOT = PHASE2.parent
REPORT = PHASE2 / "evaluation" / "latest_evaluation.json"
GROUP_TOOL = {
    "G1_AREA_PRODUCTION": "pdfplumber_extract_tables",
    "G2_BASIC_STATS": "pdfplumber_extract_tables",
    "G3_ISLAND_PROFILES": "pdfplumber_extract_text",
    "G4_NARRATIVE": "pdfplumber_extract_text",
    "G5_PRICES": "pdfplumber_extract_tables",
    "G6_CENSUS_IMAGE": None,
    "G7_LULC": "pdfplumber_extract_tables",
    "G8_RASTER_MAPS": None,
}


def trajectory(group: str) -> list[dict]:
    messages = [{"role": "user", "content": f"Process the {group} source group."}]
    tool = GROUP_TOOL[group]
    if tool:
        messages.append({"role": "assistant", "content": "", "tool_calls": [{
            "function": {"name": tool, "arguments": json.dumps({"source_group": group})}
        }]})
        messages.append({"role": "tool", "content": "Extraction completed; result recorded in the local SQLite database."})
    messages.append({"role": "assistant", "content": "Processing status recorded."})
    return messages


def main() -> int:
    if not os.getenv("LANGSMITH_API_KEY"):
        raise SystemExit("Set LANGSMITH_API_KEY before running the optional hosted evaluation.")
    if not REPORT.exists():
        raise SystemExit("Run phase2/run_pipeline.py and phase2/evaluate.py first.")
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    run_id = report["workflow"]["run_id"]
    summary = json.loads((PHASE2 / "logs" / f"run_{run_id}.json").read_text(encoding="utf-8"))
    trace_path = ROOT / summary["trace"]
    trace_by_doc: dict[str, list[dict]] = {}
    with trace_path.open(encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            trace_by_doc.setdefault(event["doc_id"], []).append(event)
    examples = []
    for item in report["routing_checks"]:
        doc = next(d for d in summary["documents"] if d["doc_id"] == item["doc_id"])
        group = doc["group"]
        expected = trajectory(group)
        actual = [{"role": "user", "content": f"Process the {group} source group."}]
        calls = [event["detail"].get("tool") for event in trace_by_doc.get(item["doc_id"], [])
                 if event["event"] == "tool_call"]
        if calls:
            actual.append({"role": "assistant", "content": "", "tool_calls": [{
                "function": {"name": name, "arguments": json.dumps({"source_group": group})}
            } for name in calls]})
            actual.append({"role": "tool", "content": "Extraction completed; result recorded in the local SQLite database."})
        actual.append({"role": "assistant", "content": "Processing status recorded."})
        examples.append({"inputs": {"source_group": group, "doc_id": item["doc_id"]},
                         "outputs": {"messages": expected}, "actual": {"messages": actual},
                         "metadata": {"doc_id": item["doc_id"], "evaluation": "tool-trajectory-only"}})

    client = Client()
    dataset_name = f"agriculture-phase2-{report['workflow']['run_id']}"
    dataset = client.create_dataset(dataset_name, description="Phase 2 source-group tool trajectory checks; no source content included.")
    client.create_examples(dataset_id=dataset.id, examples=[{
        "inputs": row["inputs"], "outputs": row["outputs"], "metadata": row["metadata"]
    } for row in examples])
    trajectory_evaluator = create_trajectory_match_evaluator(trajectory_match_mode="strict")

    def target(inputs: dict) -> dict:
        row = next(ex for ex in examples if ex["inputs"]["doc_id"] == inputs["doc_id"])
        return row["actual"]

    def evaluator(run, example):
        return trajectory_evaluator(outputs=run.outputs["messages"],
                                    reference_outputs=example.outputs["messages"])

    result = client.evaluate(target, data=dataset_name, evaluators=[evaluator],
                             experiment_prefix="phase2-agent-trajectories")
    print(f"LangSmith dataset: {dataset_name}")
    print("Experiment submitted. Open the run in LangSmith to inspect example-level scores.")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
