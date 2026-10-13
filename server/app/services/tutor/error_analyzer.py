"""认知诊断与错误模式识别模块。

增强版错误分析：
  - 错误类型分类（概念混淆、计算错误、阅读理解等）
  - 误解分类法（misconception taxonomy）
  - 错误模式可视化数据生成
  
基于 Kloks et al. (2023) 的研究，错误类型分析比单纯的正确率更能预测学习进展。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)
from app.services.observability.langfuse_client import langfuse_observed

# 误解分类法（基于教育数据挖掘文献）
MISCONCEPTION_TAXONOMY = {
    "conceptual_confusion": {
        "label": "概念混淆",
        "description": "将两个相似但不同的概念混淆",
        "keywords": ["混淆", "区别", "不同", "类似", "相似"],
        "examples": [
            "把 list 和 tuple 混用",
            "= 和 == 的区别不清楚",
            "global 和 local 变量作用域混淆"
        ]
    },
    "syntax_error": {
        "label": "语法错误",
        "description": "对编程语言语法规则理解错误",
        "keywords": ["语法", "格式", "冒号", "缩进", "括号"],
        "examples": [
            "忘记冒号",
            "缩进错误",
            "括号不匹配"
        ]
    },
    "logic_error": {
        "label": "逻辑错误",
        "description": "程序能运行但逻辑不正确",
        "keywords": ["逻辑", "条件", "循环", "判断", "流程"],
        "examples": [
            "循环条件永远为真",
            "if-else 分支写反",
            " off-by-one 错误"
        ]
    },
    "calculation_error": {
        "label": "计算错误",
        "description": "数值计算或表达式求值错误",
        "keywords": ["计算", "运算", "结果", "等于", "数值"],
        "examples": [
            "运算符优先级错误",
            "整数除法误用",
            "浮点数精度问题"
        ]
    },
    "reading_comprehension": {
        "label": "阅读理解问题",
        "description": "未能正确理解题目或文档描述",
        "keywords": ["理解", "题意", "描述", "要求", "含义"],
        "examples": [
            "没读懂函数说明",
            "忽略边界条件",
            "误解输入输出格式"
        ]
    },
    "missing_knowledge": {
        "label": "知识缺失",
        "description": "缺乏必要的基础知识",
        "keywords": ["不知道", "没学过", "不会", "不懂", "什么是"],
        "examples": [
            "不了解装饰器语法",
            "不知道列表推导式",
            "未掌握递归概念"
        ]
    }
}


class ErrorAnalyzer:
    """错误模式分析器。"""
    
    def __init__(self):
        self.taxonomy = MISCONCEPTION_TAXONOMY
    
    @langfuse_observed("error_analyzer.classify")
    def classify_error(self, question_text: str, student_answer: str, 
                      correct_answer: str, explanation: str | None = None) -> dict[str, Any]:
        """分析错误类型并返回分类结果。"""
        # 组合分析文本
        analysis_text = f"{question_text} {student_answer} {correct_answer}"
        if explanation:
            analysis_text += f" {explanation}"
        
        analysis_text_lower = analysis_text.lower()
        
        # 基于关键词的分类
        scores: dict[str, float] = {}
        matched_keywords: dict[str, list[str]] = {}
        
        for error_type, info in self.taxonomy.items():
            keywords = info["keywords"]
            matches = [kw for kw in keywords if kw in analysis_text_lower]
            if matches:
                scores[error_type] = len(matches) / len(keywords)
                matched_keywords[error_type] = matches
        
        # 如果没有关键词匹配，使用启发式规则
        if not scores:
            scores = self._heuristic_classify(question_text, student_answer, correct_answer)
        
        # 确定主要错误类型
        if scores:
            primary_type = max(scores.items(), key=lambda x: x[1])
            error_type = primary_type[0]
            confidence = primary_type[1]
        else:
            error_type = "unknown"
            confidence = 0.0
        
        # 查找相似的误解案例
        similar = self._find_similar_misconceptions(error_type, student_answer, correct_answer)
        
        # 生成复习建议
        remediation = self._generate_remediation_hint(error_type, matched_keywords.get(error_type, []))
        
        return {
            "error_type": error_type,
            "error_label": self.taxonomy.get(error_type, {}).get("label", "未知错误"),
            "confidence": round(confidence, 2),
            "keywords_matched": matched_keywords.get(error_type, []),
            "similar_misconceptions": similar[:3],
            "remediation_hint": remediation,
            "all_scores": scores
        }
    
    def _heuristic_classify(self, question: str, answer: str, correct: str) -> dict[str, float]:
        """启发式分类规则（当关键词匹配失败时使用）。"""
        scores = {}
        
        # 检查是否是选择题的简单错误
        if len(answer.strip()) == 1 and len(correct.strip()) == 1:
            # 单字母答案，可能是记忆性错误
            scores["missing_knowledge"] = 0.6
        
        # 检查是否涉及计算
        calc_patterns = [r'\d+\s*[+\-*/]\s*\d+', r'=\s*\d+', r'结果.*\d+']
        if any(re.search(p, question + answer) for p in calc_patterns):
            scores["calculation_error"] = 0.5
        
        # 检查是否涉及代码/语法
        if any(c in answer for c in ['()', '{}', '[]', ':', 'indent']):
            scores["syntax_error"] = 0.4
        
        return scores
    
    def _find_similar_misconceptions(self, error_type: str, 
                                     student_answer: str, 
                                     correct_answer: str) -> list[dict[str, str]]:
        """查找相似的已知误解案例。"""
        info = self.taxonomy.get(error_type, {})
        examples = info.get("examples", [])
        
        return [
            {"example": ex, "type": error_type}
            for ex in examples[:3]
        ]
    
    def _generate_remediation_hint(self, error_type: str, keywords: list[str]) -> str:
        """生成个性化复习建议。"""
        hints = {
            "conceptual_confusion": "建议对比学习相关概念，制作概念对照表，重点区分易混点。",
            "syntax_error": "建议多做语法练习，使用代码编辑器的高亮提示功能。",
            "logic_error": "建议画流程图梳理逻辑，逐步调试验证每一步的执行结果。",
            "calculation_error": "建议手算验算关键步骤，注意运算符优先级和结合性。",
            "reading_comprehension": "建议慢读题干，划出关键词，确认理解后再作答。",
            "missing_knowledge": "建议先补习基础知识，观看入门视频，做基础练习题。",
            "unknown": "建议回顾相关章节，重新阅读教材和笔记。"
        }
        
        base_hint = hints.get(error_type, hints["unknown"])
        
        if keywords:
            return f"{base_hint} 关注要点：{', '.join(keywords)}"
        return base_hint
    
    @langfuse_observed("error_analyzer.analyze_quiz")
    def analyze_quiz_errors(self, quiz_results: list[dict[str, Any]]) -> dict[str, Any]:
        """分析整套测验的错误模式。"""
        error_counts: dict[str, int] = {}
        topic_errors: dict[str, dict[str, int]] = {}
        
        for result in quiz_results:
            if result.get("is_correct"):
                continue
                
            classification = self.classify_error(
                question_text=result.get("question", ""),
                student_answer=result.get("student_answer", ""),
                correct_answer=result.get("correct_answer", ""),
                explanation=result.get("explanation")
            )
            
            error_type = classification["error_type"]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
            
            # 按主题统计
            for tid in result.get("topic_ids", []):
                if tid not in topic_errors:
                    topic_errors[tid] = {}
                topic_errors[tid][error_type] = topic_errors[tid].get(error_type, 0) + 1
        
        # 找出主要误解
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        
        # 生成推荐
        recommended = []
        for error_type, count in sorted_errors[:3]:
            label = self.taxonomy.get(error_type, {}).get("label", error_type)
            recommended.append({
                "error_type": error_type,
                "label": label,
                "count": count,
                "percentage": round(count / max(sum(error_counts.values()), 1) * 100, 1)
            })
        
        return {
            "error_distribution": error_counts,
            "topic_error_patterns": topic_errors,
            "strongest_misconceptions": recommended,
            "total_errors": sum(error_counts.values()),
            "analysis_timestamp": self._get_timestamp()
        }
    
    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


_analyzer: ErrorAnalyzer | None = None


def get_error_analyzer() -> ErrorAnalyzer:
    """获取全局错误分析器实例。"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ErrorAnalyzer()
    return _analyzer