"""Shared agent scaffolding: context, result, tool invocation with tracing, record construction."""
from __future__ import annotations

import inspect
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from langsmith import traceable

from agri.agents.normalizer import Normalizer
from agri.llm.client import LLM
from agri.tracing import Tracer


@dataclass
class AgentContext:
    conn: sqlite3.Connection
    llm: LLM
    normalizer: Normalizer
    tracer: Tracer
    run_id: str
    batch_id: str
    document: dict          # row from `document`
    path: Path
    attempt: int = 1
    feedback: str = ""      # validator feedback from a previous attempt (retry loop)
    use_llm: bool = True
    base_llm: LLM | None = None   # model without adapter, for tasks the adapter was not trained on

    @property
    def general_llm(self) -> LLM:
        return self.base_llm or self.llm

    @property
    def doc_id(self) -> str:
        return self.document["document_id"]

    @property
    def legacy_font(self) -> bool:
        return bool(self.document.get("legacy_font"))


@dataclass
class AgentResult:
    records: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    status: str = "ok"                  # ok | partial | failed | skipped
    notes: list[str] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)   # labels/columns the agent could not map
    stats: dict = field(default_factory=dict)


class BaseAgent:
    agent_id = "base"
    uses_llm = False
    description = ""

    def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - interface
        raise NotImplementedError

    def tool(self, ctx: AgentContext, name: str, fn, summarize=None, **args):
        """Invoke a tool and record the call + (summarised) result in the trace."""
        ctx.tracer.tool_call(name, {k: _arg_summary(v) for k, v in args.items()})
        try:
            params = inspect.signature(fn).parameters
            accepts_all = any(p.kind == p.VAR_KEYWORD for p in params.values())
            call_args = args if accepts_all else {k: v for k, v in args.items() if k in params}
            # extra keyword arguments are trace-only context (e.g. island=, attempt=)
            res = traceable(name=name, run_type="tool")(fn)(**call_args)
        except Exception as e:  # noqa: BLE001
            ctx.tracer.tool_result(name, f"{type(e).__name__}: {e}", ok=False)
            raise
        ctx.tracer.tool_result(name, summarize(res) if summarize else res)
        return res


def _arg_summary(v):
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, str) and len(v) > 200:
        return f"<text {len(v)} chars: {v[:80]!r}...>"
    if isinstance(v, (list, tuple)) and v and isinstance(v[0], str) and sum(len(x) for x in v) > 200:
        return f"<{len(v)} texts, {sum(len(x) for x in v)} chars>"
    return v


def make_record(ctx: AgentContext, agent_id: str, *, metric_id: str, location_id: str, period: dict,
                value: float | None, value_raw: str, missing_reason: str | None, unit_id: str | None,
                commodity_id: str | None = None, unit_raw: str | None = None, dims: dict | None = None,
                page: int | None = None, table_ref: str | None = None, row_label: str | None = None,
                col_label: str | None = None, is_total_row: bool = False, confidence: float = 1.0,
                season: str | None = None) -> dict:
    return {
        "metric_id": metric_id, "commodity_id": commodity_id, "location_id": location_id,
        "period_label": period["period_label"], "period_type": period["period_type"],
        "period_start": period["period_start"], "period_end": period["period_end"], "season": season,
        "dims": dims or {}, "value": value, "unit_id": unit_id, "value_raw": value_raw or "", "unit_raw": unit_raw,
        "missing_reason": missing_reason, "is_total_row": 1 if is_total_row else 0,
        "document_id": ctx.doc_id, "page": page, "table_ref": table_ref, "row_label": row_label,
        "col_label": col_label, "run_id": ctx.run_id, "agent_id": agent_id, "confidence": confidence,
        "validation": "ok", "validation_note": None,
    }
