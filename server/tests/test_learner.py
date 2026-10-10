# -*- coding: utf-8 -*-
"""Unit tests for BKT learner model."""

from app.services.tutor.learner import LearnerModel, _clamp


def test_clamp_bounds():
    assert _clamp(-0.5) == 0.001
    assert _clamp(1.5) == 0.999
    assert _clamp(0.5) == 0.5


def test_bkt_initial_state():
    learner = LearnerModel()
    student = {"profile": {}}
    state = learner.get_mastery(student, "t_variables")
    assert "pL0" in state and "pT" in state and "pG" in state and "pS" in state
    assert state["n_correct"] == 0 and state["n_wrong"] == 0 and state["updates"] == 0
    assert 0.001 <= state["pL0"] <= 0.999


def test_bkt_correct_increases_mastery():
    learner = LearnerModel(learner_skill=0.75)
    student = {"profile": {}}
    initial = learner.mastery_level(student, "t_var")
    new = learner.observe(student, "t_var", correct=True)
    assert new > initial
    assert student["mastery"]["t_var"]["n_correct"] == 1


def test_bkt_wrong_decreases_mastery():
    learner = LearnerModel(learner_skill=0.75)
    student = {"profile": {}}
    initial = learner.mastery_level(student, "t_var")
    new = learner.observe(student, "t_var", correct=False)
    assert new < initial
    assert student["mastery"]["t_var"]["n_wrong"] == 1


def test_bkt_mastery_always_in_range():
    learner = LearnerModel(learner_skill=1.0)
    student = {"profile": {}}
    for _ in range(20):
        learner.observe(student, "t_var", correct=True)
    m = learner.mastery_level(student, "t_var")
    assert 0.0 <= m <= 1.0, f"Mastery {m} out of range"
    student["mastery"]["t_var"]["n_correct"] = 0
    student["mastery"]["t_var"]["n_wrong"] = 0
    for _ in range(20):
        learner.observe(student, "t_var", correct=False)
    m = learner.mastery_level(student, "t_var")
    assert 0.0 <= m <= 1.0, f"Mastery {m} out of range after errors"


def test_bkt_converge_high_correct():
    learner = LearnerModel(learner_skill=0.75)
    student = {"profile": {}}
    for _ in range(10):
        learner.observe(student, "t_var", correct=True)
    m = learner.mastery_level(student, "t_var")
    assert m > 0.5, f"Expected high mastery after 10 correct, got {m}"


def test_bkt_converge_low_wrong():
    learner = LearnerModel(learner_skill=0.75)
    student = {"profile": {}}
    for _ in range(5):
        learner.observe(student, "t_var", correct=True)
    initial_high = learner.mastery_level(student, "t_var")
    for _ in range(10):
        learner.observe(student, "t_var", correct=False)
    final_low = learner.mastery_level(student, "t_var")
    assert final_low < initial_high and final_low < 0.5


def test_weakest_topics_ordering():
    learner = LearnerModel()
    student = {"profile": {}, "mastery": {
        "t_a": {"pL0": 0.8, "n_correct": 5, "n_wrong": 0, "updates": 5},
        "t_b": {"pL0": 0.3, "n_correct": 1, "n_wrong": 3, "updates": 4},
        "t_c": {"pL0": 0.6, "n_correct": 3, "n_wrong": 1, "updates": 4},
    }}
    weakest = learner.weakest_topics(student, ["t_a", "t_b", "t_c"], limit=3)
    assert weakest[0][0] == "t_b" and weakest[0][1] == 0.3
    assert weakest[1][0] == "t_c" and weakest[1][1] == 0.6
    assert weakest[2][0] == "t_a" and weakest[2][1] == 0.8


def test_diagnostic_prior_mapping():
    learner = LearnerModel()
    correct_map = {"t_high": 0.8, "t_mid": 0.4, "t_low": 0.2}
    priors = learner.knowledge_prior_from_diagnostic(correct_map)
    assert len(priors) == 3
    for p in priors.values():
        assert 0.02 <= p <= 0.98
    assert priors["t_high"] > priors["t_low"]
