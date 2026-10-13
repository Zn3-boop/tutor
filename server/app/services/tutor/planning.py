"""Learning-planning helpers (Day7 / optional enhancements).

Three offline-first, deterministic features layered on top of the BKT learner
model and the topic graph:

  1. ``course_graph``     - topic + prerequisite graph (nodes/edges) for a
                            course-flow visualisation in the dashboard.
  2. ``weakness_flashcards`` - review cards mined from the weakest topics:
                            a source sentence with a key term blanked (front)
                            and the answer + citation (back). No LLM needed.
  3. ``study_plan``       - a day-by-day schedule that ranks weak topics first,
                            honours prerequisite ordering, and spaces reviews
                            with an exponential forgetting curve so material is
                            re-visited before it decays.

All of it runs fully offline (stdlib + existing store/learner only).
"""

from __future__ import annotations

import re
from typing import Any

from app.services.tutor.learner import LearnerModel
from app.services.tutor.store import TutorStore
from app.services.translation.client import translate_text, translation_enabled

# Spaced-repetition (EBH-style) review intervals, in days, after first exposure.
_SPACED_INTERVALS = [1, 3, 7, 14, 30]

_WEAK_THRESHOLD = 0.40
_MASTERED_THRESHOLD = 0.70

_SENT_SPLIT = re.compile(r"(?<=[.!?。！？；;])\s+|\n+")
# Learnable key term: identifiers / camelCase / underscored words (min 4 chars).
_KEYWORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


class LearningPlanner:
    def __init__(self, store: TutorStore, learner: LearnerModel | None = None):
        self.store = store
        self.learner = learner or LearnerModel()

    # ---------------- 6a. course graph ----------------
    def course_graph(self, student_id: str = "") -> dict[str, Any]:
        topics = self.store.list_topics_by_id()
        mastery = {}
        if student_id:
            student = self.store.get_student(student_id)
            if student:
                mastery = self.learner.mastery_summary(student, topics)

        nodes = []
        for tid, t in topics.items():
            m = mastery.get(tid, {}).get("mastery")
            nodes.append({
                "id": tid,
                "name": t.get("name", tid),
                "concepts": t.get("concepts", []),
                "mastery": round(m, 3) if m is not None else None,
            })

        edges = []
        seen: set[tuple[str, str]] = set()
        for tid, t in topics.items():
            for pre in t.get("prerequisites", []) or []:
                if pre in topics and (pre, tid) not in seen:
                    edges.append({"from": pre, "to": tid})
                    seen.add((pre, tid))
        return {"nodes": nodes, "edges": edges}

    # ---------------- 6b. weakness flashcards ----------------
    def weakness_flashcards(self, student_id: str, limit: int = 10) -> dict[str, Any]:
        topics = self.store.list_topics_by_id()
        student = self.store.get_student(student_id)
        if student is None:
            return {"ok": False, "error": "student not found: {}".format(student_id)}

        # Weakest topics first (the learner model folds in default priors).
        weak_first = self.learner.weakest_topics(student, list(topics.keys()), limit=99)

        units_by_topic: dict[str, list[dict]] = {tid: [] for tid in topics}
        for u in self.store.list_units():
            for t in u.get("topic_ids", []):
                if t in units_by_topic:
                    units_by_topic[t].append(u)

        cards: list[dict[str, Any]] = []
        for tid, _m in weak_first:
            if tid not in topics:
                continue
            for unit in units_by_topic.get(tid, []):
                if len(cards) >= limit:
                    break
                card = self._card_from_unit(unit, topics.get(tid, {}))
                if card:
                    cards.append(card)
            if len(cards) >= limit:
                break

        if translation_enabled() and student.get("lang") == "zh":
            for card in cards:
                front = (card.get("front") or "").strip()
                if front:
                    res = translate_text(front)
                    if res.translated:
                        card["front"] = res.text
                        card["translated"] = True

        return {"ok": True, "count": len(cards), "cards": cards}

    def _card_from_unit(self, unit: dict, topic: dict) -> dict | None:
        text = (unit.get("text") or "").strip()
        if not text:
            return None
        # Keep the first short sentence so the cloze stays readable.
        sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
        for sent in sentences:
            if len(sent) > 600:
                continue
            kw = self._first_learnable_keyword(sent)
            if not kw:
                continue
            idx = sent.lower().find(kw.lower())
            if idx < 0:
                continue
            front = sent[:idx] + "_____" + sent[idx + len(kw):]
            origin = unit.get("origin") or {}
            topic_ids = unit.get("topic_ids") or []
            return {
                "unit_id": unit.get("unit_id", ""),
                "topic_id": topic_ids[0] if topic_ids else topic.get("topic_id"),
                "topic_name": topic.get("name", ""),
                "front": front,
                "back": kw,
                "source_label": origin.get("label", ""),
            }
        return None

    @staticmethod
    def _first_learnable_keyword(sentence: str) -> str | None:
        for kw in _KEYWORD.findall(sentence):
            low = kw.lower()
            if low in {"the", "and", "this", "that", "with", "from", "into",
                       "will", "have", "when", "then", "else", "case", "such"}:
                continue
            return kw
        return None

    # ---------------- 6c. study plan ----------------
    def study_plan(self, student_id: str, exam_days: int,
                   sessions_per_week: int,
                   strategy: str = "static") -> dict[str, Any]:
        student = self.store.get_student(student_id)
        if student is None:
            return {"ok": False, "error": "student not found: {}".format(student_id)}
        topics = self.store.list_topics_by_id()

        mastery: dict[str, float] = {}
        for tid in topics:
            mastery[tid] = self.learner.mastery_level(student, tid)

        ordered = self._toposort(topics)
        level: dict[str, int] = {tid: 0 for tid in topics}
        for tid in ordered:
            pres = [p for p in (topics.get(tid, {}).get("prerequisites") or [])
                    if p in topics]
            if pres:
                level[tid] = 1 + max(level[p] for p in pres)

        # Task 13: 每日任务内容增强 —— 预先为每个主题收集真实教材材料标签，
        # 供 _activity 生成「学习目标 / 教材材料 / 练习任务 / 复习要求」。
        materials_by_topic = self._topic_materials(topics)

        if strategy == "rl":
            ordered = self._rl_reorder(
                student, topics, mastery, ordered, level,
            )
        else:
            ordered.sort(key=lambda tid: (
                level.get(tid, 0),
                mastery.get(tid, self.learner._fresh_params()["pL0"]),
                tid,
            ))

        def _session_count(tid: str) -> int:
            m = mastery.get(tid, 0.25)
            extra = 1 if any(tid in (topics.get(o, {}).get("prerequisites") or [])
                             for o in topics) else 0
            if m < _WEAK_THRESHOLD:
                return 3 + extra
            if m < _MASTERED_THRESHOLD:
                return 2 + extra
            return 1

        daily_capacity = max(1, round(sessions_per_week / 7))

        schedule: list[dict[str, Any]] = []
        day_load: dict[int, int] = {}
        for tid in ordered:
            count = _session_count(tid)
            gaps = _SPACED_INTERVALS[: count - 1] if count > 1 else []
            day = 1
            while day_load.get(day, 0) >= daily_capacity and day < exam_days:
                day += 1
            day_load[day] = day_load.get(day, 0) + 1
            m = mastery.get(tid, 0.25)
            if count > 1:
                reason = ("弱项掌握度 {:.2f}, 需加强".format(m) if m < _WEAK_THRESHOLD
                          else "掌握度 {:.2f}, 巩固".format(m))
            else:
                reason = "掌握良好, 轻复习"
            schedule.append(self._activity(day, tid, topics, "学习", reason, materials_by_topic))
            for gi, gap in enumerate(gaps, start=1):
                rday = day + sum(gaps[:gi])
                if rday > exam_days:
                    break
                while day_load.get(rday, 0) >= daily_capacity:
                    rday += 1
                    if rday > exam_days:
                        break
                if rday > exam_days:
                    break
                day_load[rday] = day_load.get(rday, 0) + 1
                schedule.append(self._activity(
                    rday, tid, topics, "复习",
                    "遗忘曲线间隔复习 (第{}次)".format(gi + 1),
                    materials_by_topic, review_round=gi + 1))

        schedule.sort(key=lambda a: (a["day"], a["topic_name"]))

        by_day: dict[int, list[dict]] = {}
        for a in schedule:
            by_day.setdefault(a["day"], []).append(a)
        days = [{
            "day": d,
            "activities": by_day[d],
            "minutes": 10 * len(by_day[d]),
        } for d in sorted(by_day)]

        return {
            "ok": True,
            "student_id": student_id,
            "exam_days": exam_days,
            "sessions_per_week": sessions_per_week,
            "strategy": strategy,
            "days": days,
            "stats": {
                "total_activities": len(schedule),
                "learn_sessions": sum(1 for a in schedule if a["action"] == "学习"),
                "review_sessions": sum(1 for a in schedule if a["action"] == "复习"),
                "covered_topics": len(ordered),
            },
        }

    def _topic_materials(self, topics: dict[str, dict]) -> dict[str, list[str]]:
        """为每个主题收集真实教材材料标签（来源标题 + 页码/段落），供每日任务使用。

        规则：从 store 中找出 topic_ids 命中该主题的 units，聚合其来源标题与
        origin 标签（如 p.12 / slide 3 / text#5）；最多取前 3 条去重结果。
        没有资料时回退为「《主题名》相关章节」通用提示，保证字段非空。
        """
        sources = {s["source_id"]: s for s in self.store.list_sources()}
        index: dict[str, list[str]] = {}
        for u in self.store.list_units():
            origin = u.get("origin") or {}
            plabel = origin.get("label") or ""
            if not plabel and origin.get("page") is not None:
                plabel = "p.{}".format(origin["page"])
            src = sources.get(u.get("source_id") or "") or {}
            base = src.get("title") or src.get("name") or ""
            item = "{}{}".format(base, "（{}）".format(plabel) if plabel else "")
            if not item:
                continue
            for tid in u.get("topic_ids") or []:
                if tid not in topics:
                    continue
                bucket = index.setdefault(tid, [])
                if item not in bucket:
                    bucket.append(item)
        out: dict[str, list[str]] = {}
        for tid, t in topics.items():
            labels = index.get(tid) or []
            if not labels:
                labels = ["《{}》相关章节".format(t.get("name", tid))]
            out[tid] = labels[:3]
        return out

    def _activity(
        self,
        day: int,
        tid: str,
        topics: dict,
        action: str,
        reason: str,
        materials_by_topic: dict[str, list[str]] | None = None,
        review_round: int = 0,
    ) -> dict[str, Any]:
        """构造一条每日学习/复习任务，包含：
        - 学习目标 learning_goal：核心概念 + 掌握度目标
        - 教材材料 materials：真实来源标题/页码（来自 _topic_materials）
        - 练习任务 exercise：针对学习/复习动作给出可执行的练习与错题复盘
        - 复习要求 review_requirement：前置知识 / 遗忘曲线间隔复习自测要求
        """
        t = topics.get(tid, {})
        name = t.get("name", tid)
        concepts = t.get("concepts", [])
        mats = (materials_by_topic or {}).get(tid) or []

        learning_goal = "掌握 {} 核心概念".format(name)
        if concepts:
            learning_goal += "：{}".format("、".join(concepts[:3]))
        learning_goal += "，目标掌握度 ≥ 70%"

        materials = "；".join(mats[:2]) if mats else "《{}》相关章节".format(name)

        if action == "复习":
            exercise = "重做「{}」的 Quiz 3-5 题 / 闪卡，并复盘上次错题".format(name)
            if review_round > 0:
                exercise += "（第 {} 轮间隔复习）".format(review_round)
            pre_names = [topics.get(p, {}).get("name", p)
                         for p in (t.get("prerequisites") or []) if p in topics]
            if pre_names:
                review_requirement = "复习前先回顾前置主题：{}；完成后自测确认掌握度回升 ≥70%".format(
                    "、".join(pre_names[:3]))
            else:
                review_requirement = "按遗忘曲线完成本轮复习，并用 3 道自测题确认掌握度未衰减"
        else:
            exercise = "完成「{}」的练习题（Quiz 3-5 题），记录错题并入错题本".format(name)
            pre_names = [topics.get(p, {}).get("name", p)
                         for p in (t.get("prerequisites") or []) if p in topics]
            review_requirement = (
                "先复习前置主题：{}（掌握度不足 70% 时优先补基础）".format("、".join(pre_names[:3]))
                if pre_names else "无需前置复习，可直接开始学习")

        return {
            "day": day,
            "topic_id": tid,
            "topic_name": name,
            "action": action,
            "reason": reason,
            "learning_goal": learning_goal,
            "materials": materials,
            "exercise": exercise,
            "review_requirement": review_requirement,
        }

    def _rl_reorder(
        self,
        student: dict,
        topics: dict[str, dict],
        mastery: dict[str, float],
        ordered: list[str],
        level: dict[str, int],
    ) -> list[str]:
        """使用 RL 策略重新排序 topic 列表。"""
        try:
            from app.services.tutor.rl_planner import get_rl_planner, RLState
            rl = get_rl_planner()
            prerequisites_map: dict[str, list[str]] = {}
            for tid, t in topics.items():
                prerequisites_map[tid] = [p for p in (t.get("prerequisites") or []) if p in topics]
            history = student.get("mastery_traj", [])[-20:]
            state = RLState(
                mastery_vector=mastery,
                topic_graph=prerequisites_map,
                history_window=history,
            )
            actions = rl.recommend_path(state, ordered, prerequisites_map, top_k=len(ordered))
            action_order = {a.topic_id: i for i, a in enumerate(actions)}
            remaining = [tid for tid in ordered if tid not in action_order]
            reordered = [a.topic_id for a in actions] + remaining
            return reordered
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"RL reorder failed, fallback to static: {e}")
            ordered.sort(key=lambda tid: (
                level.get(tid, 0),
                mastery.get(tid, self.learner._fresh_params()["pL0"]),
                tid,
            ))
            return ordered

    @staticmethod
    def _toposort(topics: dict[str, dict]) -> list[str]:
        """Kahn's algorithm; prerequisites before dependents."""
        indeg = {tid: 0 for tid in topics}
        children: dict[str, list[str]] = {tid: [] for tid in topics}
        for tid, t in topics.items():
            for pre in t.get("prerequisites", []) or []:
                if pre not in topics:
                    continue
                children[pre].append(tid)
                indeg[tid] += 1
        ready = [tid for tid, d in indeg.items() if d == 0]
        order: list[str] = []
        while ready:
            tid = ready.pop(0)
            order.append(tid)
            for c in children[tid]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    ready.append(c)
        for tid in topics:
            if tid not in order:
                order.append(tid)
        return order


_planner: LearningPlanner | None = None


def get_learning_planner(store: TutorStore | None = None) -> LearningPlanner:
    global _planner
    if store is None:
        from app.services.tutor.store import get_tutor_store
        store = get_tutor_store()
    if _planner is None or _planner.store is not store:
        _planner = LearningPlanner(store=store)
    return _planner