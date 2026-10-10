"""System evaluation for the Tutor subsystem.

Two layers:
  1. RAG retrieval/generation metrics (faithfulness, answer relevance, context
     precision/recall) reusing the existing RAG evaluator over a team-built
     test set (on-material queries with known source locations + off-material
     queries that must be refused).
  2. Personalization evaluation: simulated student profiles run across multiple
     assessment sessions; we report mastery gains over sessions and the
     question repetition rate (the generator avoids repeats as history grows).
"""

from __future__ import annotations

import logging
import random
from typing import Any

from app.services.tutor.assessment import AssessmentGenerator
from app.services.tutor.learner import LearnerModel
from app.services.tutor.store import TutorStore

logger = logging.getLogger(__name__)

DEFAULT_PROFILES = [
    {"name": "fast", "accuracy": 0.85, "accuracy_by_topic": {}},
    {"name": "average", "accuracy": 0.65, "accuracy_by_topic": {}},
    {"name": "struggling", "accuracy": 0.45, "accuracy_by_topic": {}},
    {"name": "functions_weak", "accuracy": 0.65,
     "accuracy_by_topic": {"t_functions": 0.25, "t_control": 0.4}},
]


class EvaluationRunner:
    def __init__(self, store: TutorStore,
                 generator: AssessmentGenerator | None = None,
                 learner: LearnerModel | None = None):
        self.store = store
        self.generator = generator or AssessmentGenerator(store=store)
        self.learner = learner or self.generator.learner

    def _response_correct(self, profile: dict, topic_ids: list[str]) -> bool:
        acc = float(profile.get("accuracy", 0.6))
        by_topic = profile.get("accuracy_by_topic", {})
        for tid in topic_ids:
            if tid in by_topic:
                acc = min(acc, float(by_topic[tid]))
        return random.random() < acc

    async def run_simulated_students(self, *, n_sessions: int = 4,
                                     questions_per_session: int = 5,
                                     seed: int = 42,
                                     profiles: list[dict] | None = None) -> dict[str, Any]:
        random.seed(seed)
        profiles = profiles or DEFAULT_PROFILES
        topics = self.store.list_topics_by_id()
        all_topic_ids = list(topics.keys())
        results = []

        for profile in profiles:
            student = self.store.create_student(name=profile["name"],
                                                profile=profile)
            before_mastery = self._avg_mastery(student, all_topic_ids)
            session_records = []
            all_seen: set[str] = set()
            repeats = 0
            total_qs = 0

            for _ in range(n_sessions):
                quiz = await self.generator.generate_quiz(
                    student, all_topic_ids, num_questions=questions_per_session,
                    llm=False)
                if not quiz.get("ok"):
                    break
                correct = 0
                for q in quiz["questions"]:
                    total_qs += 1
                    qid = q["question_id"]
                    if qid in all_seen:
                        repeats += 1
                    all_seen.add(qid)
                    is_right = self._response_correct(profile, q["topic_ids"])
                    if is_right:
                        correct += 1
                    await self.generator.submit_answer(
                        student, quiz["assessment_id"], qid,
                        q["options"][0] if q.get("options") else "ans")
                session_records.append({
                    "session": len(session_records) + 1,
                    "questions": len(quiz["questions"]),
                    "correct": correct,
                    "accuracy": round(correct / max(len(quiz["questions"]), 1), 3),
                    "avg_mastery": round(self._avg_mastery(student, all_topic_ids), 3),
                })

            after_mastery = self._avg_mastery(student, all_topic_ids)
            repetition_rate = round(repeats / max(total_qs, 1), 3)
            results.append({
                "student": profile["name"],
                "mastery_before": round(before_mastery, 3),
                "mastery_after": round(after_mastery, 3),
                "mastery_gain": round(after_mastery - before_mastery, 3),
                "question_repetition_rate": repetition_rate,
                "sessions": session_records,
            })
        return {"ok": True, "profiles": results,
                "config": {"n_sessions": n_sessions,
                           "questions_per_session": questions_per_session}}

    # ---------------- Day6 full system evaluation ----------------
    def _answer_choice_for(self, profile: dict, q: dict, qid: str) -> str:
        """Pick the option a simulated student submits for question ``q``.

        Chooses the *correct* option when the profile gets it right (using the
        stored answer key) and a wrong option otherwise, so BKT mastery gain
        actually reflects the profile's accuracy instead of the first option.
        """
        full = None
        if qid:
            full = self.store.get_question(qid)
        options = (full or {}).get("options") or (q.get("options") or [])
        answer = (full or {}).get("answer") or None
        is_right = self._response_correct(profile, q.get("topic_ids") or [])
        if is_right and answer and answer in options:
            return answer
        wrong = [o for o in options if o != answer] if answer else (options or ["ans"])
        return wrong[0] if wrong else "ans"

    async def run_full_evaluation(self, *, n_sessions: int = 4,
                                  questions_per_session: int = 5,
                                  seed: int = 42,
                                  profiles: list[dict] | None = None,
                                  llm: bool = False) -> dict[str, Any]:
        """One-shot system benchmark reporting all Day6 headline metrics.

        - mastery_gain / question_repetition_rate come from the adaptive
          assessment simulation (multiple sessions, simulated students with
          per-topic accuracy).
        - faithfulness / context_precision / context_recall / refusal_rate come
          from a RAG chat sub-simulation over a KB-derived test set (on-material
          queries with known gold units + off-material queries that must refuse).
        RAG metrics use RAGAS when installed, else deterministic lexical probes.
        """
        from app.services.eval.dataset import build_test_cases, summarize_dataset
        random.seed(seed)
        profiles = profiles or DEFAULT_PROFILES
        topics = self.store.list_topics_by_id()
        all_topic_ids = list(topics.keys())

        # (1) adaptive assessment sessions -> mastery gain + repetition rate
        assessment_results = []
        for profile in profiles:
            student = self.store.create_student(name='sim_' + profile["name"],
                                                profile=profile)
            before = self._avg_mastery(student, all_topic_ids)
            seen = set()
            repeats = 0
            asked_total = 0
            difficulty_seen = {"easy": 0, "medium": 0, "hard": 0}
            for _ in range(n_sessions):
                quiz = await self.generator.generate_quiz(
                    student, all_topic_ids,
                    num_questions=questions_per_session, llm=False)
                if not quiz.get("ok"):
                    break
                for q in quiz["questions"]:
                    asked_total += 1
                    qid = q.get("question_id", "")
                    if qid in seen:
                        repeats += 1
                    seen.add(qid)
                    diff = q.get("difficulty") or "medium"
                    difficulty_seen[diff] = difficulty_seen.get(diff, 0) + 1
                    chosen = self._answer_choice_for(profile, q, qid)
                    await self.generator.submit_answer(
                        student, quiz["assessment_id"], qid, chosen)
            after = self._avg_mastery(student, all_topic_ids)
            assessment_results.append({
                "profile": profile["name"],
                "mastery_before": round(before, 3),
                "mastery_after": round(after, 3),
                "mastery_gain": round(after - before, 3),
                "question_repetition_rate": round(repeats / max(asked_total, 1), 3),
                "asked_questions": asked_total,
                "difficulty_distribution": difficulty_seen,
            })

        # (2) RAG chat sub-simulation -> faithfulness / context precision+recall
        from app.services.tutor.grounding import get_grounded_tutor
        from app.services.eval import ragas_metrics as rm
        grounded = get_grounded_tutor()
        cases = build_test_cases(self.store)
        rows = []
        off_total = 0
        off_refused = 0
        for case in cases:
            res = await grounded.answer(case["query"], llm=llm)
            if case.get("category") == "off-material":
                off_total += 1
                if res.get("status") == "refused":
                    off_refused += 1
                continue
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

        rag_metrics = rm.aggregate_rag_metrics(rows)
        ragas_block = rm.try_ragas_evaluate(rows)
        if ragas_block is not None:
            rag_metrics = ragas_block
        rag_metrics["refusal_rate"] = round(
            off_refused / off_total if off_total else 0.0, 4)

        gains = [p["mastery_gain"] for p in assessment_results]
        reps = [p["question_repetition_rate"] for p in assessment_results]
        assessment_metrics = {
            "mastery_gain_avg": round(sum(gains) / len(gains), 4) if gains else 0.0,
            "question_repetition_rate_avg": round(sum(reps) / len(reps), 4) if reps else 0.0,
        }

        return {
            "ok": True,
            "ragas_used": rag_metrics.get("ragas_used", False),
            "test_dataset": summarize_dataset(cases),
            "rag_metrics": rag_metrics,
            "assessment_metrics": assessment_metrics,
            "all_metrics": {
                "faithfulness": rag_metrics["faithfulness"],
                "context_precision": rag_metrics["context_precision"],
                "context_recall": rag_metrics["context_recall"],
                "refusal_rate": rag_metrics["refusal_rate"],
                "mastery_gain": assessment_metrics["mastery_gain_avg"],
                "question_repetition_rate": assessment_metrics["question_repetition_rate_avg"],
            },
            "student_profiles": assessment_results,
            "config": {"n_sessions": n_sessions,
                       "questions_per_session": questions_per_session,
                       "seed": seed},
        }

    def _avg_mastery(self, student: dict, topic_ids: list[str]) -> float:
        vals = [self.learner.mastery_level(student, tid) for tid in topic_ids]
        return sum(vals) / len(vals) if vals else 0.0

    # ---------------- RAG metrics reuse ----------------
    async def evaluate_rag_metrics(self, cases: list[Any] | None = None) -> dict[str, Any]:
        from app.services.eval.rag_evaluator import RAGEvaluator
        from app.services.rag.service import get_rag_service
        if cases is None:
            cases = self._default_eval_cases()
        evaluator = RAGEvaluator()
        rag = get_rag_service()
        retrieval = await evaluator.evaluate_retrieval(cases, rag, top_k=5)
        generation = await evaluator.evaluate_generation(cases, rag)
        return {"retrieval": retrieval, "generation": generation,
                "case_count": len(cases)}

    def _default_eval_cases(self) -> list[Any]:
        from app.services.eval.rag_evaluator import RAGEvalCase
        cases = [
            RAGEvalCase(query="What is a variable in Python?",
                        expected_doc_ids=self._unit_ids_for("t_variable"),
                        expected_answer="named memory location",
                        category="on-material", difficulty="easy"),
            RAGEvalCase(query="How does the def keyword define a function?",
                        expected_doc_ids=self._unit_ids_for("t_functions"),
                        expected_answer="def keyword",
                        category="on-material", difficulty="easy"),
            RAGEvalCase(query="Explain the return statement.",
                        expected_doc_ids=self._unit_ids_for("t_functions"),
                        expected_answer="return",
                        category="on-material", difficulty="medium"),
            RAGEvalCase(query="What is the population of Mars?",
                        expected_doc_ids=[],
                        expected_answer="",
                        category="off-material", difficulty="easy"),
            RAGEvalCase(query="Who wrote the Iliad?",
                        expected_doc_ids=[],
                        expected_answer="",
                        category="off-material", difficulty="easy"),
        ]
        return cases

    def _unit_ids_for(self, topic_id: str) -> list[str]:
        # RAG evaluator compares against the retrieved chunk_id, so return the
        # unit's indexed chunk_id (the RAG doc/chunk identity) as ground truth.
        ids: list[str] = []
        for u in self.store.list_units():
            if topic_id in u.get("topic_ids", []):
                cid = u.get("chunk_id") or u["unit_id"]
                ids.append(cid)
        return ids


_runner: EvaluationRunner | None = None


def get_evaluation_runner(store: TutorStore | None = None) -> EvaluationRunner:
    global _runner
    if store is None:
        from app.services.tutor.store import get_tutor_store
        store = get_tutor_store()
    if _runner is None or _runner.store is not store:
        _runner = EvaluationRunner(store=store)
    return _runner
