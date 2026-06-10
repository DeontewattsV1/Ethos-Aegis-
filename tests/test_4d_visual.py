"""
tests/test_4d_visual.py
=======================
Pytest suite for the ETHOS-AEGIS 4D Immersive Visual Package.

Covers:
  - SpacetimeCoordinate geometry (distance, Minkowski metric)
  - WorldLine arc length and ethical integral
  - EthosSpacetime event recording and manifold summary
  - SpacetimeMetrics: curvature tensor, phase transitions, entropy, geodesic, Lyapunov
  - FourDRenderer: smoke test (no exception on render)
  - FourDTestHarness: end-to-end integration
"""

import io
import math
import sys
import pytest

# ──────────────────────────────────────────────────────────────
# spacetime tests
# ──────────────────────────────────────────────────────────────

from ethos_4d.spacetime import (
    SpacetimeCoordinate,
    WorldLine,
    EthosSpacetime,
    TASK_STATE_ORDINAL,
    NODE_TYPE_ORDINAL,
    ETHICAL_WEIGHT,
)


class TestSpacetimeCoordinate:
    def test_zero_distance_to_self(self):
        c = SpacetimeCoordinate(x=1.0, y=2.0, z=0.5, t=0.0)
        assert c.distance_to(c) == 0.0

    def test_known_distance(self):
        c1 = SpacetimeCoordinate(x=0, y=0, z=0, t=0)
        c2 = SpacetimeCoordinate(x=1, y=1, z=1, t=1)
        assert abs(c1.distance_to(c2) - 2.0) < 1e-9

    def test_to_dict_keys(self):
        c = SpacetimeCoordinate(x=1.0, y=2.0, z=0.9, t=0.5, task_id="t1", state="EXECUTING")
        d = c.to_dict()
        assert set(d.keys()) == {"x", "y", "z", "t", "task_id", "state", "node_type", "label"}


class TestWorldLine:
    def _make_wl(self):
        wl = WorldLine(task_id="test-task")
        for i, state in enumerate(["QUEUED", "VALIDATED", "ETHICAL_CHECK", "EXECUTING"]):
            wl.add_point(SpacetimeCoordinate(
                x=float(i), y=float(TASK_STATE_ORDINAL[state]),
                z=ETHICAL_WEIGHT[state], t=float(i * 0.1),
                task_id="test-task", state=state,
            ))
        return wl

    def test_arc_length_positive(self):
        wl = self._make_wl()
        assert wl.arc_length() > 0.0

    def test_arc_length_single_point_zero(self):
        wl = WorldLine(task_id="solo")
        wl.add_point(SpacetimeCoordinate(x=0, y=0, z=0, t=0))
        assert wl.arc_length() == 0.0

    def test_ethical_integral_positive(self):
        wl = self._make_wl()
        assert wl.ethical_integral() >= 0.0

    def test_final_state(self):
        wl = self._make_wl()
        assert wl.final_state == "EXECUTING"


class TestEthosSpacetime:
    def test_record_and_retrieve(self):
        st = EthosSpacetime()
        coord = st.record_task_event("t1", "QUEUED", "Task", tick=0.0)
        assert coord.state == "QUEUED"
        assert "t1" in st.world_lines

    def test_manifold_summary_structure(self):
        st = EthosSpacetime()
        st.record_task_event("t1", "QUEUED", tick=0.0)
        st.record_task_event("t1", "EXECUTING", tick=0.1)
        s = st.manifold_summary()
        assert "total_world_lines" in s
        assert s["total_world_lines"] == 1
        assert s["total_events"] == 2

    def test_ethical_weight_range(self):
        for state, weight in ETHICAL_WEIGHT.items():
            assert 0.0 <= weight <= 1.0, f"{state} out of range"

    def test_state_ordinals_unique(self):
        vals = list(TASK_STATE_ORDINAL.values())
        assert len(vals) == len(set(vals))

    def test_node_type_ordinals_unique(self):
        vals = list(NODE_TYPE_ORDINAL.values())
        assert len(vals) == len(set(vals))


# ──────────────────────────────────────────────────────────────
# metrics tests
# ──────────────────────────────────────────────────────────────

from ethos_4d.metrics import SpacetimeMetrics


def _populated_spacetime():
    st = EthosSpacetime()
    tasks = [
        ("t1", "Agent",      ["QUEUED","VALIDATED","ETHICAL_CHECK","EXECUTING","COMMITTED"]),
        ("t2", "Governance", ["QUEUED","VALIDATED","ETHICAL_CHECK","FAILED"]),
        ("t3", "Workflow",   ["QUEUED","PLANNED","EXECUTING","ARCHIVED"]),
    ]
    tick = 0.0
    for tid, ntype, states in tasks:
        for state in states:
            st.record_task_event(tid, state, ntype, tick=tick)
            tick += 0.05
    return st


class TestSpacetimeMetrics:
    def setup_method(self):
        self.metrics = SpacetimeMetrics(_populated_spacetime())

    def test_curvature_count(self):
        tensors = self.metrics.ethical_curvature()
        # Should be n_states - 2
        from ethos_4d.spacetime import TASK_STATE_ORDINAL
        assert len(tensors) == len(TASK_STATE_ORDINAL) - 2

    def test_phase_transitions_non_empty(self):
        transitions = self.metrics.detect_phase_transitions()
        assert len(transitions) > 0

    def test_critical_phase_exists(self):
        transitions = self.metrics.detect_phase_transitions()
        crits = [t for t in transitions if t.significance == "CRITICAL"]
        assert len(crits) > 0  # VALIDATED→ETHICAL_CHECK jump

    def test_entropy_positive(self):
        H = self.metrics.manifold_entropy()
        assert H >= 0.0

    def test_geodesic_reports_count(self):
        reports = self.metrics.geodesic_reports()
        assert len(reports) == 3  # one per task with >=2 coords

    def test_geodesic_ratio_gte_one(self):
        for g in self.metrics.geodesic_reports():
            assert g.deviation_ratio >= 1.0 - 1e-9  # arc ≥ straight line

    def test_lyapunov_returns_float(self):
        lam = self.metrics.lyapunov_estimate()
        assert lam is None or isinstance(lam, float)

    def test_full_report_structure(self):
        report = self.metrics.full_report()
        assert "curvature_tensors" in report
        assert "phase_transitions" in report
        assert "manifold_entropy_bits" in report
        assert "geodesic_reports" in report
        assert "lyapunov_exponent" in report


# ──────────────────────────────────────────────────────────────
# renderer smoke test
# ──────────────────────────────────────────────────────────────

from ethos_4d.renderer import FourDRenderer


class TestFourDRenderer:
    def test_render_no_exception(self, capsys):
        st = _populated_spacetime()
        renderer = FourDRenderer(st, width=60)
        renderer.render(tick=0.5)  # should not raise
        captured = capsys.readouterr()
        assert "ETHOS-AEGIS" in captured.out

    def test_ethical_heatmap_no_exception(self, capsys):
        st = EthosSpacetime()
        renderer = FourDRenderer(st)
        renderer.ethical_heatmap()
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_hypercube_no_exception(self, capsys):
        st = EthosSpacetime()
        renderer = FourDRenderer(st)
        renderer.hypercube(tick=1.0)


# ──────────────────────────────────────────────────────────────
# harness integration test
# ──────────────────────────────────────────────────────────────

from ethos_4d.test_harness import FourDTestHarness


class TestFourDTestHarness:
    def test_simulate_records_all_tasks(self):
        harness = FourDTestHarness()
        harness.simulate_tasks()
        from ethos_4d.test_harness import TEST_TASKS
        assert len(harness.spacetime.world_lines) == len(TEST_TASKS)

    def test_total_events_match(self):
        harness = FourDTestHarness()
        harness.simulate_tasks()
        from ethos_4d.test_harness import TEST_TASKS
        expected = sum(len(t["states"]) for t in TEST_TASKS)
        actual = sum(len(wl.coordinates) for wl in harness.spacetime.world_lines.values())
        assert actual == expected

    def test_metrics_run_no_exception(self, capsys):
        harness = FourDTestHarness()
        harness.simulate_tasks()
        harness.run_metrics()

    def test_entropy_after_simulation(self):
        harness = FourDTestHarness()
        harness.simulate_tasks()
        H = harness.metrics.manifold_entropy()
        assert H > 0.0  # tasks spread across multiple final states
