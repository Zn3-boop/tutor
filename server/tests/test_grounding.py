# -*- coding: utf-8 -*-
"""Unit tests for grounded tutor refusal logic."""

import asyncio
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from app.services.tutor.grounding import _relevance_ok, _query_tokens


def test_query_tokens_no_stopwords():
    tokens = _query_tokens("What is the append method in Python lists")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "in" not in tokens
    assert any(t.startswith("append") for t in tokens)
    assert any(t.startswith("python") for t in tokens)


def test_relevance_off_topic():
    retrieved = [
        {"content": "Python variables store values in memory."},
        {"content": "The append method modifies lists in Python."},
    ]
    relevant = _relevance_ok("What is the best recipe for chocolate cake?", retrieved)
    assert not relevant


def test_relevance_on_topic():
    retrieved = [
        {"content": "Python variables store values in memory."},
        {"content": "The append method modifies lists in Python."},
        {"content": "Functions are defined with the def keyword."},
    ]
    relevant = _relevance_ok(
        "What is a variable in Python and how do you define it?", retrieved
    )
    assert relevant


def test_relevance_empty_query():
    assert _relevance_ok("", [{"content": "Some content"}])


def test_relevance_empty_retrieved():
    assert not _relevance_ok("test query", [])


def test_grounding_no_hallucinated_citations():
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
