"""RAGAS 诊断评估模块测试。"""

import pytest

from app.services.eval.ragas_diagnostic import (
    DiagnosticTestCase,
    DiagnosticEvaluator,
    RAGASDiagnosticPipeline,
    run_diagnostic_eval
)
from app.services.tutor.error_analyzer import get_error_analyzer, MISCONCEPTION_TAXONOMY


class TestDiagnosticTestCase:
    def test_dataclass_fields(self):
        tc = DiagnosticTestCase(
            test_id="t1",
            student_answer="answer",
            correct_answer="correct",
            question_text="question",
            expected_error_type="conceptual_confusion",
            expected_label="概念混淆"
        )
        assert tc.test_id == "t1"
        assert tc.expected_error_type == "conceptual_confusion"
        assert tc.gold_contexts == []
        assert tc.metadata == {}


class TestDiagnosticEvaluator:
    def test_build_test_suite_returns_fourteen_cases(self):
        evaluator = DiagnosticEvaluator()
        cases = evaluator.build_test_suite()
        assert len(cases) == 14
        assert all(hasattr(c, "test_id") for c in cases)

    def test_all_six_taxonomy_types_covered(self):
        evaluator = DiagnosticEvaluator()
        cases = evaluator.build_test_suite()
        types = {c.expected_error_type for c in cases}
        assert types == set(MISCONCEPTION_TAXONOMY.keys())

    def test_all_labels_match_taxonomy(self):
        evaluator = DiagnosticEvaluator()
        cases = evaluator.build_test_suite()
        for c in cases:
            expected_label = MISCONCEPTION_TAXONOMY[c.expected_error_type]["label"]
            assert c.expected_label == expected_label, (
                f"{c.test_id}: expected '{expected_label}', got '{c.expected_label}'"
            )

    def test_each_case_has_required_fields(self):
        evaluator = DiagnosticEvaluator()
        cases = evaluator.build_test_suite()
        for c in cases:
            assert c.test_id, "test_id must not be empty"
            assert c.student_answer, "student_answer must not be empty"
            assert c.correct_answer, "correct_answer must not be empty"
            assert c.question_text, "question_text must not be empty"
            assert c.expected_error_type in MISCONCEPTION_TAXONOMY, (
                f"unknown error type: {c.expected_error_type}"
            )

    def test_no_duplicate_test_ids(self):
        evaluator = DiagnosticEvaluator()
        cases = evaluator.build_test_suite()
        ids = [c.test_id for c in cases]
        assert len(ids) == len(set(ids)), "duplicate test_id found"


class TestRAGASDiagnosticPipeline:
    @pytest.fixture
    def pipeline(self):
        analyzer = get_error_analyzer()
        return RAGASDiagnosticPipeline(analyzer)

    def test_run_full_evaluation_returns_required_keys(self, pipeline):
        report = pipeline.run_full_evaluation()
        required_keys = [
            "accuracy", "precision", "recall", "f1",
            "total_cases", "per_type_breakdown",
            "failed_cases", "ragas_used"
        ]
        for key in required_keys:
            assert key in report, f"missing key: {key}"

    def test_accuracy_in_valid_range(self, pipeline):
        report = pipeline.run_full_evaluation()
        assert 0.0 <= report["accuracy"] <= 1.0

    def test_total_cases_matches_suite_size(self, pipeline):
        report = pipeline.run_full_evaluation()
        assert report["total_cases"] == 14

    def test_extended_dimensions_are_reported(self, pipeline):
        report = pipeline.run_full_evaluation(
            graph_data={
                "edges": [{"from": "t1", "to": "t2", "type": "prerequisite"}],
                "recommended_path": [{"topic_id": "t1"}, {"topic_id": "t2"}],
            },
            robustness_score=0.8,
        )
        assert report["misconception_coverage"]["score"] == 1.0
        assert 0.0 <= report["remediation_relevance"]["score"] <= 1.0
        assert report["path_reasonableness"]["score"] == 1.0
        assert report["robustness_score"] == 0.8
        assert set(report["dimensions"]) == {
            "error_classification", "misconception_coverage",
            "remediation_relevance", "path_reasonableness", "robustness",
        }

    def test_path_reasonableness_detects_reversed_prerequisite(self, pipeline):
        result = pipeline._path_reasonableness({
            "edges": [{"from": "t1", "to": "t2", "type": "prerequisite"}],
            "recommended_path": [{"topic_id": "t2"}, {"topic_id": "t1"}],
        })
        assert result["score"] == 0.0
        assert result["violations"] == [{"prerequisite": "t1", "topic": "t2"}]
