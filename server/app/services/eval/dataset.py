"""Knowledge-base-driven evaluation test set (Day6).

Builds on-material cases from real unit sentences (gold = the unit's own
indexed chunk id, so retrieval precision/recall are measurable) and injects
off-material distractor queries that the grounded tutor must refuse.
"""

from __future__ import annotations

import re
from typing import Any

# Off-material queries that must NOT be answered (refusal-rate ground truth).
_OFF_MATERIAL_QUERIES = [
    ("What is the capital of France?", "general"),
    ("How do you cook pasta from scratch?", "general"),
    ("Who wrote the Iliad?", "general"),
    ("Explain how to fix a bicycle chain.", "general"),
]


def _first_sentence(unit: dict) -> str | None:
    text = (unit.get("text") or "").strip()
    # drop markdown heading lines
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))
    sentences = re.split(r"(?<=[.!?。！？；;])\s+", text)
    for s in sentences:
        s = s.strip()
        if 15 <= len(s) <= 260:
            return s
    return None


def build_test_cases(store) -> list[dict]:
    """Build [on-material, off-material] cases from the current KB state."""
    topics = store.list_topics_by_id()
    cases: list[dict] = []
    seen_gold: set[str] = set()
    for u in store.list_units():
        sent = _first_sentence(u)
        if not sent:
            continue
        cid = u.get("chunk_id") or u.get("unit_id")
        if cid in seen_gold:  # avoid duplicating gold units across cases
            continue
        seen_gold.add(cid)
        tid = (u.get("topic_ids") or [None])[0]
        cases.append({
            "query": sent,
            "expected_answer": sent,
            "expected_doc_ids": [cid],
            "category": "on-material",
            "difficulty": "medium",
            "topic_ids": u.get("topic_ids", []) or [],
            "source_ids": u.get("source_ids", []) or [u.get("source_id", "")],
        })
    for q, cat in _OFF_MATERIAL_QUERIES:
        cases.append({
            "query": q, "expected_answer": "", "expected_doc_ids": [],
            "category": "off-material", "difficulty": "easy",
            "topic_ids": [], "source_ids": [],
        })
    return cases


def summarize_dataset(cases: list[dict]) -> dict[str, Any]:
    n_on = sum(1 for c in cases if c.get("category") == "on-material")
    n_off = sum(1 for c in cases if c.get("category") == "off-material")
    topics: set[str] = set()
    for c in cases:
        topics.update(c.get("topic_ids", []) or [])
    return {
        "total": len(cases),
        "on_material": n_on,
        "off_material": n_off,
        "topic_coverage": sorted(topics),
    }