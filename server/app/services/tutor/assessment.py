"""Adaptive assessment: quiz generation, answer verification, feedback, reports.

Offline-first design:
  - Questions are generated deterministically from the knowledge base as
    verifiable cloze-MCQs: a sentence from a Unit has a keyword blanked; the
    correct option is the true keyword and distractors are other keywords from
    the same topic. This guarantees an exact answer key (no model needed).
  - When an LLM provider is enabled, richer question types (short-answer /
    numerical) can be generated and cross-validated against the source.
  - Every question is tagged with its topic(s), source location(s) and
    difficulty, feeding both the learner model and post-assessment reports.
  - Repetition is avoided by tracking previously asked question ids per student.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random

from app.services.observability.langfuse_client import langfuse_observed
import re
from typing import Any

from app.services.tutor.learner import LearnerModel
from app.services.tutor.store import TutorStore
from app.services.tutor.error_analyzer import get_error_analyzer
from app.services.translation.client import translate_text, translation_enabled


logger = logging.getLogger(__name__)

_STOP = {".", "!", "?", ";", "，", "。", "！", "？", "；"}


class AssessmentGenerator:
    def __init__(self, store: TutorStore, learner: LearnerModel | None = None):
        self.store = store
        self.learner = learner or LearnerModel()

    # ---------------- offline question construction ----------------
    def _keywords(self, text: str) -> list[str]:
        """Real word/programming keywords from text, deduped, min length."""
        kw = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        seen: set[str] = set()
        out = []
        for k in kw:
            kk = k.lower()
            if kk in seen:
                continue
            seen.add(kk)
            out.append(k)
        return out

    # ---------------- adaptive difficulty (Day5) ---------------- 
    @staticmethod
    def _difficulty_for_mastery(mastery: float) -> str:
        """Map a topic's BKT mastery to a question difficulty band.

        Weak topics (<0.4) get easy questions to build confidence, mid topics
        (0.4-0.7) medium, and well-mastered topics hard / extension questions.
        """
        if mastery < 0.4:
            return "easy"
        if mastery < 0.7:
            return "medium"
        return "hard"

    @staticmethod
    def _distractor_limit(difficulty: str) -> int:
        """Offline difficulty knob: more options => harder MCQ (2 vs up to 4)."""
        return {"easy": 1, "medium": 2, "hard": 3}.get(difficulty, 2)

    def _build_cloze(self, sentence: str, answer: str,
                     distractors: list[str],
                     difficulty: str = "medium") -> dict | None:
        # Do a case-insensitive whole-word splice so cloze is exact.
        idx = sentence.lower().find(answer.lower())
        if idx < 0:
            return None
        end = idx + len(answer)
        blanked = sentence[:idx] + "______" + sentence[end:]
        # Take only the distractors the requested band allows, so an easy
        # question has 2 options and a hard one up to 4.
        options = [answer, *distractors[:self._distractor_limit(difficulty)]]
        random.shuffle(options)
        if len(options) < 2:  # degenerate single-option question
            return None
        return {
            "type": "mcq",
            "text": blanked.strip() + " (选择正确的一项)",
            "options": options,
            "answer": answer,
            "answer_key": options.index(answer),  # index of correct option
            "difficulty": difficulty,
        }

    def _make_question(self, unit: dict, sentence: str,
                       topic_ids: list[str],
                       difficulty: str = "medium") -> dict | None:
        kws = self._keywords(sentence)
        if len(kws) < 2:
            return None
        candidates = [k for k in kws if len(k) >= 3]
        if not candidates:
            return None
        answer = random.choice(candidates)
        distractors = [k for k in kws if k.lower() != answer.lower()]
        random.shuffle(distractors)
        distractors = list(dict.fromkeys(distractors))[:3]
        if not distractors:
            # pull distractors from the same topic's other units
            distractors = self._topic_distractors(topic_ids, answer)
        q = self._build_cloze(sentence, answer, distractors,
                              difficulty=difficulty)
        if not q:
            return None
        q["topic_ids"] = topic_ids
        q["source_ids"] = [unit.get("source_id", "")]
        q["origin"] = unit.get("origin", {})
        q["source_title"] = self._source_title(unit.get("source_id", ""))
        return q

    def _source_title(self, source_id: str) -> str:
        src = self.store.get_source(source_id)
        return (src or {}).get("title", source_id)

    def _topic_distractors(self, topic_ids: list[str], exclude: str) -> list[str]:
        out = []
        for tid in topic_ids:
            for unit in self.store.list_units():
                if tid in unit.get("topic_ids", []):
                    for k in self._keywords(unit.get("text", "")):
                        if k.lower() != exclude.lower():
                            out.append(k)
        return list(dict.fromkeys(out))[:3]

    def _pick_sentence(self, unit: dict) -> str | None:
        text = unit.get("text", "").strip()
        # drop markdown heading lines (e.g. "## Lists")
        text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))
        sentences = re.split(r"(?<=[.!?。！？；;])\s+", text)
        for s in sentences:
            s = s.strip()
            if 15 <= len(s) <= 260 and self._keywords(s) and len(self._keywords(s)) >= 2:
                return s
        return None

    # ---------------- quiz generation ----------------
    @langfuse_observed("tutor.quiz", as_type="chain")
    async def generate_quiz(self, student: dict, scope_topic_ids: list[str],
                            num_questions: int = 6,
                            llm: bool = True) -> dict[str, Any]:
        """Build a quiz over the requested scope, avoiding repeats for this student."""
        asked = set(student.get("asked_questions", []))
        units = self.store.list_units()
        topic_units = [u for u in units if set(u.get("topic_ids", [])) & set(scope_topic_ids)]
        if not topic_units:
            return {"ok": False, "error": "所选范围没有可用的课程单元", "questions": []}

        # Day5 adaptive targeting: surface the student's weakest topics first so
        # the quiz drills the gaps, and pick each unit's difficulty band from the
        # current BKT mastery. Stable sort after shuffle keeps weak topics first
        # while retaining presentation variety within a band.
        def _unit_mastery(u: dict) -> float:
            tids = u.get("topic_ids", []) or []
            scores = [self.learner.mastery_level(student, tid) for tid in tids]
            return min(scores) if scores else 0.5
        random.shuffle(topic_units)
        topic_units.sort(key=_unit_mastery)
        difficulty_plan = {
            (u.get("unit_id") or str(i)): self._difficulty_for_mastery(_unit_mastery(u))
            for i, u in enumerate(topic_units)
        }
        questions: list[dict] = []
        qids: list[str] = []

        # Phase 1: reuse persisted, valid, in-scope questions this student hasn't seen.
        bank = self.store.list_questions()
        bank_qs = [q for q in bank
                   if set(q.get("topic_ids", [])) & set(scope_topic_ids)
                   and q["question_id"] not in asked]
        random.shuffle(bank_qs)
        # Prefer bank questions whose stored difficulty already matches the
        # topic's current target band, so reuse is also adaptive (Day5).
        def _bank_difficulty_match(q: dict) -> float:
            tids = q.get("topic_ids", []) or []
            wanted = {self._difficulty_for_mastery(
                self.learner.mastery_level(student, tid)) for tid in tids}
            return 0.0 if q.get("difficulty") in wanted else 1.0
        bank_qs.sort(key=_bank_difficulty_match)
        for q in bank_qs:
            if len(questions) >= num_questions:
                break
            questions.append(self._public_question(q))
            qids.append(q["question_id"])

        # Phase 2: generate fresh cloze MCQs offline (verifiable keys).
        for unit in topic_units:
            if len(questions) >= num_questions:
                break
            sentence = self._pick_sentence(unit)
            if not sentence:
                continue
            difficulty = self._difficulty_for_mastery(_unit_mastery(unit))
            q = self._make_question(unit, sentence, unit.get("topic_ids", []),
                                    difficulty=difficulty)
            if not q:
                continue
            qid = self.store.add_question(
                text=q["text"], qtype=q["type"], options=q["options"],
                answer=q["answer"], topic_ids=q["topic_ids"],
                source_ids=q["source_ids"], difficulty=q["difficulty"],
                answer_key=str(q["answer_key"]), explanation="",
                origin=q.get("origin", {}),
            )
            questions.append(self._public_question(q, qid))
            qids.append(qid)

        # Phase 3: LLM-augmented short-answer / numerical (optional).
        if llm and len(questions) < num_questions:
            try:
                extras = await self._llm_questions(scope_topic_ids,
                                                   num_questions - len(questions))
                for eq in extras:
                    if len(questions) >= num_questions:
                        break
                    eqid = self.store.add_question(**eq)
                    questions.append(self._public_question(eq, eqid))
                    qids.append(eqid)
            except Exception as e:  # pragma: no cover - optional
                logger.warning(f"LLM questions skipped: {e}")

        self.store.update_student(student["student_id"],
                                  {"asked_questions": list(set(asked) | set(qids))})
        assessment = self.store.add_assessment(
            student_id=student["student_id"],
            scope_topic_ids=scope_topic_ids,
            questions=[{"question_id": qid, "topic_ids": q.get("topic_ids", [])}
                       for qid, q in zip(qids, questions)],
        )
        if translation_enabled() and student.get("lang") == "zh":
            questions = await self._translate_questions(questions)

        return {"ok": True, "assessment_id": assessment["assessment_id"],
                "questions": questions, "count": len(questions),
                "difficulty_plan": difficulty_plan}

# ---------------- diagnostic quiz (new-student onboarding) ----------------
    @langfuse_observed("tutor.diagnostic", as_type="chain")
    async def generate_diagnostic(self, student: dict, num_questions: int = 6,
                                  llm: bool = False,
                                  scope_topic_ids: list[str] | None = None) -> dict[str, Any]:
        """Onboarding diagnostic for a (new) student, optionally scoped.

        Generates a balanced quiz covering every selected topic (default: all),
        tags the assessment as ``mode="diagnostic"`` and seeds per-topic BKT
        defaults so the learner model has initial pL state for the report.
        As answers are submitted the existing ``submit_answer`` path updates
        mastery (pL) per topic.
        """
        topics = self.store.list_topics_by_id()
        if not topics:
            return {"ok": False, "error": "没有可用的课程主题", "questions": []}
        scope = [t for t in (scope_topic_ids or list(topics.keys())) if t in topics]
        if not scope:
            return {"ok": False, "error": "scope 中没有可用的主题", "questions": []}
        # ensure a new student's mastery map exists so report shows pL from the start
        for tid in scope:
            self.learner.get_mastery(student, tid)
        self.store.save_student(student)

        quiz = await self.generate_quiz(
            student, scope, num_questions=num_questions, llm=llm,
        )
        if not quiz.get("ok"):
            return quiz
        aid = quiz["assessment_id"]
        self.store._update("assessments", aid, {"meta": {"mode": "diagnostic"}})
        quiz["diagnostic"] = True
        quiz["mode"] = "diagnostic"
        quiz["topic_count"] = len(scope)
        return quiz

    def finalize_diagnostic(self, student: dict, assessment_id: str) -> dict[str, Any]:
        """Apply IRT-ish BKT priors from a completed diagnostic & build a report.

        Grades the diagnostic using the student's observed BKT counters
        (n_correct / n_wrong per topic), seeds ``pL0`` priors for topics that
        have NOT yet been touched by question-level BKT updates (updates==0),
        persists and returns the learner report. Offline and deterministic.
        """
        assessment = next(
            (a for a in self.store.list_assessments()
             if a.get("assessment_id") == assessment_id),
            None,
        )
        if not assessment or (assessment.get("meta") or {}).get("mode") != "diagnostic":
            return {"ok": False, "error": "assessment_id 不是诊断测验"}

        # Grade from the learner's BKT counters (n_correct / n_wrong per topic).
        correct_map: dict[str, float] = {}
        for tid, st in (student.get("mastery") or {}).items():
            n = int(st.get("n_correct", 0)) + int(st.get("n_wrong", 0))
            if n > 0:
                correct_map[tid] = int(st.get("n_correct", 0)) / n

        if not correct_map:
            return {"ok": False, "error": "诊断测验没有可评分的作答记录"}

        prior = self.learner.knowledge_prior_from_diagnostic(correct_map)
        mastery = student.setdefault("mastery", {})
        seeded = []
        for tid, pl0 in prior.items():
            st = mastery.setdefault(tid, {})
            # Only seed priors for topics BKT has NOT already started updating.
            if st.get("updates", 0) == 0:
                st.setdefault("pL0", pl0)
                seeded.append(tid)
        self.store.save_student(student)

        report = self.generate_report(student, assessment_id)
        return {"ok": True, "prior": {t: round(p, 3) for t, p in prior.items()},
                "seeded_topics": seeded, "report": report}
    def _public_question(self, q: dict, qid: str = "") -> dict:
        return {
            "question_id": qid or q.get("question_id", ""),
            "text": q["text"], "type": q.get("type", "mcq"),
            "options": q.get("options", []),
            "topic_ids": q.get("topic_ids", []),
            "source_ids": q.get("source_ids", []),
            "difficulty": q.get("difficulty", "medium"),
            "origin": q.get("origin", {}),
            "source_title": q.get("source_title", ""),
        }

    async def _translate_questions(self, questions: list[dict]) -> list[dict]:
        """P1.5 轻量按需翻译：把英文题干翻译成中文展示文本。

        - 只改 ``text``（题干）；选项保留英文术语，保证答案按 index 校验不受影响。
        - 下划线占位符（______）与技术术语由翻译客户端原样保留。
        - 翻译失败/关闭开关时保持原文，绝不阻断出题。
        """
        for q in questions:
            text = (q.get("text") or "").strip()
            if not text:
                continue
            res = await asyncio.to_thread(translate_text, text)
            if res.translated:
                q["text"] = res.text
                q["translated"] = True
        return questions

    async def _llm_questions(self, scope_topic_ids: list[str],
                             count: int) -> list[dict]:
        from app.services.llm.provider import provider
        if not provider.enabled:
            return []
        context = self._scope_context(scope_topic_ids)[:6000]
        prompt = (
            "Generate exactly " + str(count) +
            " short-answer/numerical questions grounded in this course material.\n"
            "Return JSON array of objects: {type, text, answer, topic_ids, difficulty}.\n"
            "Each answer must be verifiable from the material. Material:\n" + context
        )
        resp = (await provider.chat(system_prompt="You are a course-exam generator.",
                                    user_prompt=prompt, temperature=0.3)).strip()
        raw = re.sub(r"^```json\s*", "", resp)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("questions", [])
        out = []
        for it in data:
            qid_topics = [t for t in it.get("topic_ids", []) if t in scope_topic_ids] \
                or scope_topic_ids
            q = {
                "text": it.get("text", ""), "qtype": it.get("type", "short"),
                "options": [], "answer": it.get("answer", ""),
                "topic_ids": qid_topics, "source_ids": [],
                "difficulty": it.get("difficulty", "medium"),
                "answer_key": "", "explanation": "", "origin": {},
            }
            # Verify LLM-generated question before adding
            verification = await self.verify_llm_question(q, scope_topic_ids, max_retries=1)
            if verification.get("verification_passed"):
                out.append(q)
                logger.info(f"LLM question verified (confidence={verification.get('confidence_score', 0):.2f}): {q['text'][:50]}...")
            else:
                logger.warning(f"LLM question verification failed, skipping: {q['text'][:50]}...")
        return out

    def _scope_context(self, topic_ids: list[str]) -> str:
        parts = []
        for u in self.store.list_units():
            if set(u.get("topic_ids", [])) & set(topic_ids):
                parts.append(u.get("text", ""))
        return "\n\n".join(parts)

    # ---------------- verification ----------------
    def verify_question(self, question_id: str) -> dict[str, Any]:
        q = self.store.get_question(question_id)
        if q is None:
            return {"valid": False, "issues": ["question not found"]}
        issues = []
        opts = q.get("options") or []
        if not q.get("text"):
            issues.append("empty stem")
        if q.get("type") == "mcq":
            if len(opts) < 2:
                issues.append("fewer than 2 options")
            if q.get("answer") not in opts:
                issues.append("answer not among options")
            if len(opts) != len(set(opts)):
                issues.append("duplicate options")
            if not q.get("answer_key") and not q.get("answer"):
                issues.append("missing answer key")
        else:
            if not q.get("answer"):
                issues.append("missing answer key")
        return {"valid": len(issues) == 0, "issues": issues,
                "question_id": question_id, "type": q.get("type")}

    async def verify_llm_question(self, question: dict, scope_topic_ids: list[str],
                                   max_retries: int = 2) -> dict[str, Any]:
        """Verify an LLM-generated question against course material.

        Uses the LLM to self-check that the answer is verifiable from the
        course context. If verification fails, retries up to max_retries times.

        Args:
            question: The generated question dict with text, answer, topic_ids
            scope_topic_ids: Topic IDs the question should be grounded in
            max_retries: Maximum number of regeneration attempts

        Returns:
            dict with verified_question, confidence_score, verification_passed,
            and retry_count.
        """
        from app.services.llm.provider import provider
        if not provider.enabled:
            return {
                "verified_question": question,
                "confidence_score": 0.5,
                "verification_passed": True,  # offline fallback: trust the question
                "retry_count": 0,
                "method": "offline_fallback",
            }

        context = self._scope_context(scope_topic_ids)[:4000]
        prompt = (
            f"Verify if this question and answer are factually correct "
            f"based on the course material below.\n\n"
            f"Question: {question.get('text', '')}\n"
            f"Answer: {question.get('answer', '')}\n\n"
            f"Course Material:\n{context}\n\n"
            f"Respond with JSON: {{\"verified\": true/false, "
            f"\"confidence\": 0.0-1.0, \"issues\": [\"issue1\", ...]}}"
        )

        for attempt in range(max_retries + 1):
            try:
                resp = (await provider.chat(
                    system_prompt="You are a strict educational content verifier. "
                                  "Check that questions and answers are factually "
                                  "correct and verifiable from the provided material.",
                    user_prompt=prompt,
                    temperature=0.1,
                )).strip()

                # Extract JSON from response
                import json
                raw = re.sub(r"^```json\s*", "", resp)
                raw = re.sub(r"\s*```$", "", raw)
                result = json.loads(raw)

                verified = result.get("verified", False)
                confidence = float(result.get("confidence", 0.0))
                issues = result.get("issues", [])

                if verified and confidence >= 0.7:
                    return {
                        "verified_question": question,
                        "confidence_score": confidence,
                        "verification_passed": True,
                        "retry_count": attempt,
                        "method": "llm_verification",
                        "issues": issues,
                    }

                # If failed and we have retries left, try to regenerate
                if attempt < max_retries:
                    regen_prompt = (
                        f"The previous question had issues: {issues}.\n"
                        f"Please generate a corrected question and answer "
                        f"based on this course material:\n{context}\n\n"
                        f"Return JSON: {{\"text\": \"...\", \"answer\": \"...\", "
                        f"\"type\": \"short\", \"difficulty\": \"medium\"}}"
                    )
                    regen_resp = (await provider.chat(
                        system_prompt="You are a course-exam generator.",
                        user_prompt=regen_prompt,
                        temperature=0.3,
                    )).strip()
                    raw = re.sub(r"^```json\s*", "", regen_resp)
                    raw = re.sub(r"\s*```$", "", raw)
                    new_q = json.loads(raw)
                    question["text"] = new_q.get("text", question["text"])
                    question["answer"] = new_q.get("answer", question["answer"])
                    question["difficulty"] = new_q.get("difficulty", question.get("difficulty", "medium"))

            except Exception as exc:
                logger.warning(f"LLM question verification failed (attempt {attempt}): {exc}")
                if attempt == max_retries:
                    break

        # If all retries exhausted, return the last version with low confidence
        return {
            "verified_question": question,
            "confidence_score": 0.3,
            "verification_passed": False,
            "retry_count": max_retries,
            "method": "llm_verification_failed",
            "issues": ["Verification failed after maximum retries"],
        }

    # ---------------- answering + learner update ----------------
    @langfuse_observed("tutor.submit", as_type="chain")
    async def submit_answer(self, student: dict, assessment_id: str,
                            question_id: str, chosen: str) -> dict[str, Any]:
        q = self.store.get_question(question_id)
        if q is None:
            return {"ok": False, "error": "question not found"}
        if q.get("type") == "mcq":
            correct = (chosen == q.get("answer"))
        else:
            correct = self._short_answer_match(chosen, q.get("answer", ""))

        mastery_delta = {}
        for tid in q.get("topic_ids", []):
            before = self.learner.mastery_level(student, tid)
            after = self.learner.observe(student, tid, correct)
            mastery_delta[tid] = {"before": round(before, 3), "after": round(after, 3)}

        misconceptions = student.get("misconceptions", {})
        if not correct:
            for tid in q.get("topic_ids", []):
                misconceptions[tid] = misconceptions.get(tid, 0) + 1
            # keep a capped sample of wrong answers so the LLM misconception judge
            # (3c) can reason about *why* the student is wrong, not just the count.
            samples = student.setdefault("misconception_samples", [])
            if not any(s.get("question_id") == question_id for s in samples):
                samples.append({
                    "question_id": question_id,
                    "topic_ids": q.get("topic_ids", []),
                    "question": q.get("text", ""),
                    "chosen": chosen,
                    "correct_answer": q.get("answer", ""),
                })
                del samples[:-12]
            # auto-record to wrong-question notebook
            self.store.add_wrong_question(
                student_id=student["student_id"],
                question_id=question_id,
                question_text=q.get("text", ""),
                chosen=chosen,
                correct_answer=q.get("answer", ""),
                topic_ids=q.get("topic_ids", []),
                assessment_id=assessment_id,
                explanation=q.get("explanation", ""),
            )
        student["misconceptions"] = misconceptions
        # snapshot average mastery for the learner-visualization curve (20% weight).
        traj = student.setdefault("mastery_traj", [])
        avgs = [self.learner.mastery_level(student, t)
                for t in self.store.list_topics_by_id().keys()]
        traj.append({"step": len(traj) + 1,
                     "mastery": round((sum(avgs) / len(avgs)) if avgs else 0.0, 3)})
        if len(traj) > 200:
            del traj[:-200]
        self.store.save_student(student)

        feedback = self._build_feedback(q, correct, chosen)
        return {
            "ok": True,
            "correct": correct,
            "feedback": feedback,
            "mastery_delta": mastery_delta,
            "question": self._public_question(q, question_id),
        }

    # ---------------- LLM misconception judge (3c) ----------------
    def _fallback_misconceptions(self, student: dict) -> dict[str, Any]:
        """Count-based fallback when the LLM is unavailable."""
        out = {}
        for tid, count in sorted(student.get("misconceptions", {}).items(),
                                 key=lambda x: x[1], reverse=True)[:5]:
            out[tid] = {"label": "在该主题上重复出错，疑似概念混淆", "error_count": count}
        return out

    async def analyze_misconceptions(self, student: dict) -> dict[str, Any]:
        """LLM judge: one call groups the student's wrong-answer samples and emits
        a concrete misconception label per topic (e.g. 混淆了 def 与 lambda).

        Falls back to a count-based report when the LLM is disabled/unreachable,
        so assessment never blocks on the network.
        """
        from app.services.llm.provider import provider
        samples = student.get("misconception_samples") or []
        if not samples:
            return self._fallback_misconceptions(student)
        grouped: dict[str, list[dict]] = {}
        for s in samples:
            for tid in (s.get("topic_ids") or []):
                grouped.setdefault(tid, []).append(s)
        if not provider.enabled:
            return self._fallback_misconceptions(student)

        topics = self.store.list_topics_by_id()
        lines = []
        for tid, ss in grouped.items():
            name = topics.get(tid, {}).get("name", tid)
            lines.append(f"- topic: {tid} ({name})")
            for s in ss[-3:]:
                lines.append(f"  题目: {s.get('question', '')}")
                lines.append(f"  学生答案: {s.get('chosen', '')} / 正确答案: {s.get('correct_answer', '')}")
        prompt = (
            "分析学生在测验中的答错模式，找出每个 topic 背后真正的心智误解（misconception）。\n"
            "对每个出现过的 topic_id 给出一个简短的中文误解标签（如『混淆了函数定义 def 与调用』"
            "『遗漏了返回值的空返回场景』），不要只重复『概念不清』这类空话。\n\n"
            + "\n".join(lines) +
            "\n\n只输出 JSON 对象，键为 topic_id、值为字符串标签，例如："
            '{"t_functions": "混淆了 def 定义与函数调用"}'
        )
        resp = ""
        try:
            resp = (await provider.chat(
                system_prompt="你是诊断学生学情的学习分析师。",
                user_prompt=prompt, temperature=0.2)).strip()
        except Exception as exc:
            logger.warning(f"misconception LLM call failed: {exc}")
            return self._fallback_misconceptions(student)

        analysis: dict[str, str] = {}
        m = re.search(r"\{.*\}", resp, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    analysis = {str(k): str(v) for k, v in data.items() if v}
            except Exception as exc:
                logger.warning(f"misconception json parse failed: {exc}")

        out = {}
        for tid, ss in grouped.items():
            out[tid] = {
                "label": analysis.get(tid) or "在该主题上重复出错，疑似概念混淆",
                "error_count": len(ss),
            }
        student["misconception_analysis"] = out
        self.store.save_student(student)
        return out

    def _short_answer_match(self, chosen: str, key: str) -> bool:
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", (s or "").lower())
        c, k = norm(chosen), norm(key)
        if c == k:
            return True
        try:
            return abs(float(chosen) - float(key)) < 1e-3
        except Exception:
            return False

    def _build_feedback(self, q: dict, correct: bool, chosen: str) -> dict[str, Any]:
        src = self._source_title(q.get("source_ids", [""])[0]) \
            if q.get("source_ids") else ""
        
        # 如果不正确，进行错误分析
        error_analysis = None
        if not correct:
            analyzer = get_error_analyzer()
            error_analysis = analyzer.classify_error(
                question_text=q.get("text", ""),
                student_answer=chosen,
                correct_answer=q.get("answer", ""),
                explanation=q.get("explanation")
            )
        
        return {
            "correct": correct,
            "your_answer": chosen,
            "correct_answer": q.get("answer", ""),
            "explanation": q.get("explanation") or f"依据来源：{src}",
            "citation": {"source_title": src, "origin": q.get("origin", {})},
            "summary": "回答正确 ✔" if correct else "回答错误 ✘，可回看下方来源再复习。",
            "error_analysis": error_analysis,
        }

    # ---------------- post-assessment report ----------------
    def generate_report(self, student: dict, assessment_id: str) -> dict[str, Any]:
        topics = self.store.list_topics_by_id()
        mastery = self.learner.mastery_summary(student, topics)
        weakest = self.learner.weakest_topics(student, list(topics.keys()), limit=5)
        weak = []
        for tid, m in weakest:
            weak.append({"topic_id": tid, "name": topics.get(tid, {}).get("name", tid),
                         "mastery": round(m, 3)})
        misconceptions = []
        analysis = student.get("misconception_analysis") or {}
        for tid, count in sorted(student.get("misconceptions", {}).items(),
                                 key=lambda x: x[1], reverse=True)[:5]:
            a = analysis.get(tid)
            misconceptions.append({
                "topic_id": tid,
                "name": topics.get(tid, {}).get("name", tid),
                "error_count": count,
                "misconception": (a.get("label") if isinstance(a, dict) else a)
                                 or "在该主题上重复出错，疑似概念混淆",
            })
        overall = 0.0
        if mastery:
            overall = sum(x["mastery"] for x in mastery.values()) / len(mastery)
        report = {
            "assessment_id": assessment_id,
            "overall_mastery": round(overall, 3),
            "topic_count": len(mastery),
            "weak_topics": weak,
            "misconceptions": misconceptions,
            "mastery_by_topic": mastery,
        }
        self.store.update_student(student["student_id"], {"last_report": report})
        return report


_generator: AssessmentGenerator | None = None


def get_assessment_generator(store: TutorStore | None = None) -> AssessmentGenerator:
    global _generator
    if store is None:
        from app.services.tutor.store import get_tutor_store
        store = get_tutor_store()
    if _generator is None or _generator.store is not store:
        _generator = AssessmentGenerator(store=store)
    return _generator