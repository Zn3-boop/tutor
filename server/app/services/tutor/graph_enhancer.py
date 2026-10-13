"""增强版知识图谱服务。

功能扩展：
  - 交互式节点图（节点大小=重要性，颜色=掌握度）
  - 知识点关联分析（共现频率、依赖强度）
  - 学习路径推荐（基于掌握度和先修关系）
  - 图谱统计指标（中心性、密度、连通性）
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.tutor.learner import LearnerModel
from app.services.tutor.store import TutorStore

from app.services.observability.langfuse_client import langfuse_observed
from app.services.observability.tracing import traced_execution

logger = logging.getLogger(__name__)

# 节点大小映射（基于重要性/出现频率）
NODE_SIZE_SCALE = {"low": 4, "medium": 7, "high": 10, "critical": 13}

# 掌握度颜色梯度（红->橙->绿 + 灰）
MASTERY_COLORS = {
    "weak": "#F87171",      # < 0.4 红粉
    "learning": "#FB923C",  # 0.4-0.7 橙色
    "mastered": "#10B981",  # >= 0.7 绿色
    "unlearned": "#94A3B8"  # 未学习 灰色
}


class GraphEnhancer:
    """增强的知识图谱服务。"""
    
    def __init__(self, store: TutorStore, learner: LearnerModel | None = None):
        self.store = store
        self.learner = learner or LearnerModel()
    
    @langfuse_observed("graph_enhancer.build_graph")
    def build_enhanced_graph(self, student_id: str = "") -> dict[str, Any]:
        """
        构建增强版知识图谱。
        
        Returns:
            {
                "nodes": [...],         # 节点列表（含元数据）
                "edges": [...],         # 边列表（含权重）
                "clusters": [...],      # 知识点簇
                "statistics": {...},    # 图谱统计
                "recommended_path": [...] # 推荐学习路径
            }
        """
        topics = self.store.list_topics_by_id()
        units = self.store.list_units()
        
        # 获取学生掌握度
        mastery_map: dict[str, float] = {}
        if student_id:
            student = self.store.get_student(student_id)
            if student:
                summary = self.learner.mastery_summary(student, topics)
                mastery_map = {tid: data["mastery"] for tid, data in summary.items()}

        # OpenTelemetry span 记录查询链路
        with traced_execution("graph_query", {
            "student_id": student_id,
            "topic_count": len(topics)
        }) as span:
            pass
        
        # 计算节点重要性（基于在单元中的出现频率）
        importance_map = self._compute_importance(topics, units)

        # 每个 topic 关联的内容来源（哪个课程/课件/章节）——用于节点标注
        topic_units: dict[str, dict[str, Any]] = {
            tid: {"count": 0, "source_titles": [], "samples": []} for tid in topics
        }
        for unit in units:
            src = self.store.get_source(unit.get("source_id", "")) or {}
            src_title = src.get("title") or src.get("name") or "未知材料"
            for tid in (unit.get("topic_ids") or []):
                if tid not in topic_units:
                    continue
                tu = topic_units[tid]
                tu["count"] += 1
                if src_title not in tu["source_titles"]:
                    tu["source_titles"].append(src_title)
                if len(tu["samples"]) < 3:
                    tu["samples"].append((unit.get("text") or "")[:120].replace("\n", " "))

        # 构建节点
        nodes = []
        for tid, topic in topics.items():
            m = mastery_map.get(tid)
            imp = importance_map.get(tid, 0.5)
            tu = topic_units.get(tid, {"count": 0, "source_titles": [], "samples": []})
            src_titles = tu["source_titles"]
            unit_count = tu["count"]

            # 自动生成节点说明（课程/章节/是什么）
            description = (topic.get("description") or "").strip()
            if not description:
                if tu["samples"]:
                    description = tu["samples"][0][:90]
                else:
                    description = ""
            origin_note = "、".join(src_titles) if src_titles else "尚无关联素材"
            annotation = (
                f"主题「{topic.get('name', tid)}」：{description or '课程核心概念'}。"
                f"来自 {origin_note}，共 {unit_count} 个内容单元。"
            )

            node = {
                "id": tid,
                "name": topic.get("name", tid),
                "concepts": topic.get("concepts", []),
                "description": description,
                "annotation": annotation,
                "source_titles": src_titles,
                "unit_count": unit_count,
                "mastery": round(m, 3) if m is not None else None,
                "mastery_level": self._mastery_level(m),
                "importance": round(imp, 2),
                "size": self._node_size(imp),
                "color": self._node_color(m),
                "prereq_count": len(topic.get("prerequisites", []) or []),
                "dependent_count": self._count_dependents(tid, topics)
            }
            nodes.append(node)

        # 构建边（含权重 + 关系标注）
        edges = self._build_weighted_edges(topics, importance_map, topic_units)
        
        # 识别簇（基于主题聚类）
        clusters = self._detect_clusters(topics, units)
        
        # 计算统计指标
        statistics = self._compute_graph_statistics(nodes, edges)
        
        # 生成推荐学习路径
        recommended_path = []
        if student_id and mastery_map:
            recommended_path = self._generate_recommended_path(
                student_id, topics, mastery_map, importance_map
            )
        
        # 全图课程来源（用于“这门课/这份教材讲什么”的标注）
        course_titles: list[str] = []
        seen_src: set[str] = set()
        for units_tu in topic_units.values():
            for s in units_tu.get("source_titles", []):
                if s not in seen_src:
                    seen_src.add(s)
                    course_titles.append(s)

        return {
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "statistics": statistics,
            "recommended_path": recommended_path,
            "meta": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "student_id": student_id or None,
                "course_titles": course_titles,
                "legend": {
                    "node_color": "节点颜色 = 掌握度（灰=未学 / 红=薄弱 / 橙=学习中 / 绿=已掌握）",
                    "node_size": "节点大小 = 知识点重要性（来源中出现频率）",
                    "edge_arrow": "箭头 a → b 表示 a 是 b 的前置知识（先修）",
                },
                "generated_at": self._timestamp()
            }
        }
    
    def _compute_importance(self, topics: dict, units: list[dict]) -> dict[str, float]:
        """计算每个知识点的重要性（基于在单元中的出现频率）。"""
        counts: dict[str, int] = {}
        total = 0
        
        for unit in units:
            topic_ids = unit.get("topic_ids", [])
            for tid in topic_ids:
                counts[tid] = counts.get(tid, 0) + 1
                total += 1
        
        if total == 0:
            return {tid: 0.5 for tid in topics}
        
        # 归一化到 [0.3, 1.0]
        max_count = max(counts.values()) if counts else 1
        return {
            tid: 0.3 + 0.7 * (counts.get(tid, 0) / max_count)
            for tid in topics
        }
    
    def _node_size(self, importance: float) -> str:
        """根据重要性返回节点大小类别。"""
        if importance >= 0.9:
            return "critical"
        if importance >= 0.7:
            return "high"
        if importance >= 0.4:
            return "medium"
        return "low"
    
    def _node_color(self, mastery: float | None) -> str:
        """根据掌握度返回节点颜色。"""
        if mastery is None:
            return MASTERY_COLORS["unlearned"]
        if mastery < 0.4:
            return MASTERY_COLORS["weak"]
        if mastery < 0.7:
            return MASTERY_COLORS["learning"]
        return MASTERY_COLORS["mastered"]
    
    def _mastery_level(self, mastery: float | None) -> str:
        """返回掌握度级别标签。"""
        if mastery is None:
            return "unlearned"
        if mastery < 0.4:
            return "weak"
        if mastery < 0.7:
            return "learning"
        return "mastered"
    
    def _count_dependents(self, tid: str, topics: dict) -> int:
        """统计有多少主题依赖当前主题。"""
        count = 0
        for other_tid, topic in topics.items():
            if tid in (topic.get("prerequisites") or []):
                count += 1
        return count
    
    def _build_weighted_edges(self, topics: dict, importance_map: dict,
                             topic_units: dict[str, dict[str, Any]] | None = None) -> list[dict]:
        """构建带权重的边（含先修关系标注）。"""
        edges = []
        seen: set[tuple[str, str]] = set()
        topic_units = topic_units or {}

        for tid, topic in topics.items():
            for pre in topic.get("prerequisites") or []:
                if pre not in topics or (pre, tid) in seen:
                    continue

                # 权重基于两个节点的重要性
                imp_pre = importance_map.get(pre, 0.5)
                imp_tid = importance_map.get(tid, 0.5)
                weight = (imp_pre + imp_tid) / 2

                pre_name = topics[pre].get("name", pre)
                tid_name = topic.get("name", tid)
                srcs = sorted(
                    set((topic_units.get(pre, {}).get("source_titles") or [])
                        + (topic_units.get(tid, {}).get("source_titles") or []))
                )
                annotation = f"「{pre_name}」是「{tid_name}」的前置知识，建议先学「{pre_name}」。"
                if srcs:
                    annotation += f"（课程素材：{'、'.join(srcs[:3])}）"

                edges.append({
                    "from": pre,
                    "to": tid,
                    "weight": round(weight, 2),
                    "type": "prerequisite",
                    "label": "先修",
                    "annotation": annotation,
                    "source_titles": srcs,
                })
                seen.add((pre, tid))

        return edges
    
    def _detect_clusters(self, topics: dict, units: list[dict]) -> list[dict]:
        """检测知识点簇（基于共同出现的单元）。"""
        # 简单的共现聚类
        cooccurrence: dict[str, dict[str, int]] = {}
        
        for unit in units:
            tids = [t for t in unit.get("topic_ids", []) if t in topics]
            for i, tid1 in enumerate(tids):
                if tid1 not in cooccurrence:
                    cooccurrence[tid1] = {}
                for tid2 in tids[i+1:]:
                    cooccurrence[tid1][tid2] = cooccurrence[tid1].get(tid2, 0) + 1
                    if tid2 not in cooccurrence:
                        cooccurrence[tid2] = {}
                    cooccurrence[tid2][tid1] = cooccurrence[tid2].get(tid1, 0) + 1
        
        # 合并为簇（简单贪心算法）
        clusters = []
        visited = set()
        
        for tid in topics:
            if tid in visited:
                continue
            
            cluster_members = {tid}
            if tid in cooccurrence:
                # 添加强关联的主题
                related = sorted(
                    cooccurrence[tid].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                for related_tid, _ in related:
                    cluster_members.add(related_tid)
                    visited.add(related_tid)
            
            if len(cluster_members) > 1:
                clusters.append({
                    "id": f"cluster_{len(clusters)}",
                    "members": list(cluster_members),
                    "size": len(cluster_members)
                })
            
            visited.add(tid)
        
        return clusters
    
    def _compute_graph_statistics(self, nodes: list, edges: list) -> dict[str, Any]:
        """计算图谱统计指标。"""
        n = len(nodes)
        m = len(edges)
        
        # 密度
        max_edges = n * (n - 1) / 2 if n > 1 else 1
        density = m / max_edges if max_edges > 0 else 0
        
        # 平均入度/出度
        in_degree: dict[str, int] = {}
        out_degree: dict[str, int] = {}
        for edge in edges:
            out_degree[edge["from"]] = out_degree.get(edge["from"], 0) + 1
            in_degree[edge["to"]] = in_degree.get(edge["to"], 0) + 1
        
        avg_in = sum(in_degree.values()) / n if n > 0 else 0
        avg_out = sum(out_degree.values()) / n if n > 0 else 0
        
        # 连通分量（简化：只计算有边的节点）
        connected_nodes = set()
        for edge in edges:
            connected_nodes.add(edge["from"])
            connected_nodes.add(edge["to"])
        isolated = n - len(connected_nodes)
        
        return {
            "node_count": n,
            "edge_count": m,
            "density": round(density, 3),
            "avg_in_degree": round(avg_in, 2),
            "avg_out_degree": round(avg_out, 2),
            "isolated_nodes": isolated,
            "strongest_topics": self._find_strongest_nodes(nodes),
            "weakest_topics": self._find_weakest_nodes(nodes)
        }
    
    def _find_strongest_nodes(self, nodes: list) -> list[dict]:
        """找出掌握度最高的节点。"""
        mastered = [
            {"id": n["id"], "name": n["name"], "mastery": n["mastery"]}
            for n in nodes
            if n["mastery"] is not None and n["mastery"] >= 0.7
        ]
        return sorted(mastered, key=lambda x: x["mastery"], reverse=True)[:5]
    
    def _find_weakest_nodes(self, nodes: list) -> list[dict]:
        """找出掌握度最低的节点。"""
        weak = [
            {"id": n["id"], "name": n["name"], "mastery": n["mastery"]}
            for n in nodes
            if n["mastery"] is not None and n["mastery"] < 0.4
        ]
        return sorted(weak, key=lambda x: x["mastery"])[:5]
    
    def _generate_recommended_path(self, student_id: str, topics: dict,
                                   mastery_map: dict, importance_map: dict
                                   ) -> list[dict[str, Any]]:
        """生成推荐学习路径（拓扑排序保证先修在前）。"""
        scores: dict[str, float] = {}
        for tid, topic in topics.items():
            m = mastery_map.get(tid, 0.25)
            imp = importance_map.get(tid, 0.5)
            prereqs = topic.get("prerequisites") or []
            unmet_prereqs = sum(
                1 for p in prereqs
                if p in mastery_map and mastery_map[p] < 0.5
            )
            prereq_penalty = 0.5 ** unmet_prereqs
            scores[tid] = imp * (1 - m) * prereq_penalty

        topo_order = self._topological_sort(topics)
        ranked = sorted(topo_order, key=lambda tid: scores.get(tid, 0.0), reverse=True)

        seen = set()
        path = []
        for tid in ranked:
            if tid in seen:
                continue
            prereqs = topics[tid].get("prerequisites") or []
            for p in prereqs:
                if p not in seen and p in topics:
                    seen.add(p)
                    path.append(p)
            seen.add(tid)
            path.append(tid)

        return [
            {
                "rank": i + 1,
                "topic_id": tid,
                "topic_name": topics[tid].get("name", tid),
                "priority_score": round(scores.get(tid, 0.0), 3),
                "current_mastery": round(mastery_map.get(tid, 0.25), 3),
                "importance": round(importance_map.get(tid, 0.5), 2)
            }
            for i, tid in enumerate(path[:10])
        ]

    @staticmethod
    def _topological_sort(topics: dict) -> list[str]:
        """Kahn's algorithm: topological sort respecting prerequisites."""
        in_degree: dict[str, int] = {tid: 0 for tid in topics}
        adj: dict[str, list[str]] = {tid: [] for tid in topics}
        for tid, topic in topics.items():
            for p in (topic.get("prerequisites") or []):
                if p in topics:
                    adj[p].append(tid)
                    in_degree[tid] += 1
        queue = [tid for tid, d in in_degree.items() if d == 0]
        result = []
        while queue:
            queue.sort(key=lambda t: len(adj[t]), reverse=True)
            node = queue.pop(0)
            result.append(node)
            for child in adj[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        for tid in topics:
            if tid not in result:
                result.append(tid)
        return result
    
    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


_enhancer: GraphEnhancer | None = None


def get_graph_enhancer(store: TutorStore | None = None) -> GraphEnhancer:
    """获取全局图谱增强器实例。"""
    global _enhancer
    if store is None:
        from app.services.tutor.store import get_tutor_store
        store = get_tutor_store()
    
    if _enhancer is None or _enhancer.store is not store:
        _enhancer = GraphEnhancer(store=store)
    return _enhancer