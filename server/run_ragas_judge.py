"""Run RAGAS LLM-judge evaluation on sampled test cases.

Purpose:
    Evaluate the grounded tutor with real LLM answers, then run RAGAS
    LLM-judge (faithfulness, context_precision, context_recall,
    answer_relevancy) on a sampled subset for semantic-level metrics.

Output:
    docs/eval_results_ragas_judge.json

Usage:
    cd server && python run_ragas_judge.py

Note:
    Samples 50 on-material + 30 off-material cases (seed=42).
    Requires LLM_API_KEY in server/.env.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.services.tutor.store import get_tutor_store
from app.services.eval.dataset import build_comprehensive_test_set
from app.services.tutor.grounding import get_grounded_tutor
from app.services.eval import ragas_metrics as rm


async def main():
    store = get_tutor_store()
    topics = store.list_topics_by_id()
    units = store.list_units()
    print(f"Topics: {len(topics)}, Units: {len(units)}")

    print("Building comprehensive test set...")
    comprehensive_result = build_comprehensive_test_set(store)
    cases = comprehensive_result["cases"]
    print(f"Total cases: {len(cases)} (on-material: {sum(1 for c in cases if c.get('category')=='on-material')}, off-material: {sum(1 for c in cases if c.get('category')=='off-material')})")

    grounded = get_grounded_tutor()

    print("Running grounded tutor on sampled cases (with LLM)...")
    t0 = time.perf_counter()
    rows = []
    off_total = 0
    off_refused = 0
    on_cases = [c for c in cases if c.get("category") == "on-material"]
    off_cases = [c for c in cases if c.get("category") == "off-material"]

    import random
    random.seed(42)
    sampled_on = random.sample(on_cases, min(50, len(on_cases)))
    sampled_off = random.sample(off_cases, min(30, len(off_cases)))
    print(f"Sampled: {len(sampled_on)} on-material, {len(sampled_off)} off-material")

    for case in sampled_off:
        res = await grounded.answer(case["query"], llm=True)
        off_total += 1
        if res.get("status") == "refused":
            off_refused += 1

    for i, case in enumerate(sampled_on):
        res = await grounded.answer(case["query"], llm=True)
        retrieved = res.get("evidence") or []
        retrieved_ids = [
            ((r.get("meta") or {}).get("doc_id") or r.get("chunk_id", ""))
            for r in retrieved]
        contexts = [r.get("content") or r.get("text") or "" for r in retrieved]
        rows.append({
            "question": case["query"],
            "answer": res.get("answer") or "",
            "contexts": contexts,
            "retrieved_ids": retrieved_ids,
            "gold_ids": case.get("expected_doc_ids", []),
        })
        if (i + 1) % 10 == 0:
            print(f"  Processed {i+1}/{len(sampled_on)} on-material cases...")

    t1 = time.perf_counter()
    print(f"Grounded tutor completed in {t1-t0:.1f}s ({len(sampled_on)} on-material, {off_total} off-material)")

    refusal_rate = round(off_refused / off_total if off_total else 0.0, 4)
    print(f"Refusal rate: {refusal_rate} ({off_refused}/{off_total})")

    print(f"\nRunning RAGAS LLM-judge on {len(rows)} cases...")
    print("(This may take several minutes with the LLM judge)")
    t2 = time.perf_counter()
    ragas_result = rm.try_ragas_evaluate(rows)
    t3 = time.perf_counter()

    if ragas_result and ragas_result.get("ragas_used"):
        print(f"RAGAS LLM-judge completed in {t3-t2:.1f}s")
        print(f"  faithfulness: {ragas_result.get('faithfulness')}")
        print(f"  answer_relevancy: {ragas_result.get('answer_relevancy')}")
        print(f"  context_precision: {ragas_result.get('context_precision')}")
        print(f"  context_recall: {ragas_result.get('context_recall')}")

        result = {
            "ok": True,
            "ragas_used": True,
            "ragas_judge_model": os.getenv("LLM_MODEL", "glm-5.3-flash"),
            "test_dataset": comprehensive_result["summary"],
            "rag_metrics": {
                **ragas_result,
                "refusal_rate": refusal_rate,
            },
            "all_metrics": {
                "faithfulness": ragas_result["faithfulness"],
                "answer_relevancy": ragas_result["answer_relevancy"],
                "context_precision": ragas_result["context_precision"],
                "context_recall": ragas_result["context_recall"],
                "refusal_rate": refusal_rate,
            },
            "elapsed_seconds": {
                "grounded_tutor": round(t1 - t0, 1),
                "ragas_judge": round(t3 - t2, 1),
                "total": round(t3 - t0, 1),
            },
        }
    else:
        print("RAGAS LLM-judge FAILED, falling back to lexical probes")
        lexical_metrics = rm.aggregate_rag_metrics(rows)
        result = {
            "ok": True,
            "ragas_used": False,
            "test_dataset": comprehensive_result["summary"],
            "rag_metrics": {
                **lexical_metrics,
                "refusal_rate": refusal_rate,
            },
            "all_metrics": {
                "faithfulness": lexical_metrics["faithfulness"],
                "answer_relevancy": lexical_metrics["answer_relevancy"],
                "context_precision": lexical_metrics["context_precision"],
                "context_recall": lexical_metrics["context_recall"],
                "refusal_rate": refusal_rate,
            },
        }

    out = os.path.join(os.path.dirname(__file__), "..", "docs", "eval_results_ragas_judge.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    asyncio.run(main())