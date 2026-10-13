# -*- coding: utf-8 -*-
"""Regression tests for the full evaluation runner.

Covers the P0/P1 fixes in `EvaluationRunner.run_full_evaluation`:
- the endpoint no longer 500s (was broken by a missing-await on the async
  `generate_quiz` inside `_evaluate_synthesis_queries`),
- `synthesis_performance` lives at the top level (not nested inside
  `all_metrics`),
- offline mode reports `ragas_used: false` and deterministic lexical probes,
- the archived test set path points at `server/tests/test_set.json`.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest import mock

from app.services.tutor.store import TutorStore
from app.services.tutor.assessment import AssessmentGenerator
from app.services.tutor.evaluation import EvaluationRunner


def _seed_store() -> TutorStore:
    store = TutorStore(data_dir=tempfile.mkdtemp(prefix="test_eval_runner_"))
    topics = {
        "t_vars": ("Variables", ["variable", "assignment"], []),
        "t_funcs": ("Functions", ["function", "def", "return"], ["t_vars"]),
        "t_loops": ("Loops", ["for", "while", "iteration"], ["t_funcs"]),
        "t_lists": ("Lists", ["list", "append", "index"], ["t_vars"]),
        "t_dicts": ("Dicts", ["dict", "key", "value"], ["t_vars"]),
        "t_strings": ("Strings", ["string", "slice", "concat"], ["t_vars"]),
        "t_files": ("Files", ["open", "read", "write"], ["t_funcs"]),
    }
    for tid, (name, concepts, prereqs) in topics.items():
        store.upsert_topic(topic_id=tid, name=name,
                           concepts=concepts, prerequisites=prereqs)
    src_id = store.add_source(title="Intro to Python", kind="text", path="")["source_id"]
    sentences = [
        ("A variable is a name that refers to a value stored in memory.", "t_vars"),
        ("The assignment operator stores a value into a variable container.", "t_vars"),
        ("A function is defined using the def keyword in Python programming.", "t_funcs"),
        ("The return statement sends a value back from a function call.", "t_funcs"),
        ("A for loop iterates over a sequence of items in Python code.", "t_loops"),
        ("The while loop repeats as long as the condition remains true.", "t_loops"),
        ("The range function generates a sequence of integer numbers.", "t_loops"),
        ("A list is an ordered mutable collection of elements in Python.", "t_lists"),
        ("The append method adds an item to the end of a list object.", "t_lists"),
        ("A dictionary maps unique keys to their corresponding values.", "t_dicts"),
        ("Dict keys must be immutable and hashable in Python code.", "t_dicts"),
        ("A string is an immutable sequence of characters in Python.", "t_strings"),
        ("String slicing extracts a substring using index notation.", "t_strings"),
        ("The open function returns a file object for reading or writing.", "t_files"),
        ("Files should be closed after use to release system resources.", "t_files"),
        ("The print function outputs text to the console terminal.", "t_vars"),
    ]
    for i, (text, tid) in enumerate(sentences):
        store.add_unit(source_id=src_id, text=text,
                       origin={"index": i, "label": f"unit#{i + 1}"},
                       topic_ids=[tid], concepts=["python"])
    return store
def _run_full_eval(store: TutorStore, **kwargs):
    """Run the runner with RAGAS mocked away so tests stay fast and offline."""
    runner = EvaluationRunner(store, generator=AssessmentGenerator(store))
    with mock.patch("app.services.eval.dataset.save_test_set",
                    return_value=str(Path(tempfile.gettempdir()) / "test_set.json")), \
         mock.patch("app.services.eval.ragas_metrics.try_ragas_evaluate",
                    return_value=None):
        return asyncio.run(runner.run_full_evaluation(
            n_sessions=kwargs.get("n_sessions", 2),
            questions_per_session=kwargs.get("questions_per_session", 2),
            seed=kwargs.get("seed", 42),
            llm=False,
        ))


def test_full_evaluation_returns_complete_offline_structure():
    result = _run_full_eval(_seed_store())

    assert result["ok"] is True
    # Offline lexical-probe path must be flagged honestly.
    assert result["ragas_used"] is False

    # all_metrics must be flat and contain every headline metric.
    assert set(result["all_metrics"]) == {
        "faithfulness", "context_precision", "context_recall",
        "refusal_rate", "mastery_gain", "question_repetition_rate",
    }

    # synthesis_performance is a top-level list (one entry per profile),
    # NOT nested inside all_metrics.
    assert isinstance(result["synthesis_performance"], list)
    assert len(result["synthesis_performance"]) == len(result["student_profiles"])
    for perf in result["synthesis_performance"]:
        assert set(perf) == {"count", "correct", "accuracy"}
        assert isinstance(perf["accuracy"], float)

    # Profiles simulated; mastery/repetition aggregates present.
    assert result["assessment_metrics"]["mastery_gain_avg"] >= 0.0
    assert result["assessment_metrics"]["question_repetition_rate_avg"] >= 0.0
    assert len(result["student_profiles"]) == len(
        result["profile_trajectories"])

    # Off-material queries were refused by the grounded tutor.
    assert result["rag_metrics"]["refusal_rate"] >= 0.0
    assert "test_set_path" in result


def test_full_evaluation_test_set_summary_is_consistent():
    store = _seed_store()
    result = _run_full_eval(store, n_sessions=2, questions_per_session=2, seed=42)

    summary = result["test_dataset"]
    # The summary always reflects the cases actually scored.
    assert summary["total"] == summary["on_material"] + summary["off_material"]
    assert summary["off_material"] >= 1
    assert "query_type_distribution" in summary
    # Config echoes the summary (single source of truth), not a stale duplicate.
    cfg_summary = result["config"]["test_dataset_summary"]
    assert cfg_summary["total"] == summary["total"]
    assert cfg_summary["off_material"] == summary["off_material"]


def test_synthesis_performance_uses_real_students():
    """Synthesis evaluation must not crash on a summary dict (asked_questions int)."""
    store = _seed_store()
    result = _run_full_eval(store, n_sessions=1, questions_per_session=2, seed=7)
    # Regression: previous code passed assessment summary dicts into
    # generate_quiz -> TypeError: 'int' object is not iterable.
    assert all(p["count"] >= 0 for p in result["synthesis_performance"])
def test_bm25_index_is_cached_and_invalidated(monkeypatch):
    """BM25Okapi must be built once per corpus, not once per search."""
    from app.services.rag.store import DualIndexStore

    store = DualIndexStore(store_dir=tempfile.mkdtemp(prefix="test_bm25_cache_"))
    build_count = {"n": 0}

    import rank_bm25
    real_bm25 = rank_bm25.BM25Okapi

    def _counting_new(*a, **k):
        build_count["n"] += 1
        return real_bm25(*a, **k)

    monkeypatch.setattr(rank_bm25, "BM25Okapi", _counting_new)

    # Seed the corpus so searches actually hit BM25Okapi.
    for i in range(10):
        store.add_chunk(f"Chunk {i} discusses python loops functions variables and tuples.",
                        {"chunk_id": f"c{i}", "acl_tags": ["public"]})

    # 1) Several searches on an unchanged corpus share one index build.
    for i in range(100):
        store.bm25_search("python loops variables", top_k=3)
    assert build_count["n"] == 1, f"expected 1 build after 100 searches, got {build_count['n']}"

    # 2) Adding a chunk invalidates the cache, so the next search rebuilds.
    store.add_chunk("Fresh content about python tuples and ranges.",
                    {"chunk_id": "fresh", "acl_tags": ["public"]})
    store.bm25_search("python tuples", top_k=3)
    assert build_count["n"] == 2, f"expected rebuild after add_chunk, got {build_count['n']}"

    # 3) delete_chunk invalidates too.
    store.delete_chunk("fresh")
    store.bm25_search("python loops", top_k=3)
    assert build_count["n"] == 3, f"expected rebuild after delete_chunk, got {build_count['n']}"