"""Scope control for the Query Agent: decide what a question is allowed to become.

The agent answers only from the knowledge base, so before (and after) planning it checks:
  1. chit-chat (greetings, names, thanks, "who are you")      -> help message, no query
  2. concepts the knowledge base does not hold (profit, income,
     weather, soil, ...)                                       -> "no data on X", no query
  3. questions that rank crops against each other              -> explained limitation, no query
  4. "why / should I / is it good to" questions                -> answered with the facts only, plus a caveat,
                                                                  when a crop or measure is named; refused otherwise
  5. grounding: a plan may only use a measure, crop or place that the question itself mentions
     (through the alias table or the query vocabulary). Anything the model adds on its own is dropped;
     if nothing grounded is left, the question is refused instead of being answered with unrelated numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

HELP = ("I answer questions about the Andaman & Nicobar agriculture data in this knowledge base: crop area, production "
        "and yield by zone, district or island; monthly retail prices in Port Blair; island statistics (farmers, "
        "households, livestock, farms); land use; scheme budgets, and where any of these numbers comes from. "
        "Try: \"Which agri zone produced the most paddy in 2025-26?\", \"Onion price trend in 2024\", "
        "\"Which source and page gives the 2024-25 arecanut area of South Andaman?\"")

_CHITCHAT = re.compile(
    r"^\s*(hi|hii+|hello|hey|namaste|good (morning|afternoon|evening)|thanks?|thank you|ok(ay)?|bye|"
    r"how are you|who are you|what are you|what can you do|help)\b|\bmy name is\b|\bi am [a-z]+\s*$|^\s*test\s*$",
    re.I)

# concept -> what the knowledge base does have instead
_NOT_IN_KB = {
    r"\bprofit\w*|\bincome|\bearn\w*|\bmargin|\bremunerat\w*|\bwages?\b|\bsalar\w*": "income or profit",
    r"\bweather|\brain\w*|\btemperature|\bclimate|\bmonsoon forecast|\bcyclone": "weather or rainfall",
    r"\bsoil\b|\bph\b|\bnutrient": "soil properties",
    r"\bloan interest|\bcredit score|\binsurance claim": "credit or insurance claims",
    r"\bpopulation growth|\bliteracy|\bhospital|\bschool": "non-agricultural statistics (outside this knowledge base's scope)",
    r"\bexport\w*|\bimport\w*": "trade (exports or imports)",
    r"\bfertili[sz]er price|\bseed price": "input prices",
}
_HAS_INSTEAD = {
    "income or profit": "It does have cost of cultivation, production and market prices, so you can ask e.g. "
                        "\"cost of cultivation of pulses\" or \"onion price trend in 2025\".",
    "weather or rainfall": "It has land use / land cover (2015-16) but no weather series.",
}

_RANK_ITEMS = re.compile(r"\b(which|what)\s+(crop|vegetable|fruit|item|commodity|spice|food)s?\b|"
                         r"\b(costliest|cheapest|most expensive|least expensive|most grown|main crop|top crops?)\b", re.I)
_WHY = re.compile(r"^\s*(why|how come|should\b|is it (good|wise|worth)|would it|can i|what should|recommend|advise)|"
                  r"\b(worth|advisable|good idea|best crop to grow)\b", re.I)


@dataclass
class Scope:
    kind: str            # in_scope | chitchat | not_in_kb | rank_items | why
    message: str = ""


def classify(question: str, n_items_named: int = 0) -> Scope:
    q = question.strip()
    if not q or _CHITCHAT.search(q):
        return Scope("chitchat", "Hello! " + HELP)
    for pat, concept in _NOT_IN_KB.items():
        if re.search(pat, q, re.I):
            extra = _HAS_INSTEAD.get(concept, "")
            return Scope("not_in_kb", f"This knowledge base has no data on {concept}. {extra} {HELP}".strip())
    if _RANK_ITEMS.search(q) and n_items_named == 0:
        return Scope("rank_items", "I can rank places (zones, districts, islands) or show one item over time, but I "
                                   "cannot yet rank crops or market items against each other. Ask about a specific "
                                   "item, e.g. \"tomato price trend in 2025\" or \"which zone grows the most ginger?\"")
    if _WHY.search(q):
        return Scope("why", "The knowledge base holds numbers, not causes or advice, so here are the relevant facts "
                            "only:")
    return Scope("in_scope")


RELATIVE_TIME = re.compile(r"\b(last|past|previous)\s+(\d+)\s+years?\b|\b(last|previous) year\b|\bthis year\b|"
                           r"\b(latest|recent(ly)?|current(ly)?|now|today)\b", re.I)
