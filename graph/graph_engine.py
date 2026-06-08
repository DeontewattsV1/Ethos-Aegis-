from __future__ import annotations

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from ethos_core.logging import logger
from ethos_core.settings import settings
from graph.ontology import GraphNode


class GraphEngine:
    def __init__(self) -> None:
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(
                settings.neo4j_user,
                settings.neo4j_password,
            ),
        )

    def close(self) -> None:
        self.driver.close()

    def create_node(self, node: GraphNode) -> None:
        query = f"""
        CREATE (n:GraphNode:{node.node_type.value} {{
            id: $id,
            name: $name,
            node_type: $node_type,
            metadata: $metadata,
            created_at: datetime($created_at)
        }})
        """

        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    id=node.id,
                    name=node.name,
                    node_type=node.node_type.value,
                    metadata=node.metadata,
                    created_at=node.created_at.isoformat(),
                )

            logger.info(
                "graph.node.created",
                node_id=node.id,
                node_name=node.name,
            )

        except Neo4jError as exc:
            logger.error(
                "graph.node.create_failed",
                error=str(exc),
            )
            raise

    def create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
    ) -> None:

        query = f"""
        MATCH (a:GraphNode {{id: $source_id}})
        MATCH (b:GraphNode {{id: $target_id}})
        CREATE (a)-[:{relationship_type}]->(b)
        """

        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    source_id=source_id,
                    target_id=target_id,
                )

            logger.info(
                "graph.relationship.created",
                source_id=source_id,
                target_id=target_id,
                relationship=relationship_type,
            )

        except Neo4jError as exc:
            logger.error(
                "graph.relationship.failed",
                error=str(exc),
            )
            raise
