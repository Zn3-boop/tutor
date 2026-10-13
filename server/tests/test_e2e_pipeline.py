# -*- coding: utf-8 -*-
"""E2E integration test: diagnostic → quiz → submit → report → plan.

Validates the complete learner pipeline end-to-end without LLM (offline mode).
"""

import asyncio
import tempfile

from app.services.tutor.store import TutorStore
from app.services.tutor.assessment import AssessmentGenerator
from app.services.tutor.planning import LearningPlanner
from app.services.tutor.learner import LearnerModel


def _seed_store() -> TutorStore:
    store = TutorStore(data_dir=tempfile.mkdtemp(prefix="test_e2e_"))
    store.upsert_topic(topic_id="t_vars", name="Variables",
                       concepts=["variable", "assignment"], prerequisites=[])
    store.upsert_topic(topic_id="t_funcs", name="Functions",
                       concepts=["function", "def", "return"], prerequisites=["t_vars"])
    store.upsert_topic(topic_id="t_loops", name="Loops",
                       concepts=["for", "while", "iteration"], prerequisites=["t_funcs"])
    src_id = store.add_source(title="Intro to Python", kind="text", path="")["source_id"]
    units = [
        ("A variable is a name that refers to a value stored in memory.", "t_vars"),
        ("The assignment operator stores a value into a variable container.", "t_vars"),
        ("A function is defined using the def keyword in Python programming.", "t_funcs"),
        ("The return statement sends a value back from a function call.", "t_funcs"),
        ("A for loop iterates over a sequence of items in Python code.", "t_loops"),
        ("The while loop repeats as long as the condition remains true.", "t_loops"),
        ("The range function generates a sequence of integer numbers.", "t_loops"),
        ("The print function outputs text to the console terminal.", "t_vars"),
    ]
    for i, (text, tid) in enumerate(units):
        store.add_unit(source_id=src_id, text=text,
                       origin={"index": i, "label": f"unit#{i+1}"},
                       topic_ids=[tid], concepts=["python"])
    return store


def test_full_learner_pipeline():
    store = _seed_store()
    gen = AssessmentGenerator(store)
    planner = LearningPlanner(store)

    student = store.create_student(name="E2E Student", profile={"level": "beginner"})
    sid = student["student_id"]

    async def _pipeline():
        # Step 1: Diagnostic
        diag = await gen.generate_diagnostic(student, num_questions=4, llm=False)
        assert diag["ok"], f"Diagnostic failed: {diag.get('error')}"
        aid = diag["assessment_id"]

        # Step 2: Answer diagnostic questions (mix correct/wrong)
        for i, q in enumerate(diag["questions"]):
            q_full = store.get_question(q["question_id"])
            if i % 2 == 0:
                chosen = q_full["answer"]
            else:
                opts = q_full.get("options", [])
                chosen = next((o for o in opts if o != q_full["answer"]), q_full["answer"])
            res = await gen.submit_answer(student, aid, q["question_id"], chosen)
            assert "correct" in res

        # Step 3: Finalize diagnostic
        finalize = gen.finalize_diagnostic(student, aid)
        assert finalize["ok"], f"Finalize failed: {finalize.get('error')}"

        # Step 4: Generate report
        report = gen.generate_report(student, aid)
        assert "overall_mastery" in report or "weak_topics" in report

        # Step 5: Generate study plan
        plan = planner.study_plan(sid, exam_days=14, sessions_per_week=7)
        assert plan["ok"], f"Plan failed: {plan.get('error')}"
        assert len(plan["days"]) > 0

        # Step 6: Generate flashcards
        cards = planner.weakness_flashcards(sid, limit=5)
        assert cards["ok"]

        # Step 7: Course graph
        graph = planner.course_graph(student_id=sid)
        assert len(graph["nodes"]) > 0

        # Step 8: Wrong questions recorded
        wrong_qs = store.list_wrong_questions(sid)
        assert len(wrong_qs) >= 1

        # Step 9: Second quiz (should avoid repeats)
        quiz2 = await gen.generate_quiz(student, ["t_vars", "t_funcs", "t_loops"],
                                         num_questions=4, llm=False)
        assert quiz2["ok"]
        return True

    result = asyncio.run(_pipeline())
    assert result


def test_wrong_question_retest_pipeline():
    store = _seed_store()
    gen = AssessmentGenerator(store)
    student = store.create_student(name="Retest Student", profile={"level": "beginner"})
    sid = student["student_id"]

    async def _pipeline():
        quiz = await gen.generate_quiz(student, ["t_vars", "t_funcs"], num_questions=4, llm=False)
        assert quiz["ok"]
        aid = quiz["assessment_id"]

        for q in quiz["questions"]:
            q_full = store.get_question(q["question_id"])
            opts = q_full.get("options", [])
            wrong = next((o for o in opts if o != q_full["answer"]), "")
            await gen.submit_answer(student, aid, q["question_id"], wrong)

        wrong_qs = store.list_wrong_questions(sid)
        assert len(wrong_qs) >= 1

        unresolved = [w for w in wrong_qs if not w["resolved"]]
        topic_ids = list({tid for w in unresolved for tid in w["topic_ids"]})
        retest = await gen.generate_quiz(student, topic_ids, num_questions=4, llm=False)
        assert retest["ok"]
        assert len(retest["questions"]) > 0
        return True

    result = asyncio.run(_pipeline())
    assert result