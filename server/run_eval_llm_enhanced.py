"""Run enhanced evaluation with expanded off-material test set (llm=True).

Purpose:
    Run the full evaluation pipeline with the expanded 98 off-material
    test cases and LLM-powered grounded tutor answers. Produces
    faithfulness, refusal rate, and mastery gain metrics.

Output:
    docs/eval_results_ragas_enhanced.json

Usage:
    cd server && python run_eval_llm_enhanced.py

Note:
    Requires LLM_API_KEY in server/.env.
    Uses n_sessions=4, questions_per_session=5, seed=42.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.services.tutor.store import get_tutor_store
from app.services.tutor.evaluation import EvaluationRunner


async def main():
    store = get_tutor_store()
    topics = store.list_topics_by_id()
    units = store.list_units()
    print(f"Topics: {len(topics)}, Units: {len(units)}")

    if len(units) < 10:
        print("Need to seed demo course first...")
        from app.services.tutor.knowledge import get_kb_ingestor
        ing = get_kb_ingestor()
        result = await ing.seed_demo(variant="real")
        print(f"Seed result: {result}")
        store = get_tutor_store()
        topics = store.list_topics_by_id()
        units = store.list_units()
        print(f"After seed - Topics: {len(topics)}, Units: {len(units)}")

    runner = EvaluationRunner(store)

    print("Running evaluation with RAGAS LLM judge (glm-5.3-flash)...")
    t0 = time.perf_counter()
    result = await runner.run_full_evaluation(
        n_sessions=4,
        questions_per_session=5,
        seed=42,
        llm=True,
    )
    t1 = time.perf_counter()
    print(f"\nEvaluation complete (elapsed={t1-t0:.1f}s):")
    print(f"  ragas_used: {result.get('ragas_used')}")
    metrics = result.get("all_metrics", {})
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    profiles = result.get("student_profiles", [])
    print(f"  student profiles: {len(profiles)}")
    for p in profiles:
        print(
            f"    - {p.get('profile')}: mastery_before={p.get('mastery_before')}, "
            f"mastery_after={p.get('mastery_after')}, gain={p.get('mastery_gain')}"
        )

    out = os.path.join(os.path.dirname(__file__), "..", "docs", "eval_results_ragas_enhanced.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    asyncio.run(main())