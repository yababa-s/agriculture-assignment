"""Router (supervisor) agent: decide which extraction agent handles a document.

Known corpus files carry a source group in the manifest -> routed by rule.
Unseen files (instructor documents, new downloads) -> fingerprinted with tools and
classified by the LLM; the answer must be one of the registered agents or 'skip',
otherwise a fingerprint heuristic decides. `force_llm=True` routes every file
through the model (used to evaluate tool-selection accuracy).
"""
from __future__ import annotations

from pathlib import Path

from agri.agents.base import AgentContext, BaseAgent
from agri.tools.lang import detect_languages

GROUP_TO_AGENT = {
    "G1_MATRIX_TABLES": "matrix_table_agent",
    "G2_BILINGUAL_TABLES": "bilingual_table_agent",
    "G3_PRICE_TABLES": "price_table_agent",
    "G4_ISLAND_PROFILES": "island_profile_agent",
    "G5_NARRATIVE": "narrative_agent",
    "G6_IMAGE_TABLES": "image_table_agent",
    "G7_LULC": "lulc_agent",
    "G8_RASTER_MAPS": "skip",
}
AGENT_GUIDE = {
    "matrix_table_agent": "English ruled tables of crops x locations (area, production) or islands x counts (machinery, farmers)",
    "bilingual_table_agent": "Hindi+English statistical tables, Hindi often in a legacy font that looks like ASCII gibberish",
    "price_table_agent": "monthly 'Comparative Statement of Prices' retail price tables",
    "island_profile_agent": "island-wise statistical outline: one prose profile per island with 'Key-Value' pairs",
    "narrative_agent": "narrative reports or budget memoranda (schemes, outlay, expenditure, descriptions)",
    "image_table_agent": "a photo/screenshot (PNG/JPG) of a table that needs OCR",
    "lulc_agent": "land use / land cover statistics or atlases",
    "skip": "large raster maps or files with no extractable statistics",
}


def fingerprint(path: str) -> dict:
    p = Path(path)
    fp = {"file": p.name, "ext": p.suffix.lower(), "size_kb": round(p.stat().st_size / 1024)}
    if fp["ext"] in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(p) as im:
            fp.update({"modality": "image", "pixels": im.size[0] * im.size[1], "width": im.size[0], "height": im.size[1]})
        return fp
    import pdfplumber
    import pymupdf
    with pymupdf.open(path) as d:
        texts = [pg.get_text() for pg in d]
        pg0 = d[0]
        cover = 0.0
        for img in pg0.get_images(full=True):
            for r in pg0.get_image_rects(img[0]):
                cover = max(cover, (r.width * r.height) / (pg0.rect.width * pg0.rect.height))
    with pdfplumber.open(path) as pdf:
        ruled = sum(len(pg.find_tables()) for pg in pdf.pages[:3])
    first = " ".join(texts[0].split())[:600] if texts else ""
    alltext = " ".join(texts).lower()
    fp.update({
        "modality": "pdf", "pages": len(texts), "chars": sum(len(t) for t in texts), "ruled_tables_first3": ruled,
        "image_cover_p1": round(cover, 2),
        **detect_languages(" ".join(texts[:3])),
        "keywords": [k for k in ("comparative statement of prices", "island-wise", "name of the scheme", "land use",
                                 "area and production", "production", "outlay", "census", "basic statistics")
                     if k in alltext][:8],
        "first_page": first,
    })
    return fp


def heuristic_route(fp: dict) -> tuple[str, bool]:
    """Fingerprint rules. Returns (agent, confident). Not confident = no decisive signal, ask the model."""
    if fp.get("modality") == "image":
        return ("skip", True) if fp.get("pixels", 0) > 20_000_000 else ("image_table_agent", True)
    kw = fp.get("keywords", [])
    per_page = fp.get("chars", 0) / max(1, fp.get("pages", 1))
    if per_page < 400 and fp.get("image_cover_p1", 0) > 0.5:
        return "skip", True                      # a picture with a few labels: raster map
    if "comparative statement of prices" in kw:
        return "price_table_agent", True
    if "island-wise" in kw:
        return "island_profile_agent", True
    if "land use" in kw:
        return "lulc_agent", True
    if fp.get("legacy_font"):
        return "bilingual_table_agent", True
    if "name of the scheme" in kw:
        return "narrative_agent", True
    if fp.get("ruled_tables_first3", 0) == 0:
        return "narrative_agent", False
    return "matrix_table_agent", False


SYSTEM = ("You are the router of an agriculture document-extraction system. Pick the single best agent for the "
          "document. Reply with JSON only: {\"agent\": <agent id>, \"reason\": <one sentence>}.")


def router_prompt(fp: dict) -> str:
    guide = "\n".join(f"- {k}: {v}" for k, v in AGENT_GUIDE.items())
    facts = {k: v for k, v in fp.items() if k != "first_page"}
    return f"Agents:\n{guide}\n\nDocument fingerprint: {facts}\nFirst page text: {fp.get('first_page', '')[:500]}"


class RouterAgent(BaseAgent):
    agent_id = "router_agent"
    uses_llm = True

    def route(self, ctx: AgentContext, force_llm: bool = False) -> tuple[str, str, str]:
        """Returns (agent_id, decided_by, reason)."""
        group = ctx.document.get("source_group")
        if group in GROUP_TO_AGENT and not force_llm:
            agent = GROUP_TO_AGENT[group]
            ctx.tracer.decision("route", "rule", {"agent": agent, "reason": f"manifest source group {group}"})
            return agent, "rule", f"manifest source group {group}"
        fp = self.tool(ctx, "fingerprint_document", fingerprint, path=str(ctx.path),
                       summarize=lambda f: {k: v for k, v in f.items() if k != "first_page"})
        h_agent, confident = heuristic_route(fp)
        if confident and not force_llm:
            # measured: fingerprint rules 0.95 vs 3B model 0.40 on the 20 corpus files, so decisive
            # signals are routed by rule and the model is asked only when the fingerprint is ambiguous
            ctx.tracer.decision("route", "rule", {"agent": h_agent, "reason": "decisive fingerprint signal"})
            return h_agent, "rule", "decisive fingerprint signal"
        if ctx.use_llm and ctx.llm.enabled:
            user = router_prompt(fp)
            r = self.tool(ctx, "llm_route", lambda: ctx.general_llm.json_call(SYSTEM, user, max_tokens=80),
                          summarize=lambda r: {"ok": r.ok, "reply": r.text[:200], "latency_s": round(r.latency_s, 1)})
            agent = r.parsed.get("agent") if r.ok and isinstance(r.parsed, dict) else None
            if agent in AGENT_GUIDE:
                reason = str(r.parsed.get("reason", ""))[:200]
                ctx.tracer.decision("route", "model", {"agent": agent, "reason": reason})
                return agent, "model", reason
            ctx.tracer.error("llm_route", f"invalid agent {agent!r}", handled_by="heuristic_route")
        ctx.tracer.decision("route", "rule", {"agent": h_agent, "reason": "fingerprint heuristic (model unavailable or invalid)"})
        return h_agent, "rule", "fingerprint heuristic"


def guess_group(agent_id: str) -> str:
    inv = {v: k for k, v in GROUP_TO_AGENT.items()}
    return inv.get(agent_id, "G0_UNKNOWN")

