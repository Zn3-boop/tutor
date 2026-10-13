"""RAGAS 评估扩展 - 针对认知诊断和错误模式识别模块。

本模块扩展了现有的 RAGAS 评估框架，增加对以下维度的量化评估：
1. 错误分类准确率 (Error Classification Accuracy)
2. 误解检测完整性 (Misconception Coverage)
3. 复习建议相关性 (Remediation Relevance)
4. 图谱推荐路径合理性 (Path Reasonableness)
5. 对抗测试鲁棒性 (Robustness Score)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticTestCase:
    """认知诊断测试用例。"""
    test_id: str
    student_answer: str
    correct_answer: str
    question_text: str
    expected_error_type: str  # "conceptual_confusion", "syntax_error", etc.
    expected_label: str  # "概念混淆", "语法错误", etc.
    gold_contexts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticResult:
    """单条测试用例的评估结果。"""
    test_case: DiagnosticTestCase
    predicted_type: str
    predicted_label: str
    confidence: float
    type_correct: bool  # 类型预测是否正确
    label_correct: bool  # 标签预测是否正确
    error: str | None = None


class DiagnosticEvaluator:
    """认知诊断模块的 RAGAS 式评估器。"""
    
    def __init__(self):
        self.test_cases: list[DiagnosticTestCase] = []
    
    def build_test_suite(self) -> list[DiagnosticTestCase]:
        """构建诊断测试套件（覆盖 6 类错误类型）。"""
        self.test_cases = [
            # 概念混淆
            DiagnosticTestCase(
                test_id="diag_001",
                student_answer="它们完全一样，可以互换使用",
                correct_answer="list 可变而 tuple 不可变",
                question_text="list 和 tuple 的区别是什么？",
                expected_error_type="conceptual_confusion",
                expected_label="概念混淆",
                gold_contexts=["list 是可变序列", "tuple 是不可变序列"]
            ),
            DiagnosticTestCase(
                test_id="diag_002",
                student_answer="global 变量只能在函数外部使用",
                correct_answer="global 变量可在函数内外访问",
                question_text="global 变量的作用域是什么？",
                expected_error_type="conceptual_confusion",
                expected_label="概念混淆",
                gold_contexts=["global 关键字声明全局变量"]
            ),
            
            # 语法错误
            DiagnosticTestCase(
                test_id="diag_003",
                student_answer="在函数体内直接写代码，不需要缩进",
                correct_answer="Python 使用缩进定义代码块",
                question_text="Python 的代码块如何表示？",
                expected_error_type="syntax_error",
                expected_label="语法错误",
                gold_contexts=["Python 使用缩进而不是大括号"]
            ),
            
            # 逻辑错误
            DiagnosticTestCase(
                test_id="diag_004",
                student_answer="使用 while True: 作为终止条件",
                correct_answer="使用 if condition: break",
                question_text="如何正确终止循环？",
                expected_error_type="logic_error",
                expected_label="逻辑错误",
                gold_contexts=["break 语句退出循环"]
            ),
            
            # 计算错误
            DiagnosticTestCase(
                test_id="diag_005",
                student_answer="7 // 2 = 3.5",
                correct_answer="7 // 2 = 3",
                question_text="7 整除 2 的结果是多少？",
                expected_error_type="calculation_error",
                expected_label="计算错误",
                gold_contexts=["// 运算符执行整数除法"]
            ),
            
            # 阅读理解问题
            DiagnosticTestCase(
                test_id="diag_006",
                student_answer="函数名可以包含空格",
                correct_answer="函数名不能包含空格",
                question_text="Python 函数命名规则是什么？",
                expected_error_type="reading_comprehension",
                expected_label="阅读理解问题",
                gold_contexts=["标识符只能包含字母、数字和下划线"]
            ),
            
            # 知识缺失
            DiagnosticTestCase(
                test_id="diag_007",
                student_answer="不了解装饰器是什么",
                correct_answer="装饰器用于修改函数行为的工具",
                question_text="什么是装饰器？",
                expected_error_type="missing_knowledge",
                expected_label="知识缺失",
                gold_contexts=["装饰器是一种设计模式", "用 @符号使用"]
            ),

            # --- 边界场景补充 ---

            # 概念混淆：= 与 ==
            DiagnosticTestCase(
                test_id="diag_008",
                student_answer="= 用来判断两个值是否相等",
                correct_answer="== 用来判断相等，= 用来赋值",
                question_text="= 和 == 的区别是什么？",
                expected_error_type="conceptual_confusion",
                expected_label="概念混淆",
                gold_contexts=["= 是赋值运算符", "== 是比较运算符"]
            ),

            # 语法错误：缩进
            DiagnosticTestCase(
                test_id="diag_009",
                student_answer="if x > 0:\nprint(x) 不需要缩进",
                correct_answer="if 语句后的代码块必须缩进",
                question_text="Python if 语句的代码块如何表示？",
                expected_error_type="syntax_error",
                expected_label="语法错误",
                gold_contexts=["Python 用缩进表示代码块"]
            ),

            # 逻辑错误：off-by-one
            DiagnosticTestCase(
                test_id="diag_010",
                student_answer="range(5) 产生 1,2,3,4,5",
                correct_answer="range(5) 产生 0,1,2,3,4",
                question_text="range(5) 会产生哪些数字？",
                expected_error_type="logic_error",
                expected_label="逻辑错误",
                gold_contexts=["range 从 0 开始", "range 不包含结束值"]
            ),

            # 计算错误：运算符优先级
            DiagnosticTestCase(
                test_id="diag_011",
                student_answer="2 + 3 * 4 = 20",
                correct_answer="2 + 3 * 4 = 14",
                question_text="2 + 3 * 4 的结果是多少？",
                expected_error_type="calculation_error",
                expected_label="计算错误",
                gold_contexts=["乘法优先级高于加法"]
            ),

            # 阅读理解：忽略返回值
            DiagnosticTestCase(
                test_id="diag_012",
                student_answer="list.sort() 返回排序后的新列表",
                correct_answer="list.sort() 原地排序，返回 None",
                question_text="list.sort() 的返回值是什么？",
                expected_error_type="reading_comprehension",
                expected_label="阅读理解问题",
                gold_contexts=["sort() 原地修改列表", "sorted() 返回新列表"]
            ),

            # 知识缺失：生成器
            DiagnosticTestCase(
                test_id="diag_013",
                student_answer="不知道什么是生成器",
                correct_answer="生成器用 yield 逐个产生值，惰性求值",
                question_text="Python 生成器是什么？",
                expected_error_type="missing_knowledge",
                expected_label="知识缺失",
                gold_contexts=["yield 关键字定义生成器", "生成器是惰性迭代器"]
            ),

            # 概念混淆：list.sort vs sorted
            DiagnosticTestCase(
                test_id="diag_014",
                student_answer="sort 和 sorted 完全一样",
                correct_answer="sort 原地修改，sorted 返回新列表",
                question_text="sort() 和 sorted() 有什么区别？",
                expected_error_type="conceptual_confusion",
                expected_label="概念混淆",
                gold_contexts=["sort 是列表方法", "sorted 是内置函数"]
            ),
        ]
        return self.test_cases
    
    def evaluate(self, predicted_result: dict[str, Any]) -> DiagnosticResult:
        """
        评估单次诊断结果。
        
        Returns:
            DiagnosticResult with correctness flags
        """
        return DiagnosticResult(
            test_case=predicted_result.get("test_case"),
            predicted_type=predicted_result.get("predicted_type", "unknown"),
            predicted_label=predicted_result.get("predicted_label", "未知错误"),
            confidence=predicted_result.get("confidence", 0.0),
            type_correct=predicted_result.get("type_correct", False),
            label_correct=predicted_result.get("label_correct", False),
            error=predicted_result.get("error")
        )


class RAGASDiagnosticPipeline:
    """完整的 RAGAS 诊断评估管线。"""
    
    def __init__(self, error_analyzer):
        self.analyzer = error_analyzer
        self.evaluator = DiagnosticEvaluator()
    
    def run_full_evaluation(
        self,
        *,
        graph_data: dict[str, Any] | None = None,
        robustness_score: float | None = None,
    ) -> dict[str, Any]:
        """运行诊断评估，并输出可离线复现的扩展指标。

        ``graph_data`` 和 ``robustness_score`` 是可选的：诊断单测不需要真实
        TutorStore；综合评估脚本可以注入知识图谱和对抗测试结果。
        """
        test_cases = self.evaluator.build_test_suite()
        results: list[DiagnosticResult] = []
        remediation_rows: list[tuple[DiagnosticTestCase, dict[str, Any]]] = []

        for tc in test_cases:
            predicted = self.analyzer.classify_error(
                question_text=tc.question_text,
                student_answer=tc.student_answer,
                correct_answer=tc.correct_answer,
                explanation=" ".join(tc.gold_contexts[:2]) if tc.gold_contexts else None
            )
            result = self.evaluator.evaluate({
                "test_case": tc,
                "predicted_type": predicted["error_type"],
                "predicted_label": predicted["error_label"],
                "confidence": predicted["confidence"],
                "type_correct": predicted["error_type"] == tc.expected_error_type,
                "label_correct": predicted["error_label"] == tc.expected_label
            })
            results.append(result)
            remediation_rows.append((tc, predicted))

        tp = sum(1 for r in results if r.type_correct)
        fp = sum(1 for r in results if not r.type_correct and r.predicted_type != "unknown")
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / len(results) if results else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        per_type: dict[str, dict[str, int]] = {}
        for r in results:
            etype = r.predicted_type
            per_type.setdefault(etype, {"correct": 0, "total": 0})
            per_type[etype]["total"] += 1
            if r.type_correct:
                per_type[etype]["correct"] += 1

        failed_cases = [
            {
                "test_id": r.test_case.test_id,
                "expected": r.test_case.expected_label,
                "predicted": r.predicted_label,
                "question": r.test_case.question_text[:50]
            }
            for r in results if not r.type_correct
        ]

        coverage = self._misconception_coverage(test_cases)
        remediation = self._remediation_relevance(remediation_rows)
        path = self._path_reasonableness(graph_data)
        dimensions = {
            "error_classification": round(tp / len(results), 3) if results else 0.0,
            "misconception_coverage": coverage["score"],
            "remediation_relevance": remediation["score"],
            "path_reasonableness": path["score"] if path is not None else None,
            "robustness": round(float(robustness_score), 3) if robustness_score is not None else None,
        }

        return {
            "accuracy": round(tp / len(results), 3) if results else 0.0,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "total_cases": len(results),
            "per_type_breakdown": {k: v["correct"] / max(v["total"], 1)
                                   for k, v in per_type.items()},
            "failed_cases": failed_cases[:5],
            "misconception_coverage": coverage,
            "remediation_relevance": remediation,
            "path_reasonableness": path,
            "robustness_score": dimensions["robustness"],
            "dimensions": dimensions,
            "ragas_used": self._check_ragas_availability(),
            "ragas_version": self._get_ragas_version(),
            "timestamp": self._get_timestamp()
        }

    def _misconception_coverage(self, cases: list[DiagnosticTestCase]) -> dict[str, Any]:
        taxonomy = self.analyzer.taxonomy
        counts = {key: 0 for key in taxonomy}
        for case in cases:
            if case.expected_error_type in counts:
                counts[case.expected_error_type] += 1
        covered = [key for key, count in counts.items() if count > 0]
        return {
            "score": round(len(covered) / len(counts), 3) if counts else 0.0,
            "covered_types": covered,
            "total_types": len(counts),
            "per_type_case_counts": counts,
        }

    def _remediation_relevance(
        self, rows: list[tuple[DiagnosticTestCase, dict[str, Any]]]
    ) -> dict[str, Any]:
        scores: list[float] = []
        for case, predicted in rows:
            hint = str(predicted.get("remediation_hint") or "")
            expected = self.analyzer.taxonomy.get(case.expected_error_type, {})
            base = self.analyzer._generate_remediation_hint(case.expected_error_type, [])
            if hint.startswith(base):
                scores.append(1.0)
            elif hint and any(keyword in hint for keyword in expected.get("keywords", [])):
                scores.append(0.5)
            else:
                scores.append(0.0)
        return {
            "score": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "total_cases": len(scores),
            "relevant_cases": sum(score >= 0.5 for score in scores),
        }

    @staticmethod
    def _path_reasonableness(graph_data: dict[str, Any] | None) -> dict[str, Any] | None:
        if graph_data is None:
            return None
        path = graph_data.get("recommended_path") or []
        positions = {item.get("topic_id"): index for index, item in enumerate(path)}
        edges = [edge for edge in graph_data.get("edges", [])
                 if edge.get("type") == "prerequisite"]
        checks = 0
        satisfied = 0
        violations = []
        for edge in edges:
            source, target = edge.get("from"), edge.get("to")
            if source not in positions or target not in positions:
                continue
            checks += 1
            if positions[source] < positions[target]:
                satisfied += 1
            else:
                violations.append({"prerequisite": source, "topic": target})
        return {
            "score": round(satisfied / checks, 3) if checks else 1.0,
            "path_length": len(path),
            "prerequisite_checks": checks,
            "violations": violations,
        }

    
    def _check_ragas_availability(self) -> bool:
        """检查 RAGAS 是否可用。"""
        try:
            import ragas
            return True
        except ImportError:
            return False
    
    def _get_ragas_version(self) -> str:
        """获取 RAGAS 版本。"""
        try:
            import ragas
            return ragas.__version__
        except Exception:
            return "N/A"
    
    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def run_diagnostic_eval(
    output_path: str = "",
    *,
    graph_data: dict[str, Any] | None = None,
    robustness_score: float | None = None,
) -> dict[str, Any]:
    """
    运行诊断评估并输出报告。

    Args:
        output_path: 报告输出路径（可选）
        graph_data: 知识图谱数据（含 recommended_path），用于路径合理性评估
        robustness_score: 对抗鲁棒性指数（由对抗测试管线注入）

    Returns:
        评估报告字典
    """
    from app.services.tutor.error_analyzer import get_error_analyzer

    analyzer = get_error_analyzer()
    pipeline = RAGASDiagnosticPipeline(analyzer)
    report = pipeline.run_full_evaluation(
        graph_data=graph_data,
        robustness_score=robustness_score,
    )
    
    if output_path:
        import json
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Diagnostic report saved to {output_path}")
    
    return report


if __name__ == "__main__":
    # 命令行直接运行
    report = run_diagnostic_eval()
    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))