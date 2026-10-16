"""Step-level trace of every agent run.

Each step records WHO decided (model vs rule/code), WHAT (decision, tool call,
tool result, output, error) and the payload. Traces are written as JSONL under
logs/traces/<run_id>.jsonl and, when LANGSMITH_API_KEY is set, the same tool
and LLM calls appear in LangSmith through @traceable.

`to_messages()` converts a trace into the OpenAI-style message list that
AgentEvals trajectory evaluators expect.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from agri.config import TRACE_DIR


def _short(obj, limit: int = 1200):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + f"... [{len(s) - limit} more chars]"


class Tracer:
    def __init__(self, run_id: str, agent_id: str, document_id: str):
        self.run_id, self.agent_id, self.document_id = run_id, agent_id, document_id
        self.steps: list[dict] = []
        self.path: Path = TRACE_DIR / f"{run_id}.jsonl"
        self.t0 = time.time()

    def _add(self, kind: str, name: str, by: str, payload) -> dict:
        step = {"i": len(self.steps), "t": round(time.time() - self.t0, 3), "agent": self.agent_id,
                "kind": kind, "name": name, "by": by, "payload": payload}
        self.steps.append(step)
        return step

    # by = "model" when an LLM produced the decision, "rule" when fixed code did.
    def decision(self, name: str, by: str, detail):
        return self._add("decision", name, by, detail)

    def tool_call(self, name: str, args: dict):
        return self._add("tool_call", name, "agent", args)

    def tool_result(self, name: str, result, ok: bool = True):
        return self._add("tool_result", name, "tool", {"ok": ok, "result": result})

    def output(self, name: str, detail):
        return self._add("output", name, "agent", detail)

    def error(self, name: str, detail, handled_by: str = ""):
        return self._add("error", name, "agent", {"error": detail, "handled_by": handled_by})

    def save(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            for s in self.steps:
                f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")
        return str(self.path)

    def tool_sequence(self) -> list[str]:
        return [s["name"] for s in self.steps if s["kind"] == "tool_call"]

    def to_messages(self, task: str) -> list[dict]:
        """OpenAI-format trajectory for agentevals (assistant tool_calls + tool results)."""
        msgs: list[dict] = [{"role": "user", "content": task}]
        for s in self.steps:
            if s["kind"] == "tool_call":
                msgs.append({"role": "assistant", "content": "",
                             "tool_calls": [{"function": {"name": s["name"], "arguments": json.dumps(s["payload"], default=str)}}]})
            elif s["kind"] == "tool_result":
                msgs.append({"role": "tool", "content": _short(s["payload"], 400)})
        final = [s for s in self.steps if s["kind"] == "output"]
        msgs.append({"role": "assistant", "content": _short(final[-1]["payload"] if final else "no output", 400)})
        return msgs

    def pretty(self, max_payload: int = 300) -> str:
        lines = []
        for s in self.steps:
            lines.append(f"[{s['i']:>3}] {s['t']:>7.2f}s {s['kind']:<11} {s['name']:<28} by={s['by']:<5} {_short(s['payload'], max_payload)}")
        return "\n".join(lines)
