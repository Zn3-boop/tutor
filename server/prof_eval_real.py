"""Time run_full_evaluation phases on the real seeded store (llm=False)."""
import asyncio
import os
import time

os.environ.setdefault("RAG_AUTO_BUILD_FAISS", "false")
os.environ.setdefault("RAG_DEFER_FAISS_BUILD", "true")
os.environ.setdefault("RAG_EMBEDDING_MODEL_PATH", "__missing__")

import app.services.tutor.evaluation as ev


async def main():
    from app.services.tutor.store import get_tutor_store
    from app.services.tutor.assessment import AssessmentGenerator

    store = get_tutor_store()
    gen = AssessmentGenerator(store)
    runner = ev.EvaluationRunner(store, generator=gen)

    t0 = time.perf_counter()
    # Patch the module-level ragas fn so we never hit external LLM judge.
    import app.services.eval.ragas_metrics as rm
    original = rm.try_ragas_evaluate
    rm.try_ragas_evaluate = lambda rows: None
    try:
        r = await runner.run_full_evaluation(
            n_sessions=1, questions_per_session=2, seed=42, llm=False)
    finally:
        rm.try_ragas_evaluate = original
    t1 = time.perf_counter()
    print(f"TOTAL elapsed={t1-t0:.1f}s")
    print(f"ok={r['ok']} ragas_used={r['ragas_used']} cases={r['test_dataset']['total']}")
    print(f"all_metrics={r['all_metrics']}")


asyncio.run(main())