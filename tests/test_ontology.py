from ethos_core.types import NodeType
from graph.ontology import GovernanceNode


def test_governance_node_creation() -> None:
    node = GovernanceNode(
        name="ETHOS-AEGIS"
    )

    assert node.node_type == NodeType.GOVERNANCE
    assert node.name == "ETHOS-AEGIS"
