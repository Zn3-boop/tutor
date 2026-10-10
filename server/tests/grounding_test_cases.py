# -*- coding: utf-8 -*-
"""Golden truth for the grounded-tutor refusal gate. 🔴 BASELINE — DO NOT EDIT.

These are the invariant facts the regression suite is built around. The
*execution logic* in ``test_grounding.py`` may be refactored, but the
query / retrieved / expected pairs in this module are the contract and must
NOT be tuned to make the tests green. Never auto-edit this file.
"""

from __future__ import annotations

from typing import Any

CASES: dict[str, Any] = {
    # Query that must survive stopword stripping with key stems intact.
    "tokens_query": "What is the append method in Python lists",
    # Off-topic: query has no real overlap with any retrieved evidence.
    "off_topic": {
        "query": "What is the best recipe for chocolate cake?",
        "retrieved": [
            {"content": "Python variables store values in memory."},
            {"content": "The append method modifies lists in Python."},
        ],
        "relevant": False,
    },
    # On-topic: "variable"(s) and "define(d)" must match across stem forms.
    "on_topic": {
        "query": "What is a variable in Python and how do you define it?",
        "retrieved": [
            {"content": "Python variables store values in memory."},
            {"content": "The append method modifies lists in Python."},
            {"content": "Functions are defined with the def keyword."},
        ],
        "relevant": True,
    },
    # Empty query is trivially acceptable (nothing to gate on).
    "empty_query": {"retrieved": [{"content": "Some content"}], "relevant": True},
    # No evidence -> never answer.
    "empty_retrieved": {"query": "test query", "retrieved": [], "relevant": False},
}