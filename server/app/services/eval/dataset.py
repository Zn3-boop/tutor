"""Knowledge-base-driven evaluation test set.

Two artifact kinds, kept strictly separate:

1. **QA test set** (`build_comprehensive_test_set`): real questions with
   independent gold answers. Sources: hand-written builtin cases, synthesis
   cases, bilingual cases, and the LLM-generated on-material bank
   (``docs/llm_generated_on_material.json``) which has been reviewed and
   integrated. These are the cases used to report faithfulness / relevancy /
   refusal — a query must NEVER equal its own expected answer.

2. **Retrieval self-check set** (`build_retrieval_selfcheck_set`): one case per
   KB unit where the query is the unit's first sentence and the gold is that
   unit's own chunk id. This measures whether BM25 can find the exact source
   chunk (recall@k / context recall) — it is a retrieval probe, NOT a QA case,
   and must never be folded into faithfulness/relevancy numbers.

Off-material distractor queries that the grounded tutor must refuse are part of
the QA test set.
"""
from __future__ import annotations
import json
import logging
import os
import re
import hashlib
from typing import Any
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)

# ========== Mock TutorStore (如果你的项目已有TutorStore，可以删掉这个mock) ==========
class TutorStore:
    """Mock TutorStore for type checking & local test run."""
    def list_units(self):
        return []
    def list_topics_by_id(self) -> dict:
        return {}
# =============================================================================

# Off-material queries that must NOT be answered (refusal-rate ground truth).
_OFF_MATERIAL_QUERIES = [
    ("What is the capital of France?", "general", "geography"),
    ("How do you cook pasta from scratch?", "general", "cooking"),
    ("Who wrote the Iliad?", "general", "literature"),
    ("Explain how to fix a bicycle chain.", "general", "repair"),
    ("What is the weather like in Tokyo today?", "general", "weather"),
    ("How do I invest in Bitcoin?", "general", "finance"),
    ("Who won the FIFA World Cup in 2022?", "general", "sports"),
    ("What is the population of Mars?", "general", "space"),
]

# Bilingual off-material queries (English + Chinese) for mixed-language support
_OFF_MATERIAL_QUERIES_BILINGUAL = [
    ("What is the capital of France?", "general", "geography"),
    ("法国的首都是哪里？", "general", "geography"),
    ("How do you cook pasta from scratch?", "general", "cooking"),
    ("怎么从零开始煮意大利面？", "general", "cooking"),
    ("What are the strategies for investing in the stock market?", "general", "finance"),
    ("股市投资策略有哪些？", "general", "finance"),
    ("How do I treat a common cold?", "general", "healthcare"),
    ("普通感冒该如何治疗？", "general", "healthcare"),
    ("What is the rules of basketball?", "general", "sports"),
    ("篮球的规则是什么？", "general", "sports"),
    ("How do you repair a leaking roof?", "general", "repair"),
    ("屋顶漏水该如何修理？", "general", "repair"),
    ("What is the theory of relativity?", "general", "astronomy"),
    ("相对论是什么？", "general", "astronomy"),
    ("Who was the first emperor of China?", "general", "history"),
    ("中国第一个皇帝是谁？", "general", "history"),
    ("How do you bake a chocolate cake?", "general", "cooking"),
    ("如何烤巧克力蛋糕？", "general", "cooking"),
    ("What is the best way to learn a new language?", "general", "education"),
    ("学习新语言的最佳方法是什么？", "general", "education"),
    ("How do I apply for a passport?", "general", "travel"),
    ("如何申请护照？", "general", "travel"),
    ("What is the biggest ocean on Earth?", "general", "geography"),
    ("地球上最大的海洋是什么？", "general", "geography"),
    ("How do I fix a flat tire?", "general", "repair"),
    ("如何修理爆胎？", "general", "repair"),
    ("What are the symptoms of influenza?", "general", "healthcare"),
    ("流感的症状有哪些？", "general", "healthcare"),
    ("How do you write a business plan?", "general", "business"),
    ("如何写商业计划书？", "general", "business"),
    ("What is the speed of light?", "general", "physics"),
    ("光速是多少？", "general", "physics"),
    ("Who painted the Mona Lisa?", "general", "art"),
    ("蒙娜丽莎是谁画的？", "general", "art"),
    ("What is the best way to save money?", "general", "finance"),
    ("如何储蓄最多的钱？", "general", "finance"),
    ("How do I change a light bulb?", "general", "repair"),
    ("如何更换灯泡？", "general", "repair"),
    ("How is the history of the Olympics?", "general", "sports"),
    ("奥运会的历史是什么？", "general", "sports"),
    ("How do you make homemade bread?", "general", "cooking"),
    ("如何自制面包？", "general", "cooking"),
    ("How do you troubleshoot a computer?", "general", "tech"),
    ("如何排查电脑故障？", "general", "tech"),
    ("What is the meaning of life?", "general", "philosophy"),
    ("生命的意义是什么？", "general", "philosophy"),
    ("What are the laws of thermodynamics?", "general", "physics"),
    ("热力学定律是什么？", "general", "physics"),
    ("What is the tallest mountain in the world?", "general", "geography"),
    ("世界上最高的山是什么？", "general", "geography"),
    ("How do you play chess?", "general", "games"),
    ("如何下国际象棋？", "general", "games"),
    ("What is the GDP of Japan?", "general", "economics"),
    ("日本的GDP是多少？", "general", "economics"),
    ("How do you train a dog?", "general", "pets"),
    ("如何训练狗？", "general", "pets"),
    ("What is the best smartphone on the market?", "general", "technology"),
    ("市场上最好的智能手机是什么？", "general", "technology"),
    ("How do you knit a scarf?", "general", "crafts"),
    ("如何织围巾？", "general", "crafts"),
    ("What are the best plants for indoor gardening?", "general", "gardening"),
    ("室内园艺最好的植物是什么？", "general", "gardening"),
    ("Who wrote Romeo and Juliet?", "general", "literature"),
    ("《罗密欧与朱丽叶》是谁写的？", "general", "literature"),
    ("What is the distance from Earth to the Moon?", "general", "astronomy"),
    ("地球到月球的距离是多少？", "general", "astronomy"),
    ("How do you start a startup company?", "general", "business"),
    ("如何创办初创公司？", "general", "business"),
    ("What causes earthquakes?", "general", "geology"),
    ("地震的原因是什么？", "general", "geology"),
    ("How do you meditate properly?", "general", "wellness"),
    ("如何正确冥想？", "general", "wellness"),
    ("What is the history of the Internet?", "general", "history"),
    ("互联网的历史是什么？", "general", "history"),
    ("How do you tune a guitar?", "general", "music"),
    ("如何调吉他？", "general", "music"),
    ("What is the best diet for weight loss?", "general", "healthcare"),
    ("减肥最好的饮食是什么？", "general", "healthcare"),
]

# Extended off-material queries for higher refusal rate coverage
_OFF_MATERIAL_QUERIES_EXTENDED = [
    ("What is the best recipe for chocolate cake?", "general", "cooking"),
    ("How to fix a bicycle chain?", "general", "repair"),
    ("Explain Bitcoin investment strategies.", "general", "finance"),
    ("Who won the 2022 FIFA World Cup?", "general", "sports"),
    ("How to fix a broken phone screen?", "general", "repair"),
    ("How to invest in cryptocurrency?", "general", "finance"),
    ("What is the best hotel in Paris?", "general", "travel"),
    ("巴黎最好的酒店是哪家？", "general", "travel"),
    ("How do you perform CPR?", "general", "healthcare"),
    ("如何进行心肺复苏？", "general", "healthcare"),
    ("What is the exchange rate of USD to EUR?", "general", "economics"),
    ("美元兑欧元的汇率是多少？", "general", "economics"),
    ("How do you paint a portrait?", "general", "art"),
    ("如何画肖像画？", "general", "art"),
    ("What are the rules of tennis?", "general", "sports"),
    ("网球的规则是什么？", "general", "sports"),
    ("How do you build a bookshelf?", "general", "crafts"),
    ("如何做书架？", "general", "crafts"),
    ("What is the population of India?", "general", "geography"),
    ("印度的人口是多少？", "general", "geography"),
]

# Domain-specific refusal patterns for better off-material detection
_DOMAIN_PATTERNS = {
    "geography": [r"\b(capital of|population of|weather in|located in)\b"],
    "cooking": [r"\b(recipe for|how to cook|ingredients for|make a)\b"],
    "literature": [r"\b(who wrote|author of|novel by|wrote the)\b"],
    "repair": [r"\b(how to fix|repair|breakdown|mechanic)\b"],
    "finance": [r"\b(invest|bitcoin|crypto|stock|market)\b"],
    "sports": [r"\b(olympics|world cup|nba|fifa|score)\b"],
}

# Multi-source synthesis query templates
_SYNTHESIS_QUERIES = [
    {
        "query": "Explain how variables, functions, and control flow work together in Python.",
        "expected_answer": "Variables store data, functions organize code, and control flow directs execution.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "hard",
        "topic_ids": ["t_variable", "t_functions", "t_control"],
        "source_ids": [],
        "query_type": "synthesis",
    },
    {
        "query": "对比Python中列表和字典的异同点。",
        "expected_answer": "列表是有序可变序列，字典是键值对映射结构。",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "medium",
        "topic_ids": ["t_lists", "t_dicts"],
        "source_ids": [],
        "query_type": "bilingual_comparison",
    },
]

# Pre-defined on-material queries for common CS education topics
# These serve as a reproducible benchmark even before KB ingestion
_BUILTIN_ON_MATERIAL_QUERIES = [
    {
        "query": "What is a variable in Python?",
        "expected_answer": "A variable is a named memory location that stores a value.",
        "expected_doc_ids": [],  # Will be resolved at runtime
        "category": "on-material",
        "difficulty": "easy",
        "topic_ids": ["t_variable"],
        "source_ids": [],
        "query_type": "factual",
    },
    {
        "query": "How does the def keyword define a function?",
        "expected_answer": "The def keyword is followed by the function name and parameters in parentheses.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "easy",
        "topic_ids": ["t_functions"],
        "source_ids": [],
        "query_type": "factual",
    },
    {
        "query": "Explain the difference between a list and a tuple in Python.",
        "expected_answer": "Lists are mutable while tuples are immutable.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "medium",
        "topic_ids": ["t_lists", "t_tuples"],
        "source_ids": [],
        "query_type": "comparison",
    },
    {
        "query": "What is the purpose of the return statement in a function?",
        "expected_answer": "The return statement exits a function and optionally passes back a value.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "easy",
        "topic_ids": ["t_functions"],
        "source_ids": [],
        "query_type": "factual",
    },
    {
        "query": "How do for loops and while loops differ in Python?",
        "expected_answer": "For loops iterate over a sequence, while loops repeat while a condition is true.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "medium",
        "topic_ids": ["t_control"],
        "source_ids": [],
        "query_type": "comparison",
    },
    {
        "query": "What is dictionary comprehension and how is it used?",
        "expected_answer": "Dictionary comprehension creates dictionaries from iterables using a concise syntax.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "hard",
        "topic_ids": ["t_dicts"],
        "source_ids": [],
        "query_type": "conceptual",
    },
    {
        "query": "Explain how exception handling works with try and except.",
        "expected_answer": "Try blocks contain code that might raise exceptions; except blocks handle them.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "medium",
        "topic_ids": ["t_exceptions"],
        "source_ids": [],
        "query_type": "conceptual",
    },
    {
        "query": "What is recursion and when should it be used?",
        "expected_answer": "Recursion is when a function calls itself; useful for problems with recursive structure.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "hard",
        "topic_ids": ["t_functions"],
        "source_ids": [],
        "query_type": "conceptual",
    },
    {
        "query": "How do you open and read a file in Python?",
        "expected_answer": "Use the open() function with 'r' mode and read() or readlines() methods.",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "easy",
        "topic_ids": ["t_files"],
        "source_ids": [],
        "query_type": "procedural",
    },
    {
        "query": "What is the difference between == and is in Python?",
        "expected_answer": "== checks value equality, is checks identity (same object in memory).",
        "expected_doc_ids": [],
        "category": "on-material",
        "difficulty": "medium",
        "topic_ids": ["t_variable"],
        "source_ids": [],
        "query_type": "comparison",
    },
]


def _first_sentence(unit: dict) -> str | None:
    text = (unit.get("text") or "").strip()
    # drop markdown heading lines
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))
    sentences = re.split(r"(?<=[.!?。！？；;])\s+", text)
    for s in sentences:
        s = s.strip()
        if 15 <= len(s) <= 260:
            return s
    return None


def _resolve_builtin_doc_ids(store, builtin_cases: list[dict]) -> list[dict]:
    """Resolve expected_doc_ids for built-in queries by matching topic_ids."""
    resolved = []
    for case in builtin_cases:
        case = dict(case)  # copy
        topic_ids = case.get("topic_ids", [])
        doc_ids = []
        for u in store.list_units():
            unit_topics = set(u.get("topic_ids", []) or [])
            if unit_topics & set(topic_ids):
                cid = u.get("chunk_id") or u.get("unit_id")
                if cid:
                    doc_ids.append(cid)
        case["expected_doc_ids"] = doc_ids[:3]  # limit to top 3
        resolved.append(case)
    return resolved


def build_test_cases(store, use_builtin: bool = True) -> list[dict]:
    """Build [on-material, off-material] cases from the current KB state.

    NOTE: KB-derived first-sentence fragments are NOT QA cases (their gold
    equals the query). They live in the retrieval self-check set via
    ``build_retrieval_selfcheck_set``. This function builds real QA cases:
    builtin + LLM bank + synthesis + bilingual + off-material.
    Args:
        store: TutorStore instance
        use_builtin: Whether to include built-in benchmark queries
    Returns:
        List of test cases with query, expected_answer, expected_doc_ids,
        category, difficulty, topic_ids, source_ids, and query_type.
    """
    cases: list[dict] = []
    # Phase 1: Built-in benchmark queries (reproducible across runs)
    if use_builtin:
        builtin_resolved = _resolve_builtin_doc_ids(store, _BUILTIN_ON_MATERIAL_QUERIES)
        cases.extend(builtin_resolved)
    # Phase 2: Human-reviewed LLM bank + synthesis + bilingual (real QA cases)
    cases.extend(_load_llm_reviewed_cases(store))
    for sq in _SYNTHESIS_QUERIES:
        cases.append(_resolve_query_doc_ids(store, sq))
    cases.extend(_generate_bilingual_queries(store))
    # Phase 3: Off-material queries (must be refused)
    for q, cat, domain in _OFF_MATERIAL_QUERIES:
        cases.append({
            "query": q, "expected_answer": "", "expected_doc_ids": [],
            "category": "off-material", "difficulty": "easy",
            "topic_ids": [], "source_ids": [],
            "query_type": "off-material",
            "domain": domain,
        })
    return cases


# Bilingual on-material query generator
def _generate_bilingual_queries(store: TutorStore) -> list[dict]:
    """Generate bilingual (English + Chinese) on-material queries."""
    topics = store.list_topics_by_id()
    units = store.list_units()
    queries = []

    for topic_id, topic in list(topics.items())[:5]:  # Limit to first 5 topics
        topic_units = [u for u in units if topic_id in u.get("topic_ids", [])]
        if not topic_units:
            continue

        # English query
        eng_query = f"What is {topic.get('name', topic_id)} in Python?"
        queries.append({
            "query": eng_query,
            "expected_answer": f"{topic.get('name', topic_id)} is a concept in Python programming.",
            "expected_doc_ids": [u.get("chunk_id") or u.get("unit_id") for u in topic_units[:2]],
            "category": "on-material",
            "difficulty": "easy",
            "topic_ids": [topic_id],
            "source_ids": [u.get("source_id") for u in topic_units[:2]],
            "query_type": "bilingual_factual",
            "language": "en",
        })

        # Chinese query (translation)
        chn_query = f"Python中的{topic.get('name', topic_id)}是什么？"
        queries.append({
            "query": chn_query,
            "expected_answer": f"{topic.get('name', topic_id)}是Python编程中的一个概念。",
            "expected_doc_ids": [u.get("chunk_id") or u.get("unit_id") for u in topic_units[:2]],
            "category": "on-material",
            "difficulty": "easy",
            "topic_ids": [topic_id],
            "source_ids": [u.get("source_id") for u in topic_units[:2]],
            "query_type": "bilingual_factual",
            "language": "zh",
        })

    return queries


def summarize_dataset(cases: list[dict]) -> dict[str, Any]:
    n_on = sum(1 for c in cases if c.get("category") == "on-material")
    n_off = sum(1 for c in cases if c.get("category") == "off-material")
    topics: set[str] = set()
    query_types: dict[str, int] = {}
    for c in cases:
        topics.update(c.get("topic_ids", []) or [])
        qt = c.get("query_type", "unknown")
        query_types[qt] = query_types.get(qt, 0) + 1
    return {
        "total": len(cases),
        "on_material": n_on,
        "off_material": n_off,
        "topic_coverage": sorted(topics),
        "query_type_distribution": query_types,
    }


# Enhanced summary with language distribution
def summarize_dataset_enhanced(cases: list[dict]) -> dict[str, Any]:
    base_summary = summarize_dataset(cases)
    languages = Counter()
    query_types = Counter()
    domains = Counter()
    for c in cases:
        lang = c.get("language", "en")
        languages[lang] += 1
        qt = c.get("query_type", "unknown")
        query_types[qt] += 1
        domain = c.get("domain", "unknown")
        domains[domain] += 1
    base_summary["language_distribution"] = dict(languages)
    base_summary["domain_distribution"] = dict(domains)
    base_summary["detailed_query_types"] = dict(query_types)
    base_summary["generated_at"] = datetime.now().isoformat()
    return base_summary


# Helper to resolve query doc IDs
def _resolve_query_doc_ids(store, query_template: dict) -> dict:
    """Resolve expected_doc_ids for a query template based on current store state."""
    resolved = query_template.copy()
    topic_ids = resolved.get("topic_ids", [])
    resolved["expected_doc_ids"] = []
    for u in store.list_units():
        if any(tid in u.get("topic_ids", []) for tid in topic_ids):
            cid = u.get("chunk_id") or u["unit_id"]
            if cid not in resolved["expected_doc_ids"]:
                resolved["expected_doc_ids"].append(cid)
    return resolved


_SERVER_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


def _default_test_set_path() -> str:
    """Server/tests/test_set.json — the single reproducible archive location.
    ``__file__`` lives at server/app/services/eval/, so four ``..`` steps land
    on the server root (the app/ and tests/ directories are siblings).
    """
    return os.path.join(_SERVER_ROOT, "tests", "test_set.json")


def save_test_set(cases: list[dict], filepath: str = "") -> str:
    """Save the test set to a JSON file for reproducibility.
    Args:
        cases: List of test cases
        filepath: Optional custom path, defaults to server/tests/test_set.json
    Returns:
        Path to the saved file
    """
    if not filepath:
        filepath = _default_test_set_path()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    summary = summarize_dataset_enhanced(cases)
    output = {
        "version": "2.0",
        "description": "ECV-Tutor QA test set: hand-written + reviewed LLM on-material queries with independent gold answers, plus off-material refusal cases. KB-derived first-sentence fragments are intentionally excluded — they live in the retrieval self-check set (retrieval_selfcheck.json).",
        "summary": summary,
        "cases": cases,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return filepath


def save_retrieval_selfcheck_set(cases: list[dict],
                                 filepath: str = "") -> str:
    """Persist the retrieval self-check set to server/tests/retrieval_selfcheck.json."""
    if not filepath:
        filepath = os.path.join(_SERVER_ROOT, "tests", "retrieval_selfcheck.json")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    output = {
        "version": "1.0",
        "description": "Retrieval self-check set: one case per KB unit (query = the unit's first sentence, gold = that unit's chunk id). Measures recall@k / context recall only — NOT a QA benchmark; query==answer by construction.",
        "summary": summarize_dataset(cases),
        "cases": cases,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return filepath


_REPO_ROOT = os.path.abspath(os.path.join(_SERVER_ROOT, ".."))
# v2.0 dataset: manual_22 + llm_reviewed_17_v2 merged (kch_* chunk anchors).
# 旧 118 bank (docs/llm_generated_on_material.json) 与 candidates.json 已从
# 加载路径移除，不再被 eval 引用。
_LLM_BANK_PATH = os.path.join(_SERVER_ROOT, "tests", "dataset_v2_merged.json")


def _load_llm_reviewed_cases(store) -> list[dict]:
    """Load the human-reviewed LLM on-material bank.

    ``server/tests/dataset_v2_merged.json`` holds the v2.0 dataset:
    manual_22 + llm_reviewed_17_v2 merged. Each case carries a kch_* chunk
    anchor (``expected_src``) that points at the offline KB chunk used to
    author the question — this is the "chunk-level traceability" gold.

    Two schema branches are handled:
    - v2.0 (new): ``question`` / ``answer`` / ``expected_src`` → gold is the
      kch_* chunk id directly. No store re-resolution needed.
    - legacy (old 118 bank, if ever loaded): ``query`` / ``expected_answer`` /
      ``expected_doc_ids`` with topic_ids re-resolved against the current
      store (unit UUIDs change between seeds; topic ids are stable).
    """
    try:
        with open(_LLM_BANK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        logger.warning("LLM on-material bank missing (%s); QA set built without it",
                       _LLM_BANK_PATH)
        return []
    questions = data.get("questions", []) or []
    cases = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        # --- v2.0 schema: question/answer/expected_src (kch_* chunk anchor) ---
        if (q.get("question") or "").strip() and q.get("answer"):
            case = {
                "query": q["question"],
                "expected_answer": q["answer"],
                "expected_doc_ids": [q["expected_src"]] if q.get("expected_src") else [],
                "category": "on-material",
                "query_type": "llm_reviewed",
                "language": q.get("language", "en"),
                "difficulty": q.get("difficulty", "medium"),
                "topic_ids": list(q.get("topic_ids") or []),
                "source_ids": [q["expected_src"]] if q.get("expected_src") else [],
                "generated_by": q.get("generated_by", "llm-glm-5.3-flash"),
                "expected_src": q.get("expected_src", ""),
                "origin": q.get("origin", "llm"),
            }
            cases.append(case)
            continue
        # --- legacy schema: query/expected_answer + topic re-resolution ---
        if not (q.get("query") or "").strip():
            continue
        case = dict(q)
        case.setdefault("category", "on-material")
        case.setdefault("query_type", "llm_reviewed")
        case.setdefault("language", "en")
        case.setdefault("difficulty", "medium")
        case.setdefault("source_ids", [])
        case.setdefault("generated_by", "llm-glm-5.3-flash")
        topic_ids = case.get("topic_ids") or []
        case["topic_ids"] = list(topic_ids)
        # Re-resolve gold chunks against the current store (unit UUIDs change
        # between seeds; topic ids are stable).
        case["expected_doc_ids"] = []
        if topic_ids:
            seen: set[str] = set()
            for u in store.list_units():
                if any(tid in (u.get("topic_ids") or []) for tid in topic_ids):
                    cid = u.get("chunk_id") or u.get("unit_id")
                    if cid and cid not in seen:
                        seen.add(cid)
                        case["expected_doc_ids"].append(cid)
        cases.append(case)
    return cases


def load_test_set(filepath: str = "") -> list[dict]:
    """Load a previously saved test set.
    Args:
        filepath: Path to the test set JSON file
    Returns:
        List of test cases
    """
    if not filepath:
        filepath = _default_test_set_path()
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def build_comprehensive_test_set(store: TutorStore) -> dict[str, Any]:
    """Build the QA test set per store state.

    On-material cases come from hand-written builtin queries, synthesis queries,
    bilingual queries, and the human-reviewed LLM bank
    (``docs/llm_generated_on_material.json``). KB-derived first-sentence
    fragments are intentionally NOT QA cases — they live in the retrieval
    self-check set (``build_retrieval_selfcheck_set``) so that faithfulness /
    relevancy numbers are never computed on query==answer tautologies.

    Results are persisted to server/tests/test_set.json for reproducibility.
    Use ``load_test_set`` to reuse the exact same cases across runs.
    """
    # Phase 1: Built-in queries
    builtin_resolved = _resolve_builtin_doc_ids(store, _BUILTIN_ON_MATERIAL_QUERIES)
    # Phase 2+ are appended in place; start from builtin list.
    return _build_from_seed(store, builtin_resolved,
                            _builtin_gold(builtin_resolved))


def build_retrieval_selfcheck_set(store: TutorStore) -> dict[str, Any]:
    """Build the retrieval self-check set (one case per KB unit).

    Each case's query is the unit's own first sentence and the gold is that
    unit's chunk id. This measures "can BM25 find the exact source chunk", i.e.
    recall@k / context recall — a retrieval probe, NOT a QA benchmark. It must
    never be merged into the QA test set (query would equal the answer).
    """
    cases: list[dict] = []
    seen: set[str] = set()
    for u in store.list_units():
        sent = _first_sentence(u)
        if not sent:
            continue
        cid = u.get("chunk_id") or u.get("unit_id")
        if cid in seen:
            continue
        seen.add(cid)
        cases.append({
            "query": sent,
            "expected_answer": sent,
            "expected_doc_ids": [cid],
            "category": "retrieval-selfcheck",
            "difficulty": "medium",
            "topic_ids": u.get("topic_ids", []) or [],
            "source_ids": u.get("source_ids", []) or [u.get("source_id", "")],
            "query_type": "kb-derived-retrieval-probe",
        })
    return {
        "cases": cases,
        "summary": summarize_dataset(cases),
        "path": save_retrieval_selfcheck_set(cases),
    }


def _builtin_gold(builtin_resolved: list[dict]) -> set[str]:
    seen: set[str] = set()
    for c in builtin_resolved:
        seen.update(c.get("expected_doc_ids", []))
    return seen


def _build_from_seed(store: TutorStore,
                     seed_cases: list[dict],
                     seen_gold: set[str]) -> dict[str, Any]:
    """Shared builder: seeded cases + LLM bank + synthesis + bilingual + off-material."""
    cases = list(seed_cases)
    seen_gold = set(seen_gold)
    # Phase 2: Human-reviewed LLM-generated on-material bank (docs/llm_generated_on_material.json)
    cases.extend(_load_llm_reviewed_cases(store))
    # Phase 3: Synthesis queries
    for sq in _SYNTHESIS_QUERIES:
        cases.append(_resolve_query_doc_ids(store, sq))
    # Phase 4: Bilingual queries
    cases.extend(_generate_bilingual_queries(store))
    # Phase 5: Off-material queries (bilingual)
    for q, cat, domain in _OFF_MATERIAL_QUERIES_BILINGUAL:
        cases.append({
            "query": q,
            "expected_answer": "",
            "expected_doc_ids": [],
            "category": "off-material",
            "difficulty": "easy",
            "topic_ids": [],
            "source_ids": [],
            "query_type": "off-material",
            "domain": domain,
        })

    # Phase 6: Extended off-material queries (more coverage)
    for q, cat, domain in _OFF_MATERIAL_QUERIES_EXTENDED:
        cases.append({
            "query": q,
            "expected_answer": "",
            "expected_doc_ids": [],
            "category": "off-material",
            "difficulty": "easy",
            "topic_ids": [],
            "source_ids": [],
            "query_type": "off-material",
            "domain": domain,
        })

    return {
        "cases": cases,
        "summary": summarize_dataset_enhanced(cases),
        "path": save_test_set(cases),
    }


# ========== Demo 本地测试入口（可注释） ==========
if __name__ == "__main__":
    store = TutorStore()
    result = build_comprehensive_test_set(store)
    print(f"测试集生成完成，文件路径：{result['path']}")
    print("数据集统计：")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    selfcheck = build_retrieval_selfcheck_set(store)
    print(f"\n检索自检集生成完成，文件路径：{selfcheck['path']}")
    print("检索自检集统计：")
    print(json.dumps(selfcheck["summary"], ensure_ascii=False, indent=2))