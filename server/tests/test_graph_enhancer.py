"""Unit tests for the enhanced graph visualizer."""

import pytest

from app.services.tutor.graph_enhancer import (
    GraphEnhancer,
    get_graph_enhancer,
    MASTERY_COLORS,
)


@pytest.fixture
def mock_store(tmp_path):
    """Create a minimal in-memory TutorStore for testing."""
    from app.services.tutor.store import TutorStore
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return TutorStore(str(data_dir))


@pytest.fixture
def enhancer(mock_store):
    return GraphEnhancer(mock_store)


class TestMasteryColors:
    def test_color_map_has_required_levels(self):
        required = {"weak", "learning", "mastered", "unlearned"}
        assert set(MASTERY_COLORS.keys()) == required

    def test_colors_are_hex(self):
        for color in MASTERY_COLORS.values():
            assert color.startswith("#")
            assert len(color) == 7


class TestNodeHelpers:
    def test_mastery_level_mapping(self, enhancer):
        assert enhancer._mastery_level(None) == "unlearned"
        assert enhancer._mastery_level(0.3) == "weak"
        assert enhancer._mastery_level(0.5) == "learning"
        assert enhancer._mastery_level(0.75) == "mastered"

    def test_node_color_returns_valid_hex(self, enhancer):
        colors = {
            None: MASTERY_COLORS["unlearned"],
            0.25: MASTERY_COLORS["weak"],
            0.55: MASTERY_COLORS["learning"],
            0.85: MASTERY_COLORS["mastered"],
        }
        for m, expected in colors.items():
            assert enhancer._node_color(m) == expected

    def test_node_size_category_mapping(self, enhancer):
        assert enhancer._node_size(0.95) == "critical"
        assert enhancer._node_size(0.75) == "high"
        assert enhancer._node_size(0.45) == "medium"
        assert enhancer._node_size(0.2) == "low"


class TestImportanceComputation:
    def test_importance_normalized_between_bounds(self, enhancer):
        topics = {"t1": {}, "t2": {}, "t3": {}}
        units = [
            {"topic_ids": ["t1", "t2"]},
            {"topic_ids": ["t1"]},
            {"topic_ids": ["t2", "t3"]},
        ]
        importance = enhancer._compute_importance(topics, units)
        for tid, val in importance.items():
            assert 0.3 <= val <= 1.0, f"Importance for {tid} out of bounds"

    def test_more_appearances_higher_importance(self, enhancer):
        topics = {"t1": {}, "t2": {}, "t3": {}}
        units = [
            {"topic_ids": ["t1"]},
            {"topic_ids": ["t1"]},
            {"topic_ids": ["t2"]},
            {"topic_ids": ["t3", "t3"]},
        ]
        importance = enhancer._compute_importance(topics, units)
        assert importance["t1"] >= importance["t2"]
        assert 0.3 <= importance["t3"] <= 1.0


class TestEdgeConstruction:
    def test_edges_have_weights(self, enhancer):
        topics = {
            "t1": {"prerequisites": []},
            "t2": {"prerequisites": ["t1"]},
            "t3": {"prerequisites": ["t1", "t2"]},
        }
        importance_map = {"t1": 0.5, "t2": 0.6, "t3": 0.7}
        edges = enhancer._build_weighted_edges(topics, importance_map)
        assert len(edges) >= 2
        for edge in edges:
            assert "weight" in edge
            assert 0.3 <= edge["weight"] <= 1.0
            assert edge["type"] == "prerequisite"


class TestClusterDetection:
    def test_clusters_contain_multiple_nodes_if_possible(self, enhancer):
        topics = {"t1": {}, "t2": {}, "t3": {}}
        units = [
            {"topic_ids": ["t1", "t2", "t3"]},
            {"topic_ids": ["t1", "t2"]},
        ]
        clusters = enhancer._detect_clusters(topics, units)
        multi_member_clusters = [c for c in clusters if len(c["members"]) > 1]
        assert len(multi_member_clusters) > 0

    def test_empty_input_yields_no_crash(self, enhancer):
        clusters = enhancer._detect_clusters({}, [])
        assert isinstance(clusters, list)


class TestGraphStatistics:
    def _make_nodes(self, n, with_mastery=False):
        nodes = []
        for i in range(n):
            node = {"id": str(i), "name": f"Node{i}"}
            if with_mastery:
                node["mastery"] = 0.5
            else:
                node["mastery"] = None
            nodes.append(node)
        return nodes

    def test_density_calculation(self, enhancer):
        nodes = self._make_nodes(3, with_mastery=True)
        edges = [
            {"from": "0", "to": "1"},
            {"from": "1", "to": "2"},
            {"from": "0", "to": "2"},
        ]
        stats = enhancer._compute_graph_statistics(nodes, edges)
        assert stats["node_count"] == 3
        assert stats["edge_count"] == 3
        assert stats["density"] == 1.0

    def test_isolated_nodes_counted(self, enhancer):
        nodes = self._make_nodes(3, with_mastery=True)
        edges = []
        stats = enhancer._compute_graph_statistics(nodes, edges)
        assert stats["isolated_nodes"] == 3
        assert stats["density"] == 0.0

    def test_avg_degree_zero_when_no_edges(self, enhancer):
        nodes = self._make_nodes(2, with_mastery=True)
        stats = enhancer._compute_graph_statistics(nodes, [])
        assert stats["avg_in_degree"] == 0.0
        assert stats["avg_out_degree"] == 0.0

    def test_strongest_and_weakest_topics(self, enhancer):
        nodes = [
            {"id": "t1", "name": "One", "mastery": 0.85},
            {"id": "t2", "name": "Two", "mastery": 0.35},
            {"id": "t3", "name": "Three", "mastery": 0.72},
            {"id": "t4", "name": "Four", "mastery": 0.2},
        ]
        strongest = enhancer._find_strongest_nodes(nodes)
        weakest = enhancer._find_weakest_nodes(nodes)
        assert strongest[0]["id"] == "t1"
        assert weakest[0]["id"] == "t4"
        assert len(strongest) <= 5
        assert len(weakest) <= 5

    def test_empty_graph(self, enhancer):
        stats = enhancer._compute_graph_statistics([], [])
        assert stats["node_count"] == 0
        assert stats["edge_count"] == 0
        assert stats["density"] == 0.0


class TestRecommendedPath:
    def test_path_respects_prerequisites_penalty(self, enhancer):
        topics = {
            "t1": {"prerequisites": []},
            "t2": {"prerequisites": ["t1"]},
            "t3": {"prerequisites": ["t2"]},
        }
        mastery_map = {"t1": 0.9, "t2": 0.3, "t3": 0.3}
        importance_map = {"t1": 0.5, "t2": 0.5, "t3": 0.9}
        path = enhancer._generate_recommended_path(
            "s1", topics, mastery_map, importance_map
        )
        if path:
            idx_t2 = next((i for i, p in enumerate(path) if p["topic_id"] == "t2"), None)
            idx_t3 = next((i for i, p in enumerate(path) if p["topic_id"] == "t3"), None)
            if idx_t2 is not None and idx_t3 is not None:
                assert idx_t2 < idx_t3


class TestBuildEnhancedGraph:
    def test_full_flow_without_student(self, enhancer):
        result = enhancer.build_enhanced_graph("")
        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "statistics" in result
        assert "recommended_path" in result
        assert result["meta"]["student_id"] is None

    def test_full_flow_with_student(self, enhancer, mock_store):
        mock_store.create_student(name="Test User")
        students = mock_store.list_students()
        student_id = students[0]["student_id"]
        result = enhancer.build_enhanced_graph(student_id)
        assert result["meta"]["student_id"] == student_id
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)


class TestSingleton:
    def test_get_graph_enhancer_returns_singleton(self, mock_store):
        assert get_graph_enhancer(mock_store) is get_graph_enhancer(mock_store)