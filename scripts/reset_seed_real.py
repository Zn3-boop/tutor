"""Reset -> REAL-course seed -> warmup (one-shot for Phase 1).

Deletes the dirty ``tutor_db.json`` and the RAG store, re-ingests the REAL
bundled course materials listed in ``server/demo_materials/
materials-manifest.json`` (Think Python 2e + MIT OCW 6.0001 + timestamped SRT),
rebuilds the FAISS index once, then warms up the demo student profile so the
dashboards have data.

Usage:
    python scripts/reset_seed_real.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from itertools import cycle

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(SERVER_DIR, ".env"))

os.environ["VLM_ENABLED"] = "false"          # no captioning during seed
os.environ["RAG_DEFER_FAISS_BUILD"] = "true"  # avoid O(n^2) index rebuilds
os.environ["RAG_AUTO_BUILD_FAISS"] = "false"  # final index built once below


def _reset() -> None:
    from app.services.tutor.store import DEFAULT_DATA_DIR
    db = os.path.join(DEFAULT_DATA_DIR, "tutor_db.json")
    if os.path.exists(db):
        os.remove(db)
        print(f"[reset] removed {db}")
    rag_dir = os.path.join(os.path.expanduser("~"), ".ecv_rag_store")
    if os.path.isdir(rag_dir):
        shutil.rmtree(rag_dir, ignore_errors=True)
        print(f"[reset] removed {rag_dir}")
    for parent in (DEFAULT_DATA_DIR, rag_dir):
        os.makedirs(parent, exist_ok=True)


async def _seed_real() -> None:
    from app.services.tutor.store import get_tutor_store
    from app.services.tutor.knowledge import get_kb_ingestor
    store = get_tutor_store()
    ing = get_kb_ingestor(store)
    res = await ing.seed_real_course()
    if not res.get("ok"):
        for r in res.get("results", []):
            if not r.get("ok"):
                print(f"[seed] FAILED {r.get('filename')}: {r.get('error')}")
        raise SystemExit(1)
    for r in res.get("results", []):
        print(f"[seed]   [ok] {r.get('filename')}: {r.get('unit_count', '-')} units")
    print(f"[seed] done: sources={len(store.list_sources())} units={len(store.list_units())}")


def _build_faiss() -> None:
    try:
        from app.services.rag.store import DEFAULT_STORE_DIR, DualIndexStore
        st = DualIndexStore(DEFAULT_STORE_DIR)
        st._build_faiss_index()
        total = st._faiss_index.ntotal if st._faiss_index else 0
        print(f"[rag] FAISS index built: {total} vectors")
    except Exception as exc:  # non-fatal; retrieval degrades to BM25
        print(f"[rag] FAISS build skipped (non-fatal): {exc}")


async def _warmup() -> None:
    from app.services.tutor.assessment import get_assessment_generator
    from app.services.tutor.store import get_tutor_store
    store = get_tutor_store()
    gen = get_assessment_generator(store)
    demo_name = "Demo \u5b66\u751f"  # matches DEMO_STUDENT_NAME in the API
    student = next((s for s in store.list_students() if s.get("name") == demo_name), None)
    if student is None:
        student = store.create_student(name=demo_name,
                                       profile={"level": "beginner", "mode": "demo"})
    topics = store.list_topics_by_id()
    topic_with_units: set[str] = set()
    for u in store.list_units():
        topic_with_units |= set(u.get("topic_ids", []) or [])
    scope = [tid for tid in topics if tid in topic_with_units]

    asked = set(student.get("asked_questions", []))
    correctness = cycle([True, True, False, True, True, False, True, True, False, True])
    answered = wrong = 0
    for _ in range(3):
        quiz = await gen.generate_quiz(student, scope, num_questions=5, llm=False)
        if not quiz.get("ok"):
            continue
        for pq in quiz.get("questions", []):
            qid = pq.get("question_id")
            if not qid or qid in asked:
                continue
            q = store.get_question(qid)
            if not q:
                continue
            opts = q.get("options") or []
            answer = q.get("answer", "")
            should = next(correctness)
            if should and answer in opts:
                chosen = answer
            elif opts:
                chosen = next((o for o in opts if o != answer), answer)
            else:
                chosen = answer if should else (answer or "wrong")
            res = await gen.submit_answer(student, quiz["assessment_id"], qid, chosen)
            asked.add(qid)
            answered += 1
            wrong += 0 if res.get("correct") else 1
    print(f"[warmup] student={student['student_id']} answers={answered} "
          f"wrong={wrong} trajectory={len(student.get('mastery_traj', []))}")


def main() -> None:
    _reset()
    asyncio.run(_seed_real())
    _build_faiss()
    asyncio.run(_warmup())
    print("[done] demo DB rebuilt with REAL sources; run pytest to verify citations.")


if __name__ == "__main__":
    main()