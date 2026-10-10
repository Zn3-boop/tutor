"""Bayesian Knowledge Tracing (BKT) learner model.

Maintains, per topic, the probability that the student knows the skill
(pL=mastery). Standard 4-parameter BKT:

    pL0  : prior probability of mastery (initial guess)
    pT   : transition probability (learn when unmastered after an opportunity)
    pG   : guess probability (correct while unmastered)
    pS   : slip probability (wrong while mastered)

After each observation the model applies the standard BKT Bayesian update, and
optionally learns parameters from the student's own history (MAP-ish tweaks) so
that personalization measurably improves over time. Runs fully offline.
"""

from __future__ import annotations

import math
from typing import Any


def _clamp(x: float, lo: float = 0.001, hi: float = 0.999) -> float:
    return max(lo, min(hi, x))


class LearnerModel:
    """BKT learner model per topic, with persistence onto a student dict."""

    def __init__(self, learner_skill: float = 0.75):
        # learner_skill scales default guess/slip and transition quality; higher
        # => faster learning. Used for simulated profiles and defaults.
        self.learner_skill = float(learner_skill)

    # ---------------- parameter defaults ----------------
    def _fresh_params(self) -> dict[str, float]:
        # pT correlated w/ learner skill so fast learners transition more often.
        # Keep it modest so a wrong answer genuinely *lowers* mastery instead of
        # the (1-post)*pT transition term swamping the evidence.
        base_pT = 0.08 + 0.10 * self.learner_skill
        return {
            "pL0": 0.25,
            "pT": _clamp(base_pT),
            "pG": 0.15,
            "pS": 0.10,
        }

    def get_mastery(self, student: dict, topic_id: str) -> dict[str, Any]:
        """Return (persisted) BKT state for a topic, creating defaults if absent."""
        mastery = student.setdefault("mastery", {})
        state = mastery.get(topic_id)
        if state is None:
            params = self._fresh_params()
            state = {**params, "n_correct": 0, "n_wrong": 0, "updates": 0}
            # incorporate profile priors for simulated/known students
            profile = student.get("profile") or {}
            if profile.get("knowledge_prior"):
                prior = profile["knowledge_prior"].get(topic_id)
                if isinstance(prior, (int, float)):
                    state["pL0"] = _clamp(float(prior))
            mastery[topic_id] = state
        return state

    # ---------------- BKT update ----------------
    def observe(self, student: dict, topic_id: str, correct: bool) -> float:
        """Apply one BKT update on a question response. Returns new mastery."""
        state = self.get_mastery(student, topic_id)
        pL = state["pL0"]
        pT = state["pT"]
        pG = state["pG"]
        pS = state["pS"]

        # Likelihood of the observation given mastered / unmastered.
        p_mastered = _clamp(1.0 - pS) if correct else pS
        p_unmastered = pG if correct else _clamp(1.0 - pG)

        # Posterior after observation:
        post = (p_mastered * pL) / (p_mastered * pL + p_unmastered * (1.0 - pL))
        post = _clamp(post)

        # Learning transition: unmastered students may become mastered.
        pL_next = post + (1.0 - post) * pT
        pL_next = _clamp(pL_next)

        state["pL0"] = pL_next
        state["updates"] = state.get("updates", 0) + 1
        if correct:
            state["n_correct"] += 1
        else:
            state["n_wrong"] += 1

        self._adapt_parameters(state, correct)
        return pL_next

    def _adapt_parameters(self, state: dict, correct: bool) -> None:
        """Light personalization: tune guess/slip toward the observed error rate."""
        total = state["n_correct"] + state["n_wrong"]
        if total < 3 or state["updates"] % 3 != 0:
            return
        error_rate = state["n_wrong"] / total
        # If the student keeps failing an "mastered" state, lower slip / raise guess.
        if error_rate > 0.6:
            state["pS"] = _clamp(state["pS"] * 0.8)
            state["pG"] = _clamp(state["pG"] * 0.8)
        # Note errors as a potential misconception.
        state.setdefault("_error_rate", error_rate)

    # ---------------- diagnostics / helpers ----------------
    def mastery_level(self, student: dict, topic_id: str) -> float:
        return self.get_mastery(student, topic_id)["pL0"]

    def weakest_topics(self, student: dict, topic_ids: list[str],
                       limit: int = 5) -> list[tuple[str, float]]:
        scored = []
        for tid in topic_ids:
            if tid in (student.get("mastery") or {}):
                scored.append((tid, self.mastery_level(student, tid)))
            else:
                scored.append((tid, self._fresh_params()["pL0"]))
        scored.sort(key=lambda x: x[1])
        return scored[:limit]

    def mastery_summary(self, student: dict, topics: dict[str, dict]) -> dict[str, Any]:
        """Map topic_id -> {mastery, n_correct, n_wrong} for the dashboard."""
        out = {}
        for tid, topic in topics.items():
            state = (student.get("mastery") or {}).get(tid)
            if state is None:
                continue
            out[tid] = {
                "name": topic.get("name", tid),
                "mastery": round(state["pL0"], 3),
                "n_correct": state["n_correct"],
                "n_wrong": state["n_wrong"],
                "updates": state["updates"],
            }
        return out

    _NEG_INF = -float("inf")

    def knowledge_prior_from_diagnostic(self, correct_map: dict[str, float]) -> dict[str, float]:
        """Simple IRT-ish prior from a diagnostic quiz: percent-correct per topic."""
        return {tid: _clamp(math.sqrt(pc), 0.02, 0.98) for tid, pc in correct_map.items()}