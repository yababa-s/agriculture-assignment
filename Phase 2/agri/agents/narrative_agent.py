"""G5 narrative agent: budget memoranda (scheme outlay/expenditure) and descriptive reports.

  rule  : segment memoranda by 'Name of the Scheme'; regex reads the Outlay/Expenditure block
  model : summarise each scheme / report page into typed facts with a verbatim evidence span
  rule  : evidence must be found in the page (exact, or rapidfuzz partial ratio >= 92)
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from agri.agents.base import AgentContext, AgentResult, BaseAgent, make_record
from agri.tools.parsing import parse_period
from agri.tools.pdf_tools import page_texts

PREDICATES = ["objective", "provides_input", "subsidy_rate", "covers_crop", "production_cluster", "major_produce",
              "scheme_or_initiative", "infrastructure", "market_linkage", "opportunity", "statistic"]

SYSTEM = (
    "You extract facts about agriculture and food processing in the Andaman & Nicobar Islands from report text. "
    "Return a JSON list only. Each item: {\"subject\": <short noun phrase>, \"predicate\": <one of "
    + ", ".join(PREDICATES) + ">, \"object\": <short phrase>, \"evidence\": <sentence copied exactly from the text>}. "
    "At most 8 facts. Only facts stated in the text."
)

_SCHEME = re.compile(r"Name of the Scheme\s*:\s*(.*)")
_YEARS = re.compile(r"((?:19|20)\d{2}-\d{2})")
_NUM = re.compile(r"^\s*(\d[\d,]*\.\d+|\d[\d,]*)\s*$")


def segment_schemes(pages: list[str]) -> list[dict]:
    out = []
    for pno, text in enumerate(pages, start=1):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = _SCHEME.search(line)
            if not m:
                continue
            name = m.group(1).strip()
            j = i + 1
            while not name or (j < len(lines) and lines[j].strip() and "brief description" not in lines[j].lower() and j <= i + 2):
                if j >= len(lines) or "brief description" in lines[j].lower():
                    break
                name = (name + " " + lines[j].strip()).strip()
                j += 1
            out.append({"page": pno, "line": i, "name": " ".join(name.split())})
    # attach text up to the next scheme
    for k, s in enumerate(out):
        nxt = out[k + 1] if k + 1 < len(out) else None
        chunk = []
        for pno in range(s["page"], (nxt["page"] if nxt else len(pages)) + 1):
            lines = pages[pno - 1].splitlines()
            a = s["line"] if pno == s["page"] else 0
            b = nxt["line"] if nxt and pno == nxt["page"] else len(lines)
            chunk.extend(lines[a:b])
        s["text"] = "\n".join(chunk)
    return out


def outlay_block(text: str) -> list[dict]:
    """Read 'Outlay and Expenditure (Rs. in Lakhs)' -> [{year, outlay, expenditure}]."""
    i = text.find("Outlay and Expenditure")
    if i < 0:
        return []
    seg = text[i:i + 600]
    years = _YEARS.findall(seg)[:3]
    lines = [ln.strip() for ln in seg.splitlines()]
    vals = {"Outlay": [], "Expenditure": []}
    cur = None
    for ln in lines:
        if ln in vals:
            cur = ln
            continue
        m = _NUM.match(ln)
        if cur and m and len(vals[cur]) < len(years):
            vals[cur].append(m.group(1))
        elif cur and ln and not m and len(vals[cur]) >= len(years):
            cur = None
    out = []
    for k, y in enumerate(years):
        out.append({"year": y, "outlay": vals["Outlay"][k] if k < len(vals["Outlay"]) else None,
                    "expenditure": vals["Expenditure"][k] if k < len(vals["Expenditure"]) else None})
    return out


def grounded(evidence: str, text: str) -> bool:
    ev = " ".join((evidence or "").split())
    flat = " ".join(text.split())
    if len(ev) < 15:
        return False
    return ev in flat or fuzz.partial_ratio(ev, flat) >= 92


class NarrativeAgent(BaseAgent):
    agent_id = "narrative_agent"
    uses_llm = True
    description = "Scheme memoranda + reports -> outlay observations (rules) and typed text facts (LLM, grounded)"

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        pages = list(page_texts(str(ctx.path)))
        schemes = self.tool(ctx, "segment_schemes", segment_schemes, pages=pages,
                            summarize=lambda ss: [{"page": s["page"], "name": s["name"][:60]} for s in ss])
        ctx.tracer.decision("document_kind", "rule", {"kind": "budget_memoranda" if schemes else "report",
                                                       "reason": "'Name of the Scheme' headings found" if schemes else "no scheme headings"})
        stats = {"schemes": len(schemes), "outlay_records": 0, "facts": 0, "facts_rejected": 0}
        units = [("scheme_outlay", "outlay"), ("scheme_expenditure", "expenditure")]
        if schemes:
            for s in schemes:
                block = self.tool(ctx, "read_outlay_block", outlay_block, text=s["text"])
                for row in block:
                    for metric, key in units:
                        raw = row.get(key)
                        if raw is None:
                            continue
                        result.records.append(make_record(
                            ctx, self.agent_id, metric_id=metric, location_id="AN",
                            period=parse_period(row["year"], "fiscal_year"), value=float(raw.replace(",", "")),
                            value_raw=raw, missing_reason=None, unit_id="inr_lakh", dims={"scheme": s["name"]},
                            page=s["page"], table_ref="outlay_and_expenditure", row_label=key.title(), col_label=row["year"]))
                        stats["outlay_records"] += 1
                desc = s["text"][:1800]
                self._facts(ctx, result, stats, desc, s["page"], subject_hint=s["name"])
        else:
            for pno, text in enumerate(pages, start=1):
                if len(text.strip()) < 300:
                    continue
                self._facts(ctx, result, stats, text[:2500], pno)
        result.stats = stats
        ctx.tracer.output("records", {"observations": len(result.records), "facts": len(result.facts), **stats})
        return result

    def _facts(self, ctx, result, stats, text, page, subject_hint=None):
        if not (ctx.use_llm and ctx.general_llm.enabled):
            return
        user = (f"Scheme: {subject_hint}\n" if subject_hint else "") + f"Text (page {page}):\n{text}"
        r = self.tool(ctx, "llm_extract_facts", lambda: ctx.general_llm.json_call(SYSTEM, user, max_tokens=700),
                      summarize=lambda r: {"ok": r.ok, "error": r.error, "n": len(r.parsed) if isinstance(r.parsed, list) else 0,
                                           "latency_s": round(r.latency_s, 1)}, page=page)
        if not r.ok or not isinstance(r.parsed, list):
            ctx.tracer.error("llm_extract_facts", r.error, handled_by="skip_page")
            return
        rejected = []
        for f in r.parsed:
            if not isinstance(f, dict) or f.get("predicate") not in PREDICATES or not grounded(f.get("evidence", ""), text):
                rejected.append((f.get("predicate") if isinstance(f, dict) else None))
                continue
            result.facts.append({"subject": str(f.get("subject") or subject_hint or "")[:200], "predicate": f["predicate"],
                                 "object": str(f.get("object"))[:300], "location_id": "AN",
                                 "period_label": ctx.document.get("period_label"), "document_id": ctx.doc_id, "page": page,
                                 "evidence": " ".join(f["evidence"].split())[:600], "run_id": ctx.run_id, "agent_id": self.agent_id})
        stats["facts"] += len(r.parsed) - len(rejected)
        stats["facts_rejected"] += len(rejected)
        ctx.tracer.decision("extract_facts", "model", {"page": page, "accepted": len(r.parsed) - len(rejected), "rejected": rejected[:6]})
