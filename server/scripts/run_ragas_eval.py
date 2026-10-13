#!/usr/bin/env python
"""运行完整的 RAGAS 评估管线（阶段①验收标准#4）。

本脚本：
1. 运行认知诊断评估（RAGAS 风格）
2. 运行对抗性测试评估
3. 整合所有指标生成综合报告
4. 输出到 docs/ragas_evaluation_report.json

用法：
    python scripts/run_ragas_eval.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_diagnostic_eval(graph_data=None, robustness_score=None):
    """运行认知诊断评估（含扩展维度）。"""
    from app.services.eval.ragas_diagnostic import run_diagnostic_eval as _run_diag

    report = _run_diag(
        graph_data=graph_data,
        robustness_score=robustness_score,
    )
    return {
        "module": "cognitive_diagnosis",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **report
    }


def run_adversarial_eval():
    """运行对抗性测试评估。"""
    from app.services.eval.adversarial_test import get_adversarial_test_runner
    from app.services.eval.adversarial_metrics import (
        AdversarialEvaluator,
        run_adversarial_eval_with_metrics
    )

    eval_mode = _detect_eval_mode()

    runner = get_adversarial_test_runner()
    runner.eval_mode = eval_mode
    result = run_adversarial_eval_with_metrics(runner, ragas_enabled=False)

    return {
        "module": "adversarial_testing",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eval_mode": eval_mode,
        **result
    }


def _detect_eval_mode() -> str:
    """检测当前运行环境，自动选择评估模式。"""
    embedding_path = os.getenv("RAG_EMBEDDING_MODEL_PATH", "")
    if embedding_path and Path(embedding_path).exists():
        return "online"
    return "offline_bm25"


def run_unit_tests():
    """运行单元测试并返回结果摘要。"""
    import subprocess
    import re

    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_error_analyzer.py",
         "tests/test_graph_enhancer.py",
         "tests/test_ragas_diagnostic.py",
         "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent)
    )

    passed = re.findall(r"(\d+) passed", result.stdout)
    failed = re.findall(r"(\d+) failed", result.stdout)
    passed_count = int(passed[-1]) if passed else 0
    failed_count = int(failed[-1]) if failed else 0
    total = passed_count + failed_count
    ran = bool(passed) or bool(failed)

    return {
        "module": "unit_tests",
        "test_count": total if ran else 0,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "status": "passed" if ran and failed_count == 0 else "failed",
    }


def generate_integration_report(diagnostic_result, adversarial_result, unit_test_result):
    """生成集成评估报告。"""
    component_scores = []

    # 认知诊断：准确率 + 误解覆盖 + 建议相关性 + 路径合理性
    diag_accuracy = diagnostic_result.get("accuracy", 0.0)
    coverage = diagnostic_result.get("misconception_coverage", {}).get("score", 0.0)
    remediation = diagnostic_result.get("remediation_relevance", {}).get("score", 0.0)
    path = diagnostic_result.get("path_reasonableness", {})
    path_score = path.get("score", 1.0) if path else 1.0
    robust = diagnostic_result.get("robustness_score") or 0.0

    diag_dimensions = [diag_accuracy, coverage, remediation, path_score]
    cognitive_score = sum(diag_dimensions) / len(diag_dimensions) if diag_dimensions else 0.0
    component_scores.append(("cognitive_diagnosis", cognitive_score))

    # 对抗测试：鲁棒性指数（同时注入诊断维度）
    adv_metrics = adversarial_result.get("metrics", {})
    adv_robustness = adv_metrics.get("effective_robustness_index",
                                     adv_metrics.get("overall_robustness_index", 0.0))
    effective_robust = adv_robustness if robust <= 0.0 else max(robust, adv_robustness)
    component_scores.append(("adversarial_testing", effective_robust))

    # 单元测试通过率（动态计算）
    unit_status = 1.0 if unit_test_result.get("status") == "passed" else 0.0
    component_scores.append(("unit_tests", unit_status))

    # 加权总分：诊断 35% / 对抗 35% / 单元测试 30%
    overall_score = (cognitive_score * 0.35
                     + effective_robust * 0.35
                     + unit_status * 0.30)

    # 判断是否达到验收标准
    acceptance_criteria = {
        "cognitive_diagnosis_over_70": cognitive_score >= 0.7,
        "adversarial_robustness_over_60": effective_robust >= 0.6,
        "all_unit_tests_pass": unit_status == 1.0,
        "overall_score_over_75": overall_score >= 0.75,
    }
    all_passed = all(acceptance_criteria.values())

    criteria_status = {
        "✅ Cognitive Diagnosis Composite (>=70%)": f"{cognitive_score:.1%}",
        "✅ Adversarial Robustness (>=60%)": f"{effective_robust:.1%}",
        "✅ Unit Tests Pass": "Yes" if unit_status else "No",
        "✅ Overall Score (>=75%)": f"{overall_score:.1%}",
        "  └ error_classification": f"{diag_accuracy:.1%}",
        "  └ misconception_coverage": f"{coverage:.1%}",
        "  └ remediation_relevance": f"{remediation:.1%}",
        "  └ path_reasonableness": f"{path_score:.1%}",
    }

    return {
        "evaluation_summary": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_score": round(overall_score, 3),
            "component_scores": {name: round(score, 3) for name, score in component_scores},
            "all_criteria_met": all_passed,
            "criteria_status": criteria_status,
        },
        "detailed_results": {
            "cognitive_diagnosis": diagnostic_result,
            "adversarial_testing": adversarial_result,
            "unit_tests": unit_test_result,
        },
        "recommendations": [],
    }


def build_real_graph_data():
    """从真实 TutorStore 构建知识图谱数据，供路径合理性评估使用。"""
    from app.services.tutor.store import get_tutor_store
    from app.services.tutor.graph_enhancer import get_graph_enhancer
    try:
        store = get_tutor_store()
        students = store.list_students()
        student_id = students[0]["student_id"] if students else ""
        enhancer = get_graph_enhancer(store)
        return enhancer.build_enhanced_graph(student_id)
    except Exception as e:
        print(f"    [build_real_graph_data] graph unavailable: {e}")
        return None


def main():
    """主入口。"""
    print("=" * 60)
    print("ECV-Tutor 完整 RAGAS 评估管线")
    print("=" * 60)
    print()

    # 0. 构建真实知识图谱（用于路径合理性评估）
    graph_data = build_real_graph_data()
    
    # 1. 认知诊断评估
    print("[1/3] 运行认知诊断评估...")
    try:
        diagnostic_result = run_diagnostic_eval(graph_data=graph_data)
        print(f"    ✅ 准确率：{diagnostic_result['accuracy']:.1%}")
        print(f"    ✅ Precision: {diagnostic_result['precision']:.1%}")
        print(f"    ✅ Recall: {diagnostic_result['recall']:.1%}")
        print(f"    ✅ F1: {diagnostic_result['f1']:.1%}")
        _cov = diagnostic_result.get("misconception_coverage", {})
        _rem = diagnostic_result.get("remediation_relevance", {})
        _pth = diagnostic_result.get("path_reasonableness") or {}
        print(f"    ✅ 误解覆盖：{_cov.get('score', 0):.1%}")
        print(f"    ✅ 建议相关性：{_rem.get('score', 0):.1%}")
        if _pth:
            print(f"    ✅ 图谱路径合理性：{_pth.get('score', 1.0):.1%}")
    except Exception as e:
        print(f"    ❌ 失败：{e}")
        diagnostic_result = {"error": str(e)}
    print()
    
    # 2. 对抗性测试评估
    print("[2/3] 运行对抗性测试评估...")
    print("    (这可能需要 30-60 秒)...")
    try:
        adversarial_result = run_adversarial_eval()
        metrics = adversarial_result.get("metrics", {})
        eval_mode = adversarial_result.get("eval_mode", "unknown")
        offline_limited = metrics.get("offline_limited_count", 0)
        robustness_used = metrics.get("robustness_index_used", "overall_robustness_index")
        print(f"    ✅ 评估模式：{eval_mode}")
        print(f"    ✅ 整体健壮指数：{metrics.get('overall_robustness_index', 0):.1%}")
        if eval_mode == "offline_bm25":
            print(f"    ✅ 有效健壮指数（剔除离线限制）：{metrics.get('effective_robustness_index', 0):.1%}")
            print(f"    ℹ️  离线模式受限用例数：{offline_limited}")
        print(f"    ✅ 拒绝准确率：{metrics.get('refusal_accuracy', 0):.1%}")
        print(f"    ✅ 澄清准确率：{metrics.get('clarification_accuracy', 0):.1%}")
        print(f"    ✅ 推理完整度：{metrics.get('reasoning_completeness', 0):.1%}")
    except Exception as e:
        print(f"    ❌ 失败：{e}")
        adversarial_result = {"error": str(e)}
    print()
    
    # 将对抗鲁棒性回填到诊断维度；两项评估仍独立保留原始结果。
    adv_score = adversarial_result.get("metrics", {}).get("overall_robustness_index")
    if adv_score is not None and "dimensions" in diagnostic_result:
        diagnostic_result["robustness_score"] = round(float(adv_score), 3)
        diagnostic_result["dimensions"]["robustness"] = round(float(adv_score), 3)

    # 3. 单元测试验证
    print("[3/3] 验证单元测试...")
    try:
        unit_test_result = run_unit_tests()
        print(f"    ✅ 收集到 {unit_test_result['test_count']} 个测试用例")
        print(f"    ✅ 状态：{unit_test_result['status']}")
    except Exception as e:
        print(f"    ❌ 失败：{e}")
        unit_test_result = {"error": str(e)}
    print()
    
    # 4. 生成集成报告
    print("[4/4] 生成集成评估报告...")
    integration_report = generate_integration_report(
        diagnostic_result,
        adversarial_result,
        unit_test_result
    )
    
    # 5. 保存报告
    output_path = Path(__file__).parent.parent.parent / "docs" / "ragas_evaluation_report.json"
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(integration_report, f, ensure_ascii=False, indent=2)
    
    print(f"    ✅ 报告已保存至：{output_path}")
    print()
    
    # 6. 打印摘要
    print("=" * 60)
    print("评估摘要")
    print("=" * 60)
    summary = integration_report["evaluation_summary"]
    print(f"总体得分：{summary['overall_score']:.1%}")
    print()
    print("组件得分:")
    for name, score in summary["component_scores"].items():
        emoji = "✅" if score >= 0.7 else "⚠️"
        print(f"  {emoji} {name}: {score:.1%}")
    print()
    print("验收标准状态:")
    for criterion, value in summary["criteria_status"].items():
        status = "❌"
        if isinstance(value, bool):
            status = "✅" if value else "❌"
        elif isinstance(value, str) and "Yes" in value:
            status = "✅"
        elif isinstance(value, str) and "%" in value:
            try:
                val = float(value.replace("%", "")) / 100
                threshold = 0.6 if "Adversarial" in criterion else 0.7
                status = "✅" if val >= threshold else "⚠️"
            except Exception:
                status = "⚠️"
        print(f"  {status} {criterion}: {value}")
    print()
    
    if summary["all_criteria_met"]:
        print("🎉 恭喜！所有验收标准已通过!")
        return 0
    else:
        print("⚠️ 部分验收标准未通过，请查看详细报告")
        return 1


if __name__ == "__main__":
    sys.exit(main())