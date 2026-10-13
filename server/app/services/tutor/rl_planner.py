"""RL 学习路径规划器。

在现有静态规划器基础上接入强化学习，根据学生历史掌握动态调整知识点顺序。
仅使用 LangFuse 记录 RL 决策，不引入 OTel。
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any

from app.services.observability.langfuse_client import langfuse_observed

logger = logging.getLogger(__name__)

_RL_MODEL_DIR = os.getenv("RL_MODEL_DIR", "")
_ALPHA_START = 1.0
_ALPHA_END = 0.3
_WARMUP_STEPS = 100


class RLState:
    """RL 状态空间：mastery 向量 + 图结构 + 历史窗口。"""

    def __init__(
        self,
        mastery_vector: dict[str, float],
        topic_graph: dict[str, list[str]],
        history_window: list[dict[str, Any]],
    ):
        self.mastery_vector = mastery_vector
        self.topic_graph = topic_graph
        self.history_window = history_window

    def to_embedding(self, all_topic_ids: list[str]) -> list[float]:
        """将状态转为固定长度 embedding 向量。"""
        mastery = [self.mastery_vector.get(tid, 0.0) for tid in all_topic_ids]
        n = len(all_topic_ids)
        avg_mastery = sum(mastery) / max(n, 1)
        weak_count = sum(1 for m in mastery if m < 0.4)
        history_len = len(self.history_window)
        recent_correct = 0
        if self.history_window:
            last = self.history_window[-5:]
            recent_correct = sum(1 for h in last if h.get("correct")) / max(len(last), 1)
        return mastery + [avg_mastery, weak_count / max(n, 1), recent_correct, history_len / 100.0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mastery_vector": self.mastery_vector,
            "topic_graph": self.topic_graph,
            "history_window": self.history_window[-10:],
        }


class RLAction:
    """RL 动作空间：选择下一个要学习的 topic。"""

    def __init__(self, topic_id: str, score: float = 0.0):
        self.topic_id = topic_id
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {"topic_id": self.topic_id, "score": round(self.score, 4)}


class RLReward:
    """奖励函数：R = α·mastery_gain + β·coverage_rate - γ·prerequisite_violation。"""

    def __init__(
        self,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def compute(
        self,
        mastery_before: dict[str, float],
        mastery_after: dict[str, float],
        selected_topic: str,
        prerequisites: list[str],
        total_topics: int,
    ) -> float:
        mastery_gain = sum(
            mastery_after.get(t, 0) - mastery_before.get(t, 0)
            for t in mastery_before
        )
        covered = sum(1 for m in mastery_after.values() if m >= 0.7)
        coverage_rate = covered / max(total_topics, 1)
        violation = 0.0
        for prereq in prerequisites:
            if mastery_after.get(prereq, 0) < 0.4:
                violation += 1.0
        return self.alpha * mastery_gain + self.beta * coverage_rate - self.gamma * violation

    def to_dict(self) -> dict[str, Any]:
        return {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma}


class PolicyNetwork:
    """轻量 MLP 策略网络：输入 state embedding，输出 topic scores。

    使用 numpy 实现（零额外依赖），可选 torch 加速。
    冷启动时退化为启发式评分。
    """

    def __init__(self, input_dim: int = 0, hidden_dim: int = 64, output_dim: int = 0):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.weights: list[list[list[float]]] = []
        self.biases: list[list[float]] = []
        self.step_count = 0
        self._loaded = False

    def init_weights(self, input_dim: int, output_dim: int):
        """Xavier 初始化。"""
        import random
        self.input_dim = input_dim
        self.output_dim = output_dim
        scale_in = math.sqrt(2.0 / (input_dim + self.hidden_dim))
        scale_out = math.sqrt(2.0 / (self.hidden_dim + output_dim))
        w1 = [[random.gauss(0, scale_in) for _ in range(input_dim)] for _ in range(self.hidden_dim)]
        b1 = [0.0] * self.hidden_dim
        w2 = [[random.gauss(0, scale_out) for _ in range(self.hidden_dim)] for _ in range(output_dim)]
        b2 = [0.0] * output_dim
        self.weights = [w1, w2]
        self.biases = [b1, b2]
        self._loaded = True

    def forward(self, x: list[float]) -> list[float]:
        """前向传播：ReLU hidden → linear output。"""
        if not self._loaded or not self.weights:
            return [0.0] * self.output_dim
        h = []
        for i in range(self.hidden_dim):
            s = self.biases[0][i] + sum(
                self.weights[0][i][j] * x[j]
                for j in range(min(len(x), self.input_dim))
            )
            h.append(max(0.0, s))
        out = []
        for i in range(self.output_dim):
            s = self.biases[1][i] + sum(
                self.weights[1][i][j] * h[j]
                for j in range(self.hidden_dim)
            )
            out.append(s)
        return out

    def save(self, path: str):
        data = {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "output_dim": self.output_dim,
            "weights": self.weights,
            "biases": self.biases,
            "step_count": self.step_count,
        }
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    def load(self, path: str) -> bool:
        if not Path(path).is_file():
            return False
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.input_dim = data["input_dim"]
            self.hidden_dim = data["hidden_dim"]
            self.output_dim = data["output_dim"]
            self.weights = data["weights"]
            self.biases = data["biases"]
            self.step_count = data.get("step_count", 0)
            self._loaded = True
            return True
        except Exception as e:
            logger.warning(f"Failed to load RL model: {e}")
            return False


class RLPlanner:
    """RL 学习路径规划器。

    策略模式：
    - 冷启动（无训练数据）：α=1.0 退化为静态启发式
    - 逐步退火：α 从 1.0 → 0.3，RL 权重逐步增大
    """

    def __init__(self, reward: RLReward | None = None):
        self.reward = reward or RLReward()
        self.policy = PolicyNetwork()
        self._step = 0

    def _heuristic_scores(
        self,
        state: RLState,
        candidate_topics: list[str],
        prerequisites_map: dict[str, list[str]],
    ) -> list[float]:
        """启发式评分：弱项优先 + prerequisite 未满足惩罚。"""
        scores = []
        for tid in candidate_topics:
            mastery = state.mastery_vector.get(tid, 0.0)
            weakness_score = 1.0 - mastery
            prereqs = prerequisites_map.get(tid, [])
            prereq_penalty = sum(
                1.0 for p in prereqs if state.mastery_vector.get(p, 0) < 0.4
            ) / max(len(prereqs), 1)
            score = weakness_score * 0.7 - prereq_penalty * 0.3
            scores.append(score)
        return scores

    def _get_alpha(self) -> float:
        """退火系数：从 _ALPHA_START 线性退火到 _ALPHA_END。"""
        if self._step >= _WARMUP_STEPS:
            return _ALPHA_END
        return _ALPHA_START - (_ALPHA_START - _ALPHA_END) * (self._step / _WARMUP_STEPS)

    @langfuse_observed("rl.planner.recommend_path", as_type="chain")
    def recommend_path(
        self,
        state: RLState,
        candidate_topics: list[str],
        prerequisites_map: dict[str, list[str]],
        top_k: int = 10,
    ) -> list[RLAction]:
        """推荐学习路径。

        混合策略：score = α·heuristic + (1-α)·rl_policy
        """
        if not candidate_topics:
            return []

        alpha = self._get_alpha()
        heuristic = self._heuristic_scores(state, candidate_topics, prerequisites_map)

        all_ids = list(state.mastery_vector.keys()) or candidate_topics
        embedding = state.to_embedding(all_ids)

        if not self.policy._loaded:
            self.policy.init_weights(len(embedding), len(candidate_topics))
        rl_scores = self.policy.forward(embedding)
        while len(rl_scores) < len(candidate_topics):
            rl_scores.append(0.0)

        combined = []
        for i, tid in enumerate(candidate_topics):
            h = heuristic[i] if i < len(heuristic) else 0.0
            r = rl_scores[i] if i < len(rl_scores) else 0.0
            combined.append((tid, alpha * h + (1 - alpha) * r))

        combined.sort(key=lambda x: x[1], reverse=True)
        actions = [RLAction(tid, score) for tid, score in combined[:top_k]]

        self._step += 1
        return actions

    def record_decision(
        self,
        state: RLState,
        action: RLAction,
        reward_value: float,
        mastery_before: dict[str, float],
        mastery_after: dict[str, float],
    ) -> dict[str, Any]:
        """记录 RL 决策到 LangFuse metadata。"""
        record = {
            "step": self._step,
            "alpha": self._get_alpha(),
            "state_summary": {
                "avg_mastery": sum(state.mastery_vector.values()) / max(len(state.mastery_vector), 1),
                "weak_count": sum(1 for m in state.mastery_vector.values() if m < 0.4),
            },
            "action": action.to_dict(),
            "reward": round(reward_value, 4),
            "mastery_delta": {
                tid: round(mastery_after.get(tid, 0) - mastery_before.get(tid, 0), 3)
                for tid in mastery_before
                if abs(mastery_after.get(tid, 0) - mastery_before.get(tid, 0)) > 0.01
            },
        }
        logger.info(f"RL decision: step={self._step}, topic={action.topic_id}, reward={reward_value:.3f}")
        return record

    def save_model(self, path: str = ""):
        save_path = path or os.path.join(_RL_MODEL_DIR, "rl_policy.json") if _RL_MODEL_DIR else ""
        if save_path:
            self.policy.save(save_path)
            logger.info(f"RL model saved to {save_path}")

    def load_model(self, path: str = "") -> bool:
        load_path = path or os.path.join(_RL_MODEL_DIR, "rl_policy.json") if _RL_MODEL_DIR else ""
        if load_path:
            return self.policy.load(load_path)
        return False


_rl_planner: RLPlanner | None = None


def get_rl_planner() -> RLPlanner:
    global _rl_planner
    if _rl_planner is None:
        _rl_planner = RLPlanner()
        if _RL_MODEL_DIR:
            _rl_planner.load_model()
    return _rl_planner