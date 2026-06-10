"""
ETHOS-AEGIS · 4D Immersive Visual Package Test Module
======================================================
Four scientific dimensions:
  X axis → NodeType space (governance topology)
  Y axis → TaskState lifecycle (execution phase)
  Z axis → Ethical weight / policy risk score
  T axis → Temporal evolution (simulation ticks)

Renders the live ETHOS graph as a 4D animated hypercube
where each task traces a trajectory through ethical spacetime.
"""

from .renderer import FourDRenderer
from .spacetime import EthosSpacetime
from .test_harness import FourDTestHarness
from .metrics import SpacetimeMetrics

__all__ = ["FourDRenderer", "EthosSpacetime", "FourDTestHarness", "SpacetimeMetrics"]
__version__ = "1.0.0"
