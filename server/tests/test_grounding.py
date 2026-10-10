# -*- coding: utf-8 -*-
"""Unit tests for grounded tutor refusal logic.

🔴 BASELINE PROTECTION (P0): the invariant truth for the pure relevance-gate
cases below lives in ``grounding_test_cases.py`` and must NOT be edited here.
Refactor execution logic only; never tune queries/retrieved/expected to flip a
test. The integration case (``test_grounding_no_hallucinated_citations``) keeps
its inline facts because it exercises the real seeded knowledge base.
"""

import asyncio
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from app.services.tutor.grounding import _relevance_ok, _query_tokens

from grounding_test_cases import CASES


def test_query_tokens_no_stopwords():
    tokens = _query_tokens(CASES["tokens_query"])
    assert "the" not in tokens
    assert "is" not in tokens
    assert "in" not in tokens
    assert any(t.startswith("append") for t in tokens)
    assert any(t.startswith("python") for t in tokens)


def test_relevance_off_topic():
    case = CASES["off_topic"]
    relevant = _relevance_ok(case["query"], case["retrieved"])
    assert not relevant


def test_relevance_on_topic():
    case = CASES["on_topic"]
    relevant = _relevance_ok(case["query"], case["retrieved"])
    assert relevant


def test_relevance_empty_query():
    case = CASES["empty_query"]
    assert _relevance_ok("", case["retrieved"])


def test_relevance_empty_retrieved():
    case = CASES["empty_retrieved"]
    assert not _relevance_ok(case["query"], case["retrieved"])


def test_grounding_no_hallucinated_citations():
    """Integration: with the seeded real KB, answering 'variable' must either
    produce only citations whose chunks/labels exist, or refuse cleanly.
    Needs a seeded DB (see README).
    """
    from app.services.tutor.store import get_tutor_store
    from app.services.tutor.grounding import get_grounded_tutor
    store = get_tutor_store()
    tutor = get_grounded_tutor(store=store)

    async def _run():
        return await tutor.answer(
            question="What is a variable in Python?",
            llm=False, top_k=3,
        )

    result = asyncio.run(_run())
    assert result["status"] in ("answered", "refused"), f"Unexpected status: {result.get('status')}"
    if result["status"] == "answered":
        for c in result.get("citations", []):
            assert "chunk_id" in c and c["chunk_id"]
            assert c.get("label", "")
