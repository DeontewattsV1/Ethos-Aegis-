from graph.relationship_registry import RELATIONSHIP_REGISTRY


def test_relationship_registry() -> None:
    assert "GOVERNS" in RELATIONSHIP_REGISTRY
    assert "CONSTRAINS" in RELATIONSHIP_REGISTRY
