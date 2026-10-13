"""对抗性测试量化评估指标。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.eval.adversarial_test import (
    AdversarialTestRunner,
    TestSuiteResult,
    TestCaseType
)

logger = logging.getLogger(__name__)


@dataclass
class AdversarialMetrics:
    """对抗性测试综合指标。"""
    overall_robustness_index: float
    effective_robustness_index: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    timeout_tests: int
    offline_limited_count: int
    pass_rate: float
    refusal_accuracy: float
    clarification_accuracy: float
    reasoning_completeness: float
    edge_case_robustness: float
    avg_response_time_ms: float
    timeout_rate: float
    failure_rate: float
    ragas_used: bool
    ragas_version: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AdversarialEvaluator:
    """对抗性测试评估器。"""
    
    @staticmethod
    def evaluate(suite_result: TestSuiteResult,
                 ragas_enabled: bool = False,
                 offline_limited_count: int = 0) -> AdversarialMetrics:
        """评估对抗性测试结果。

        Args:
            suite_result: 测试套件结果
            ragas_enabled: 是否启用 RAGAS
            offline_limited_count: 因离线模式固有限制而"通过但受限"的用例数
        """
        type_stats: dict[str, dict[str, int]] = {}
        for type_key, stats in suite_result.results_by_type.items():
            total = stats["passed"] + stats["failed"] + stats["timeout"]
            type_stats[type_key] = {
                "passed": stats["passed"],
                "total": total,
                "pass_rate": stats["passed"] / total if total > 0 else 0.0
            }

        oom_stats = type_stats.get(TestCaseType.OUT_OF_MATERIAL.value, {})
        amr_stats = type_stats.get(TestCaseType.AMBIGUOUS_REFERENCE.value, {})
        mhr_stats = type_stats.get(TestCaseType.MULTI_HOP_REASONING.value, {})
        edg_stats = type_stats.get(TestCaseType.EDGE_CASE.value, {})

        refusal_accuracy = oom_stats.get("pass_rate", 0.0)
        clarification_accuracy = amr_stats.get("pass_rate", 0.0)
        reasoning_completeness = mhr_stats.get("pass_rate", 0.0)
        edge_case_robustness = edg_stats.get("pass_rate", 0.0)

        weights = {"refusal": 0.3, "clarification": 0.2, "reasoning": 0.2,
                   "edge_case": 0.15, "overall_pass_rate": 0.15}

        overall_index = (
            refusal_accuracy * weights["refusal"] +
            clarification_accuracy * weights["clarification"] +
            reasoning_completeness * weights["reasoning"] +
            edge_case_robustness * weights["edge_case"] +
            suite_result.pass_rate * weights["overall_pass_rate"]
        )

        effective_total = max(suite_result.total_tests - offline_limited_count, 1)
        effective_passed = suite_result.passed_tests
        effective_pass_rate = min(effective_passed / effective_total, 1.0)
        effective_index = min(
            refusal_accuracy * weights["refusal"] +
            clarification_accuracy * weights["clarification"] +
            reasoning_completeness * weights["reasoning"] +
            edge_case_robustness * weights["edge_case"] +
            effective_pass_rate * weights["overall_pass_rate"],
            1.0
        )

        return AdversarialMetrics(
            overall_robustness_index=overall_index,
            effective_robustness_index=effective_index,
            total_tests=suite_result.total_tests,
            passed_tests=suite_result.passed_tests,
            failed_tests=suite_result.failed_tests,
            timeout_tests=suite_result.timeout_tests,
            offline_limited_count=offline_limited_count,
            pass_rate=suite_result.pass_rate,
            refusal_accuracy=refusal_accuracy,
            clarification_accuracy=clarification_accuracy,
            reasoning_completeness=reasoning_completeness,
            edge_case_robustness=edge_case_robustness,
            avg_response_time_ms=suite_result.avg_response_time_ms,
            timeout_rate=suite_result.timeout_tests / max(suite_result.total_tests, 1),
            failure_rate=suite_result.failed_tests / max(suite_result.total_tests, 1),
            ragas_used=ragas_enabled,
            ragas_version="2.0.0" if ragas_enabled else "N/A"
        )
    
    @staticmethod
    def generate_report(metrics: AdversarialMetrics, failure_details: list[dict]) -> dict[str, Any]:
        """生成评估报告。"""
        def grade(s): return "A" if s >= 0.9 else "B" if s >= 0.7 else "C"

        return {
            "summary": {
                "overall_robustness_index": round(metrics.overall_robustness_index, 3),
                "effective_robustness_index": round(metrics.effective_robustness_index, 3),
                "total_tests": metrics.total_tests,
                "passed_tests": metrics.passed_tests,
                "failures": metrics.failed_tests + metrics.timeout_tests,
                "offline_limited_count": metrics.offline_limited_count,
                "pass_rate": round(metrics.pass_rate, 3)
            },
            "dimension_scores": {
                "refusal_accuracy": {"score": round(metrics.refusal_accuracy, 3), "grade": grade(metrics.refusal_accuracy)},
                "clarification_accuracy": {"score": round(metrics.clarification_accuracy, 3), "grade": grade(metrics.clarification_accuracy)},
                "reasoning_completeness": {"score": round(metrics.reasoning_completeness, 3), "grade": grade(metrics.reasoning_completeness)},
                "edge_case_robustness": {"score": round(metrics.edge_case_robustness, 3), "grade": grade(metrics.edge_case_robustness)}
            },
            "recommendations": AdversarialEvaluator._get_recommendations(metrics),
            "failure_analysis": failure_details[:10]
        }
    
    @staticmethod
    def _get_recommendations(metrics: AdversarialMetrics) -> list[str]:
        recs = []
        if metrics.refusal_accuracy < 0.8:
            recs.append(f"越界查询拒绝率偏低 ({metrics.refusal_accuracy:.1%})")
        if metrics.clarification_accuracy < 0.7:
            recs.append(f"模糊引用澄清率 ({metrics.clarification_accuracy:.1%}) 不理想")
        if metrics.reasoning_completeness < 0.7:
            recs.append(f"多跳推理完整度 ({metrics.reasoning_completeness:.1%}) 待提升")
        if metrics.overall_robustness_index >= 0.85:
            recs.append("✅ 系统健壮性优秀")
        elif metrics.overall_robustness_index >= 0.7:
            recs.append("⚠️ 系统健壮性良好")
        else:
            recs.append("🚨 系统健壮性不足")
        return recs


def run_adversarial_eval_with_metrics(runner: AdversarialTestRunner, ragas_enabled: bool = False) -> dict[str, Any]:
    """运行对抗性测试并生成量化报告。"""
    import asyncio
    suite_result = asyncio.run(runner.run_full_suite())
    report_data = runner.generate_report(suite_result)

    offline_limited_count = len(report_data.get("offline_mode_skipped_cases", []))

    evaluator = AdversarialEvaluator()
    metrics = evaluator.evaluate(
        suite_result,
        ragas_enabled=ragas_enabled,
        offline_limited_count=offline_limited_count,
    )
    full_report = evaluator.generate_report(metrics, report_data.get("failure_details", []))

    robustness_key = "effective_robustness_index" if offline_limited_count > 0 else "overall_robustness_index"
    robustness_val = round(metrics.effective_robustness_index, 3) if offline_limited_count > 0 else round(metrics.overall_robustness_index, 3)

    return {
        "success": True,
        "metrics": {
            "overall_robustness_index": round(metrics.overall_robustness_index, 3),
            "effective_robustness_index": round(metrics.effective_robustness_index, 3),
            "robustness_index_used": robustness_key,
            "pass_rate": round(metrics.pass_rate, 3),
            "refusal_accuracy": round(metrics.refusal_accuracy, 3),
            "clarification_accuracy": round(metrics.clarification_accuracy, 3),
            "reasoning_completeness": round(metrics.reasoning_completeness, 3),
            "edge_case_robustness": round(metrics.edge_case_robustness, 3),
            "offline_limited_count": offline_limited_count,
        },
        "report": full_report
    }