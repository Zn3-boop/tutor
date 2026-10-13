"""Inline query rewrite (R7: 改写兜底 — 原查询永不替换).

A lightweight, offline-first rewriter that turns a raw learner question into a
canonical *standalone* form plus a few retrieval query variants, so the hybrid
retriever gets better recall. The original query is never dropped; variants are
only added in parallel.

The core is pure rule-based (no network/model), which is what the tests exercise.
An optional LLM expansion path exists for richer rewrites when a provider is on.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Conversational fillers we can safely strip when building the standalone query.
_FILLERS = [
    r"请(?:你)?(?:帮我)?(?:告诉我|告诉|解释|介绍|说明|回答|讲解)(?:一下?)?",
    r"帮我(?:解释|说明|讲)(?:一下?)?",
    r"what( is| are| does| do| about)? ",
    r"please ",
    r"can you (?:tell|explain|describe) ",
    r"explain (?:the|this|about) ",
    r"tell me (?:about|what|how) ",
    r"为什么(?:要|会)",
    r"请问",
    r"how to ",
    r"how do (?:you|i) ",
    r"what does \w+ mean",
    r"define ",
]


def _normalize(query: str) -> str:
    q = re.sub(r"\s+", " ", (query or "")).strip()
    q = re.sub(r"^[?？：:，,。. ]+|[?？：:，,。. ]+$", "", q)
    return q.strip()


def _strip_fillers(query: str) -> str:
    lowered = query
    for pat in _FILLERS:
        lowered = re.sub(pat, "", lowered, flags=re.IGNORECASE)
    return _normalize(lowered) or _normalize(query)


def _tokens(text: str) -> set[str]:
    """Extract meaningful tokens: English words and Chinese characters."""
    return set(re.findall(r"[a-z][a-z0-9_]{1,}|\u4e00-\u9fff", text.lower()))


def _detect_language(query: str) -> str:
    """Detect the primary language of the query.

    Returns 'zh' if Chinese characters are present, 'en' otherwise.
    Mixed queries are treated as Chinese-preferring since the UI is Chinese.
    """
    if re.search(r"[\u4e00-\u9fff]", query):
        return "zh"
    return "en"


def inline_rewrite(query: str, topics: dict[str, dict] | None = None) -> dict[str, Any]:
    """Build the canonical query + retrieval variants for the given question.

    Args:
        query: raw learner question.
        topics: optional topic graph {topic_id: {name, concepts}} used to expand
                a short query with the matching topic names as retrieval variants.

    Returns:
        dict with:
            standalone_query : cleaned, de-filler canonical form
            queries          : [standalone, *variants] to feed the retriever
            method           : "rule"
            matched_topics   : topic_ids whose name/concept matched the query
    """
    standalone = _strip_fillers(query)
    queries = [standalone]
    matched: list[str] = []

    if topics:
        lower_standalone = standalone.lower()
        for tid, topic in topics.items():
            name = (topic.get("name") or "").lower()
            concepts = [c.lower() for c in (topic.get("concepts") or [])]
            if name and name in lower_standalone:
                matched.append(tid)
            elif any(c and c in lower_standalone for c in concepts):
                matched.append(tid)

        # Short query + clear topic hit -> emit a "topic-scoped" variant.
        if matched and len(_tokens(standalone)) <= 3:
            for tid in matched:
                name = (topics.get(tid, {}) or {}).get("name")
                if name:
                    variant = f"{standalone.rstrip('。？?')} {name}".strip()
                    if variant not in queries:
                        queries.append(variant)
                break  # one scoped variant is enough

    # Dedupe preserving order.
    seen: set[str] = set()
    queries = [q for q in queries if not (q.lower() in seen or seen.add(q.lower()))]

    # Language detection for downstream response generation
    detected_language = _detect_language(query)

    return {
        "standalone_query": standalone,
        "queries": queries,
        "method": "rule",
        "matched_topics": matched,
        "detected_language": detected_language,
        "is_mixed_language": detected_language == "zh" and re.search(r"[a-zA-Z]{3,}", query) is not None,
    }