# -*- coding: utf-8 -*-
"""Unit tests for assessment generator (cloze-MCQ)."""

import asyncio
from app.services.tutor.store import TutorStore
from app.services.tutor.assessment import AssessmentGenerator
from app.services.tutor.learner import LearnerModel


def _make_store():
    import tempfile
    return TutorStore(data_dir=tempfile.mkdtemp(prefix="test_ecv_"))


def test_cloze_answer_in_source():
    store = _make_store()
    gen = AssessmentGenerator(store)
    src_id = store.add_source(title="Test Source", kind="text", path="")["source_id"]
    text = "A variable is a name that refers to a value stored in memory."
    store.add_unit(source_id=src_id, text=text, origin={"index": 0, "label": "test#1"},
                   topic_ids=["t_test"], concepts=["test"])
    unit = {"unit_id": "u1", "source_id": src_id, "text": text, "origin": {"label": "test#1"}, "topic_ids": ["t_test"]}
    q = gen._make_question(unit, text, ["t_test"], difficulty="medium")
    assert q is not None
    assert q["answer"] in q["options"]
    assert q["answer"].lower() in text.lower()


def test_cloze_no_duplicate_answer():
    store = _make_store()
    gen = AssessmentGenerator(store)
    src_id = store.add_source(title="Test Source", kind="text", path="")["source_id"]
    text = "The len function returns the number of items in a sequence."
    store.add_unit(source_id=src_id, text=text, origin={"index": 0, "label": "test#1"},
                   topic_ids=["t_test"], concepts=["test"])
    unit = {"unit_id": "u2", "source_id": src_id, "text": text, "origin": {"label": "test#1"}, "topic_ids": ["t_test"]}
    q = gen._make_question(unit, text, ["t_test"], difficulty="medium")
    assert q is not None
    answer_count = sum(1 for opt in q["options"] if opt == q["answer"])
    assert answer_count == 1


def test_generate_quiz_varied():
    store = _make_store()
    gen = AssessmentGenerator(store)
    gen.learner = LearnerModel()
    src_id = store.add_source(title="Test Course", kind="text", path="")["source_id"]
    for i in range(10):
        store.add_unit(source_id=src_id,
            text=f"Sentence number {i} about variables in Python programming language here.",
            origin={"index": i, "label": f"test#{i+1}"}, topic_ids=["t_test"], concepts=["test"])
    student = store.create_student(name="Test Student", profile={"level": "beginner"})
    async def _run():
        return await gen.generate_quiz(student, ["t_test"], num_questions=5, llm=False)
    result = asyncio.run(_run())
    assert result["ok"]
    assert len(result["questions"]) > 0
    qtexts = [q["text"] for q in result["questions"]]
    assert len(qtexts) == len(set(qtexts))
    # Original unit texts so we can prove the answer string "strictly exists"
    # in the source material (Phase 2 requirement).
    source_text = " ".join(u["text"].lower() for u in store.list_units())
    for q in result["questions"]:
        assert len(q.get("options", [])) >= 2
        # The public question must NOT leak the answer key (server-side grading).
        assert "answer" not in q
        q_full = store.get_question(q["question_id"])
        assert q_full is not None
        assert q_full["answer"], "stored question must keep an answer key"
        assert q_full["answer"] in q_full.get("options", []), "answer among options"
        assert q_full["answer"].lower() in source_text, f"answer not in source: {q_full['answer']}"


def test_quiz_avoids_repeat():
    store = _make_store()
    gen = AssessmentGenerator(store)
    gen.learner = LearnerModel()
    src_id = store.add_source(title="Test Course", kind="text", path="")["source_id"]
    for i in range(20):
        store.add_unit(source_id=src_id,
            text=f"Different sentence number {i} covering Python programming concepts and ideas.",
            origin={"index": i, "label": f"test#{i+1}"}, topic_ids=["t_test"], concepts=["test"])
    student = store.create_student(name="Repeat Test", profile={"level": "beginner"})
    async def _run():
        q1 = await gen.generate_quiz(student, ["t_test"], num_questions=5, llm=False)
        q2 = await gen.generate_quiz(student, ["t_test"], num_questions=5, llm=False)
        return q1, q2
    quiz1, quiz2 = asyncio.run(_run())
    ids1 = {q["question_id"] for q in quiz1["questions"]}
    ids2 = {q["question_id"] for q in quiz2["questions"]}
    overlap = ids1 & ids2
    assert len(overlap) < len(ids1) * 0.5, f"Too much overlap: {len(overlap)}/{len(ids1)}"


def test_short_sentence_no_question():
    store = _make_store()
    gen = AssessmentGenerator(store)
    src_id = store.add_source(title="Test Source", kind="text", path="")["source_id"]
    store.add_unit(source_id=src_id, text="Hi.", origin={"label": "test#1"},
                   topic_ids=["t_test"], concepts=["test"])
    unit = {"unit_id": "u3", "source_id": src_id, "text": "Hi.", "origin": {"label": "test#1"}, "topic_ids": ["t_test"]}
    result = gen._pick_sentence(unit)
    assert result is None


def test_difficulty_maps_mastery():
    gen = AssessmentGenerator(_make_store())
    assert gen._difficulty_for_mastery(0.1) == "easy"
    assert gen._difficulty_for_mastery(0.3) == "easy"
    assert gen._difficulty_for_mastery(0.5) == "medium"
    assert gen._difficulty_for_mastery(0.65) == "medium"
    assert gen._difficulty_for_mastery(0.8) == "hard"
    assert gen._difficulty_for_mastery(0.95) == "hard"


def test_distractor_limit_by_difficulty():
    gen = AssessmentGenerator(_make_store())
    assert gen._distractor_limit("easy") == 1
    assert gen._distractor_limit("medium") == 2
    assert gen._distractor_limit("hard") == 3


def test_submit_answer_records_wrong_question():
    store = _make_store()
    gen = AssessmentGenerator(store)
    gen.learner = LearnerModel()
    src_id = store.add_source(title="Test Source", kind="text", path="")["source_id"]
    store.add_unit(source_id=src_id,
        text="The print function outputs text to the console terminal.",
        origin={"index": 0, "label": "test#1"}, topic_ids=["t_test"], concepts=["test"])
    student = store.create_student(name="Wrong Q Student", profile={"level": "beginner"})

    async def _run():
        quiz = await gen.generate_quiz(student, ["t_test"], num_questions=1, llm=False)
        assert quiz["ok"]
        q = quiz["questions"][0]
        q_full = store.get_question(q["question_id"])
        wrong_choice = next((o for o in q_full["options"] if o != q_full["answer"]), "")
        return await gen.submit_answer(student, quiz["assessment_id"], q["question_id"], wrong_choice)

    result = asyncio.run(_run())
    assert not result["correct"]
    wrong_qs = store.list_wrong_questions(student["student_id"])
    assert len(wrong_qs) == 1
    assert wrong_qs[0]["question_id"] == result["question"]["question_id"]
    assert wrong_qs[0]["resolved"] is False


def test_submit_correct_no_wrong_question():
    store = _make_store()
    gen = AssessmentGenerator(store)
    gen.learner = LearnerModel()
    src_id = store.add_source(title="Test Source", kind="text", path="")["source_id"]
    store.add_unit(source_id=src_id,
        text="The input function reads a value from the keyboard terminal.",
        origin={"index": 0, "label": "test#1"}, topic_ids=["t_test"], concepts=["test"])
    student = store.create_student(name="Correct Q Student", profile={"level": "beginner"})

    async def _run():
        quiz = await gen.generate_quiz(student, ["t_test"], num_questions=1, llm=False)
        assert quiz["ok"]
        q = quiz["questions"][0]
        q_full = store.get_question(q["question_id"])
        return await gen.submit_answer(student, quiz["assessment_id"], q["question_id"], q_full["answer"])

    result = asyncio.run(_run())
    assert result["correct"]
    wrong_qs = store.list_wrong_questions(student["student_id"])
    assert len(wrong_qs) == 0


def test_verify_question_valid():
    store = _make_store()
    gen = AssessmentGenerator(store)
    qid = store.add_question(
        text="What is 2+2?", qtype="mcq",
        options=["3", "4", "5"], answer="4",
        topic_ids=["t_math"], source_ids=[],
        difficulty="easy", answer_key="1", explanation="Basic addition")
    result = gen.verify_question(qid)
    assert result["valid"]
    assert result["issues"] == []


def test_verify_question_invalid():
    store = _make_store()
    gen = AssessmentGenerator(store)
    qid = store.add_question(
        text="", qtype="mcq",
        options=["only_one"], answer="only_one",
        topic_ids=["t_math"], source_ids=[],
        difficulty="easy", answer_key="0", explanation="")
    result = gen.verify_question(qid)
    assert not result["valid"]
    assert "empty stem" in result["issues"]
    assert "fewer than 2 options" in result["issues"]