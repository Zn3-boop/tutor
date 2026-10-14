"""Rebuild the evaluation test-set artifacts from the current seeded KB.

Writes:
  server/tests/test_set.json            (QA set  v2.0: real, non-tautological)
  server/tests/retrieval_selfcheck.json (retrieval self-check set)

Usage:
  cd server && python rebuild_test_sets.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONIOENCODING"] = "utf-8"

import json
from app.services.tutor.store import get_tutor_store
from app.services.eval.dataset import (
    build_comprehensive_test_set,
    build_retrieval_selfcheck_set,
)


def main() -> None:
    store = get_tutor_store()
    units = store.list_units()
    topics = store.list_topics_by_id()
    print(f"Store: {len(units)} units, {len(topics)} topics")

    qa = build_comprehensive_test_set(store)
    print(f"\nQA test set      -> {qa['path']}  ({qa['summary']['total']} cases)")
    print(json.dumps(qa["summary"].get("query_type_distribution", {}),
                     ensure_ascii=False, indent=2))

    rc = build_retrieval_selfcheck_set(store)
    print(f"\nRetrieval self-check -> {rc['path']}  ({len(rc['cases'])} cases)")

    # Guard: NO case in the QA set may be a query==answer tautology.
    taut = [c for c in qa["cases"]
            if (c.get("query") or "").strip() == (c.get("expected_answer") or "").strip()]
    if taut:
        print(f"\n[WARN] {len(taut)} tautological QA cases present:")
        for c in taut[:5]:
            print("  ", c.get("query_type"), c.get("query"))
    else:
        print("\n[OK] QA set contains zero query==answer tautologies.")


if __name__ == "__main__":
    main()