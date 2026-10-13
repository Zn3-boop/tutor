"""Use LLM to auto-generate on-material test questions from course knowledge base.

Purpose:
    Read course units from TutorStore, send them to the configured LLM
    (glm-5.3-flash), and ask it to generate diverse test questions
    (factual, conceptual, procedural) in both English and Chinese.
    These questions serve as additional on-material test cases after
    human review.

Output:
    docs/llm_generated_on_material.json  (118 questions, 72 en + 46 zh)

Usage:
    cd server && python generate_llm_on_material.py

Note:
    Samples up to 3 units per topic for generation.
    Requires LLM_API_KEY in server/.env.
    Questions need human review before integration into the test set.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.services.tutor.store import get_tutor_store
from app.services.llm.provider import LLMProvider

PROMPT_TEMPLATE = """You are an expert Python programming educator. Given the following course content, generate 3 diverse test questions that a student might ask about this material.

Requirements:
- Each question should be answerable from the given content
- Generate one question of each type: factual, conceptual, procedural
- Questions should be at appropriate difficulty for introductory Python students
- Output as JSON array with fields: query, query_type, difficulty, expected_answer
- difficulty: one of "easy", "medium", "hard"
- query_type: one of "factual", "conceptual", "procedural", "comparison"
- Keep expected_answer concise (1-2 sentences)

Course content:
---
{content}
---

Output JSON array only, no other text:"""

BILINGUAL_PROMPT_TEMPLATE = """你是一个Python编程教育专家。根据以下课程内容，生成2个中文测试问题。

要求：
- 每个问题应该可以从给定内容中回答
- 一个事实性问题(factual)，一个概念性问题(conceptual)
- 输出为JSON数组，包含字段: query, query_type, difficulty, expected_answer
- difficulty: "easy", "medium", 或 "hard"
- expected_answer 简洁（1-2句话）

课程内容：
---
{content}
---

仅输出JSON数组："""


async def generate_questions_for_unit(provider: LLMProvider, unit: dict) -> list[dict]:
    content = (unit.get("text") or "").strip()
    if len(content) < 50:
        return []

    topic_ids = unit.get("topic_ids", []) or []
    chunk_id = unit.get("chunk_id") or unit.get("unit_id", "")
    source_ids = unit.get("source_ids", []) or [unit.get("source_id", "")]

    results = []

    for template, lang in [(PROMPT_TEMPLATE, "en"), (BILINGUAL_PROMPT_TEMPLATE, "zh")]:
        prompt = template.format(content=content[:1500])
        try:
            resp = await provider.chat(
                system_prompt="You are a helpful assistant that outputs valid JSON.",
                user_prompt=prompt,
                temperature=0.3,
            )
            text = resp.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            questions = json.loads(text)
            if not isinstance(questions, list):
                continue
            for q in questions:
                q["category"] = "on-material"
                q["topic_ids"] = topic_ids
                q["expected_doc_ids"] = [chunk_id]
                q["source_ids"] = source_ids
                q["language"] = lang
                q["generated_by"] = "llm-glm-5.3-flash"
                results.append(q)
        except Exception as e:
            print(f"  [WARN] LLM generation failed for {chunk_id!r} ({lang}): {e}")

    return results


async def main():
    store = get_tutor_store()
    topics = store.list_topics_by_id()
    units = store.list_units()
    print(f"Topics: {len(topics)}, Units: {len(units)}")

    provider = LLMProvider()
    print(f"LLM: {(provider.model)} @ {provider.base_url}")

    all_generated = []
    seen_topics: set[str] = set()

    topic8units = {}
    for u in units:
        for tid in (u.get("topic_ids") or []):
            topic8units.setdefault(tid, []).append(u)

    for tid, tid_units in topic8units.items():
        seen_topics.add(tid)
        sampled = tid_units[:3]
        for u in sampled:
            chunk_id = u.get("chunk_id") or u.get("unit_id", "")
            content_preview = (u.get("text") or "")[:80].replace("\n", " ")
            print(f"  Generating for {tid}/{chunk_id}: {content_preview}...")
            questions = await generate_questions_for_unit(provider, u)
            all_generated.extend(questions)
            print(f"    -> {len(questions)} questions generated")

    print(f"\nTotal generated: {len(all_generated)} questions")
    print(f"Topics covered: {sorted(seen_topics)}")

    by_type = {}
    by_lang = {}
    for q in all_generated:
        qt = q.get("query_type", "unknown")
        by_type[qt] = by_type.get(qt, 0) + 1
        lang = q.get("language", "unknown")
        by_lang[lang] = by_lang.get(lang, 0) + 1
    print(f"By type: {by_type}")
    print(f"By language: {by_lang}")

    out = os.path.join(os.path.dirname(__file__), "..", "docs", "llm_generated_on_material.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "version": "1.0",
            "description": "LLM-generated on-material test questions for human review",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "generator": "glm-5.3-flash",
            "total": len(all_generated),
            "by_type": by_type,
            "by_language": by_lang,
            "questions": all_generated,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out}")
    print("\nNext step: Human review these questions, then integrate into _BUILTIN_ON_MATERIAL_QUERIES")


if __name__ == "__main__":
    asyncio.run(main())