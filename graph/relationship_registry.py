from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Relationship:
    name: str
    description: str


GOVERNS: Final = Relationship(
    name="GOVERNS",
    description="Defines governance or policy authority over another node.",
)

CONSTRAINS: Final = Relationship(
    name="CONSTRAINS",
    description="Applies operational or ethical constraints.",
)

INFORMS: Final = Relationship(
    name="INFORMS",
    description="Provides contextual or reasoning support.",
)

ORCHESTRATES: Final = Relationship(
    name="ORCHESTRATES",
    description="Coordinates execution between systems.",
)

DEPENDS_ON: Final = Relationship(
    name="DEPENDS_ON",
    description="Declares dependency on another node.",
)

EXECUTES: Final = Relationship(
    name="EXECUTES",
    description="Executes a task or workflow.",
)

PUBLISHES: Final = Relationship(
    name="PUBLISHES",
    description="Publishes outputs or signals.",
)

PROTECTS: Final = Relationship(
    name="PROTECTS",
    description="Provides security boundary protection.",
)

ACCELERATES: Final = Relationship(
    name="ACCELERATES",
    description="Enhances execution performance.",
)

USES: Final = Relationship(
    name="USES",
    description="Consumes functionality or capabilities.",
)

RELATIONSHIP_REGISTRY = {
    rel.name: rel
    for rel in [
        GOVERNS,
        CONSTRAINS,
        INFORMS,
        ORCHESTRATES,
        DEPENDS_ON,
        EXECUTES,
        PUBLISHES,
        PROTECTS,
        ACCELERATES,
        USES,
    ]
}
