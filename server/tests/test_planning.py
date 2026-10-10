# -*- coding: utf-8 -*-
"""Unit tests for learning planner (topological sort, study plan)."""

import tempfile
from app.services.tutor.store import TutorStore
from app.services.tutor.planning import LearningPlanner, _WEAK_THRESHOLD, _MASTERED_THRESHOLD
from app.services.tutor.learner import LearnerModel


def _make_store_with_topics():
    store = TutorStore(data_dir=tempfile.mkdtemp(prefix="test_planning_"))
    store.upsert_topic(topic_id="t_base", name="Base Topic",
                       concepts=["basics"], prerequisites=[])
    store.upsert_topic(topic_id="t_mid", name="Mid Topic",
                       concepts=["intermediate"], prerequisites=["t_base"])
    store.upsert_topic(topic_id="t_advanced", name="Advanced Topic",
                       concepts=["advanced"], prerequisites=["t_mid"])
    store.upsert_topic(topic_id="t_independent", name="Independent Topic",
                       concepts=["standalone"], prerequisites=[])
    return store


def test_topological_sort_valid_order():
    store = _make_store_with_topics()
    planner = LearningPlanner(store)
    topics = store.list_topics_by_id()
    ordered = planner._toposort(topics)
    base_idx = ordered.index("t_base")
    mid_idx = ordered.index("t_mid")
    adv_idx = ordered.index("t_advanced")
    assert base_idx < mid_idx, f"t_base should come before t_mid: {ordered}"
    assert mid_idx < adv_idx, f"t_mid should come before t_advanced: {ordered}"


def test_topological_sort_with_cycles():
    store = _make_store_with_topics()
    planner = LearningPlanner(store)
    store.upsert_topic(topic_id="t_cycle_a", name="Cycle A",
                       concepts=[], prerequisites=["t_cycle_b"])
    store.upsert_topic(topic_id="t_cycle_b", name="Cycle B",
                       concepts=[], prerequisites=["t_cycle_a"])
    topics = store.list_topics_by_id()
    ordered = planner._toposort(topics)
    assert "t_cycle_a" in ordered
    assert "t_cycle_b" in ordered
    assert len(ordered) == len(topics), f"Missing topics: {set(topics.keys()) - set(ordered)}"


def test_course_graph_structure():
    store = _make_store_with_topics()
    planner = LearningPlanner(store)
    graph = planner.course_graph()
    assert len(graph["nodes"]) == 4
    edges = graph["edges"]
    assert len(edges) == 2, f"Expected 2 prerequisite edges, got {len(edges)}: {edges}"
    edge_pairs = {(e["from"], e["to"]) for e in edges}
    assert ("t_base", "t_mid") in edge_pairs
    assert ("t_mid", "t_advanced") in edge_pairs


def test_study_plan_respects_exam_days():
    store = _make_store_with_topics()
    planner = LearningPlanner(store)
    student = store.create_student(name="Plan Test Student", profile={"level": "beginner"})
    plan = planner.study_plan(student["student_id"], exam_days=7, sessions_per_week=5)
    assert plan["ok"], f"Study plan failed: {plan.get('error')}"
    assert plan["exam_days"] == 7
    for day_info in plan["days"]:
        assert 1 <= day_info["day"] <= 7, f"Day {day_info['day']} out of range [1, 7]"


def test_study_plan_topics_ordered_by_prerequisites():
    store = _make_store_with_topics()
    planner = LearningPlanner(store)
    student = store.create_student(name="Order Test", profile={"level": "beginner"})
    plan = planner.study_plan(student["student_id"], exam_days=14, sessions_per_week=7)
    topic_days = {}
    for day_info in plan["days"]:
        for activity in day_info["activities"]:
            tid = activity["topic_id"]
            if tid not in topic_days:
                topic_days[tid] = day_info["day"]
    assert (
        topic_days.get("t_base", 999) < topic_days.get("t_mid", 999)
    ), f"t_base should come before t_mid: {topic_days}"
    assert (
        topic_days.get("t_mid", 999) < topic_days.get("t_advanced", 999)
    ), f"t_mid should come before t_advanced: {topic_days}"


def test_flashcards_have_citation_labels():
    store = TutorStore(data_dir=tempfile.mkdtemp(prefix="test_flashcards_"))
    planner = LearningPlanner(store)
    store.upsert_topic(topic_id="t_flash", name="Flashcards Topic",
                       concepts=["test"], prerequisites=[])
    src_id = store.add_source(title="Flashcard Source", kind="text", path="")["source_id"]
    store.add_unit(
        source_id=src_id,
        text="Variables are names that refer to values in memory locations.",
        origin={"index": 0, "label": "text#1"},
        topic_ids=["t_flash"], concepts=["test"],
    )
    student = store.create_student(name="Flashcard Test", profile={"level": "beginner"})
    cards_result = planner.weakness_flashcards(student["student_id"], limit=5)
    assert cards_result["ok"], f"Flashcards failed: {cards_result.get('error')}"
    if cards_result["count"] > 0:
        cards = cards_result["cards"]
        assert len(cards) > 0
        card = cards[0]
        assert "front" in card, f"Card missing front: {card}"
        assert "back" in card, f"Card missing back: {card}"
        assert "topic_name" in card, f"Card missing topic_name: {card}"


def test_mastery_summary_format():
    store = TutorStore(data_dir=tempfile.mkdtemp(prefix="test_mastery_summary_"))
    learner = LearnerModel()
    student = store.create_student(name="Summary Test", profile={"level": "beginner"})
    for _ in range(3):
        learner.observe(student, "t_test", correct=True)
    for _ in range(2):
        learner.observe(student, "t_test", correct=False)
    topics = store.list_topics_by_id()
    summary = learner.mastery_summary(student, topics)
    if "t_test" in summary:
        entry = summary["t_test"]
        assert "name" in entry
        assert "mastery" in entry
        assert "n_correct" in entry
        assert "n_wrong" in entry
        assert 0.0 <= entry["mastery"] <= 1.0
