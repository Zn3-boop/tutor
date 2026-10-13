"""Unit tests for the cognitive error-pattern analyzer."""

import pytest

from app.services.tutor.error_analyzer import (
    ErrorAnalyzer,
    MISCONCEPTION_TAXONOMY,
    get_error_analyzer,
)


@pytest.fixture
def analyzer() -> ErrorAnalyzer:
    return ErrorAnalyzer()


class TestTaxonomy:
    def test_taxonomy_has_expected_types(self):
        expected = {
            "conceptual_confusion", "syntax_error", "logic_error",
            "calculation_error", "reading_comprehension", "missing_knowledge",
        }
        assert expected == set(MISCONCEPTION_TAXONOMY.keys())

    def test_every_entry_well_formed(self):
        for etype, info in MISCONCEPTION_TAXONOMY.items():
            assert info["label"], f"{etype} missing label"
            assert info["description"], f"{etype} missing description"
            assert info["keywords"], f"{etype} missing keywords"
            assert info["examples"], f"{etype} missing examples"


class TestClassifyError:
    def test_conceptual_confusion_detected(self, analyzer):
        result = analyzer.classify_error(
            question_text="list 和 tuple 的区别是什么？",
            student_answer="它们完全相似可以互换",
            correct_answer="list 可变，tuple 不可变",
        )
        assert result["error_type"] == "conceptual_confusion"
        assert result["confidence"] > 0
        assert result["error_label"] == "概念混淆"

    def test_syntax_error_detected(self, analyzer):
        result = analyzer.classify_error(
            question_text="下面哪一行有语法问题？",
            student_answer="缩进没有影响",
            correct_answer="缺少冒号",
        )
        assert result["error_type"] == "syntax_error"

    def test_missing_knowledge_detected(self, analyzer):
        result = analyzer.classify_error(
            question_text="什么是装饰器？",
            student_answer="不知道",
            correct_answer="装饰器是一种语法糖",
        )
        assert result["error_type"] == "missing_knowledge"

    def test_heuristic_fallback_on_no_keyword_match(self, analyzer):
        # 中文文本不含任何 taxonomy 关键词，应走启发式或 unknown
        result = analyzer.classify_error(
            question_text="AAA BBB CCC",
            student_answer="X",
            correct_answer="Y",
        )
        assert result["error_type"] in MISCONCEPTION_TAXONOMY or result["error_type"] == "unknown"
        assert "all_scores" in result

    def test_result_structure(self, analyzer):
        result = analyzer.classify_error(
            question_text="q", student_answer="a", correct_answer="b",
        )
        for key in ("error_type", "error_label", "confidence",
                    "keywords_matched", "similar_misconceptions",
                    "remediation_hint", "all_scores"):
            assert key in result

    def test_remediation_hint_nonempty(self, analyzer):
        result = analyzer.classify_error(
            question_text="理解题意", student_answer="wrong", correct_answer="right",
        )
        assert result["remediation_hint"]

    def test_unknown_type_has_hint(self, analyzer):
        hints = analyzer._generate_remediation_hint("totally_unknown_type", [])
        assert hints  # even unknown types must produce guidance


class TestAnalyzeQuizErrors:
    def test_all_correct_yields_empty(self, analyzer):
        results = [
            {"question": "q", "student_answer": "a", "correct_answer": "a",
             "is_correct": True, "topic_ids": ["t1"]},
        ]
        analysis = analyzer.analyze_quiz_errors(results)
        assert analysis["total_errors"] == 0
        assert analysis["error_distribution"] == {}

    def test_errors_aggregated(self, analyzer):
        results = [
            {"question": "list 和 tuple 区别", "student_answer": "x",
             "correct_answer": "y", "is_correct": False, "topic_ids": ["t1"]},
            {"question": "循环条件判断问题", "student_answer": "x",
             "correct_answer": "y", "is_correct": False, "topic_ids": ["t1", "t2"]},
            {"question": "无关题目", "student_answer": "x",
             "correct_answer": "y", "is_correct": False, "topic_ids": ["t3"]},
        ]
        analysis = analyzer.analyze_quiz_errors(results)
        assert analysis["total_errors"] == 3
        assert sum(analysis["error_distribution"].values()) == 3
        # t1 appeared in two wrong answers
        assert sum(analysis["topic_error_patterns"]["t1"].values()) == 2
        # top misconceptions ranked by count, max 3 entries
        assert len(analysis["strongest_misconceptions"]) <= 3
        counts = [m["count"] for m in analysis["strongest_misconceptions"]]
        assert counts == sorted(counts, reverse=True)

    def test_empty_input(self, analyzer):
        analysis = analyzer.analyze_quiz_errors([])
        assert analysis["total_errors"] == 0
        assert "analysis_timestamp" in analysis

    def test_percentage_computation(self, analyzer):
        results = [
            {"question": "概念混淆题目", "student_answer": "a",
             "correct_answer": "b", "is_correct": False, "topic_ids": []},
        ] * 4
        analysis = analyzer.analyze_quiz_errors(results)
        for m in analysis["strongest_misconceptions"]:
            assert m["percentage"] == 100.0


class TestSingleton:
    def test_get_error_analyzer_returns_same_instance(self):
        assert get_error_analyzer() is get_error_analyzer()